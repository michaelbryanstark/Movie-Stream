#!/usr/bin/env python3
"""
Sync your Jellyfin library into team_netflix.db.

Setup (put this file next to team_netflix.db; it needs nothing beyond Python 3):
    1. In Jellyfin: Dashboard -> API Keys -> "+" -> name it "Team Netflix" -> copy the key.
    2. export JELLYFIN_URL="http://192.168.1.50:8096"      # your server's LAN address, not localhost
       export JELLYFIN_API_KEY="paste-the-key-here"
    3. python sync_jellyfin.py --dry-run                     # preview, writes nothing
       python sync_jellyfin.py                               # do it

What it does
  * Movies -> film, Series -> tv_show (title, runtime in minutes, first genre, poster, backdrop).
  * Remembers each item's Jellyfin ID (film.jellyfin_id / tv_show.jellyfin_id), which is what
    powers the "Play on Jellyfin" button.
  * A Jellyfin title whose name matches a title already in your database (e.g. the seed data's
    "Inception") is LINKED to that row, so existing likes / watched marks are kept.
  * Adds cast (top 10 actors) and directors, reusing people who already exist.
  * Safe to re-run any time: new titles are added, existing ones refreshed, nothing duplicated.
  * Jellyfin is the source of truth for the fields above: a re-run overwrites hand edits to them.

Options
  --dry-run    show what would happen, change nothing
  --no-people  skip cast / director import
  --prune      afterwards, delete database titles that are NOT in Jellyfin (e.g. the demo seed
               data), along with their likes / watched marks. Asks first unless --yes is given.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "team_netflix.db"
PAGE = 50                       # items requested per API call
MAX_CAST = 10                   # actors imported per title
TICKS_PER_MINUTE = 600_000_000  # Jellyfin runtimes are in 100-nanosecond ticks

BASE = os.environ.get("JELLYFIN_URL", "").strip().rstrip("/")
if BASE and "://" not in BASE:
    BASE = "http://" + BASE
KEY = os.environ.get("JELLYFIN_API_KEY", "").strip()

# Fixed whitelists: table and column names are never taken from Jellyfin's data.
KINDS = {
    "film": {"label": "Movies", "item_type": "Movie", "table": "film",
             "actors": "film_actors", "directors": "film_directors", "col": "film_id"},
    "show": {"label": "TV shows", "item_type": "Series", "table": "tv_show",
             "actors": "tv_actors", "directors": "tv_directors", "col": "tv_show_id"},
}
PEOPLE = {"Actor": ("actor", "actors", "actor_id"),
          "Director": ("director", "directors", "director_id")}
WANTED_COLUMNS = {"film": ["poster_url", "backdrop_url", "jellyfin_id"],
                  "tv_show": ["poster_url", "backdrop_url", "jellyfin_id"],
                  "actor": ["photo_url"], "director": ["photo_url"]}


# ---------------------------------------------------------------- Jellyfin API
def jf(path, **params):
    """GET one Jellyfin endpoint -> parsed JSON (None on 404). Exits on auth or connection failure."""
    headers = {"Accept": "application/json", "Authorization": f'MediaBrowser Token="{KEY}"'}
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                sys.exit(f"Jellyfin rejected the API key (HTTP {e.code}). Create a new one under "
                         "Dashboard -> API Keys and check JELLYFIN_API_KEY.")
            if e.code == 404:
                return None
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = str(getattr(e, "reason", e))
        time.sleep(2)
    sys.exit(f"Could not reach Jellyfin at {BASE} ({last}).\n"
             "Check JELLYFIN_URL, that the server is running, and that port 8096 is open "
             "to this machine (on Fedora: sudo firewall-cmd --add-port=8096/tcp --permanent && "
             "sudo firewall-cmd --reload).")


def fetch_items(item_type, want_people):
    """Yield every item of one type, page by page."""
    fields = "Genres,RunTimeTicks" + (",People" if want_people else "")
    start = 0
    while True:
        data = jf("/Items", Recursive="true", IncludeItemTypes=item_type, Fields=fields,
                  SortBy="SortName", StartIndex=start, Limit=PAGE,
                  EnableImages="true", EnableImageTypes="Primary,Backdrop", ImageTypeLimit=1)
        items = (data or {}).get("Items", [])
        yield from items
        start += len(items)
        if not items or start >= (data or {}).get("TotalRecordCount", 0):
            return


def minutes(ticks):
    return round(ticks / TICKS_PER_MINUTE) if ticks else None


def episode_minutes(series_id):
    """Series carry no runtime of their own; borrow the first episode's."""
    data = jf("/Items", ParentId=series_id, Recursive="true", IncludeItemTypes="Episode",
              Fields="RunTimeTicks", Limit=1)
    items = (data or {}).get("Items", [])
    return minutes(items[0].get("RunTimeTicks")) if items else None


def image_urls(item):
    jid = item["Id"]
    poster = backdrop = None
    tag = (item.get("ImageTags") or {}).get("Primary")
    if tag:
        poster = f"{BASE}/Items/{jid}/Images/Primary?maxWidth=500&tag={tag}"
    tags = item.get("BackdropImageTags") or []
    if tags:
        backdrop = f"{BASE}/Items/{jid}/Images/Backdrop/0?maxWidth=1280&tag={tags[0]}"
    return poster, backdrop


# -------------------------------------------------------------------- database
def has_column(db, table, column):
    return column in {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}


def ensure_columns(db):
    for table, cols in WANTED_COLUMNS.items():
        for col in cols:
            if not has_column(db, table, col):
                db.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" VARCHAR(500)')
                print(f"Added column {table}.{col}")


def next_id(db, table, col="id"):
    return db.execute(f'SELECT COALESCE(MAX("{col}"), 0) + 1 FROM "{table}"').fetchone()[0]


def upsert_title(db, meta, item):
    """Insert or refresh one film / show. Returns (row_id, 'added' | 'updated' | 'linked')."""
    t = meta["table"]
    jid, name = item["Id"], item["Name"].strip()
    genres = item.get("Genres") or []
    genre = genres[0] if genres else None
    duration = minutes(item.get("RunTimeTicks"))
    if duration is None and meta["item_type"] == "Series":
        duration = episode_minutes(jid)
    poster, backdrop = image_urls(item)

    row = db.execute(f"SELECT id FROM {t} WHERE jellyfin_id = ?", (jid,)).fetchone()
    action = "updated"
    if row is None:  # adopt a same-named title that isn't tied to Jellyfin yet (keeps its likes)
        row = db.execute(
            f"SELECT id FROM {t} WHERE lower(title) = lower(?) "
            "AND (jellyfin_id IS NULL OR jellyfin_id = '') ORDER BY id LIMIT 1", (name,)).fetchone()
        action = "linked"
    if row:
        db.execute(
            f"UPDATE {t} SET title = ?, duration = COALESCE(?, duration), genre = COALESCE(?, genre), "
            "poster_url = COALESCE(?, poster_url), backdrop_url = COALESCE(?, backdrop_url), "
            "jellyfin_id = ? WHERE id = ?",
            (name, duration, genre, poster, backdrop, jid, row["id"]))
        return row["id"], action
    new_id = next_id(db, t)
    db.execute(
        f"INSERT INTO {t} (id, title, duration, genre, poster_url, backdrop_url, jellyfin_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", (new_id, name, duration, genre, poster, backdrop, jid))
    return new_id, "added"


def find_or_create_person(db, table, person):
    name = " ".join((person.get("Name") or "").split())
    if not name:
        return None
    photo = None
    if person.get("Id") and person.get("PrimaryImageTag"):
        photo = f"{BASE}/Items/{person['Id']}/Images/Primary?maxWidth=185&tag={person['PrimaryImageTag']}"
    row = db.execute(
        f"SELECT id FROM {table} WHERE lower(trim(coalesce(first_name, '') || ' ' || "
        "coalesce(last_name, ''))) = lower(?)", (name,)).fetchone()
    if row:
        if photo:
            db.execute(f"UPDATE {table} SET photo_url = ? WHERE id = ? "
                       "AND (photo_url IS NULL OR photo_url = '')", (photo, row["id"]))
        return row["id"]
    parts = name.split(" ")
    first, last = (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (name, "")
    new_id = next_id(db, table)
    db.execute(f"INSERT INTO {table} (id, first_name, last_name, photo_url) VALUES (?, ?, ?, ?)",
               (new_id, first, last, photo))
    return new_id


def sync_people(db, meta, title_id, people):
    actors = 0
    for p in people:
        kind = p.get("Type")
        if kind not in PEOPLE:
            continue
        if kind == "Actor":
            if actors >= MAX_CAST:
                continue
            actors += 1
        ptable, link_key, pcol = PEOPLE[kind]
        link = meta[link_key]
        pid = find_or_create_person(db, ptable, p)
        if pid is None:
            continue
        if not db.execute(f"SELECT 1 FROM {link} WHERE {pcol} = ? AND {meta['col']} = ?",
                          (pid, title_id)).fetchone():
            db.execute(f"INSERT INTO {link} ({pcol}, {meta['col']}) VALUES (?, ?)", (pid, title_id))


def prune(db, seen, assume_yes, dry):
    if not any(seen.values()):
        print("\nSkipping --prune: Jellyfin returned no titles at all, so deleting everything "
              "would almost certainly be a mistake.")
        return
    stale = {}
    for kind, meta in KINDS.items():
        rows = db.execute(f"SELECT id, title, jellyfin_id FROM {meta['table']} ORDER BY title").fetchall()
        stale[kind] = [r for r in rows if r["jellyfin_id"] not in seen[kind]]
    total = sum(len(v) for v in stale.values())
    print(f"\n--prune: {total} title(s) in the database are not in Jellyfin:")
    for kind, rows in stale.items():
        for r in rows[:15]:
            print(f"  {KINDS[kind]['label'][:-1]:8} {r['title']}")
        if len(rows) > 15:
            print(f"  ... and {len(rows) - 15} more {KINDS[kind]['label'].lower()}")
    if not total:
        return
    if dry:
        print("(dry run: nothing deleted)")
        return
    if not assume_yes:
        if not sys.stdin.isatty():
            print("Not deleting: run interactively or pass --yes to confirm.")
            return
        if input("Delete these, plus their likes / watched marks? Type 'yes': ").strip().lower() != "yes":
            print("Nothing deleted.")
            return
    for kind, rows in stale.items():
        meta = KINDS[kind]
        for r in rows:
            for table in ("watched", "liked", meta["actors"], meta["directors"]):
                db.execute(f"DELETE FROM {table} WHERE {meta['col']} = ?", (r["id"],))
            db.execute(f"DELETE FROM {meta['table']} WHERE id = ?", (r["id"],))
    # people who no longer appear in anything
    db.execute("DELETE FROM actor WHERE id NOT IN (SELECT actor_id FROM film_actors WHERE actor_id IS NOT NULL "
               "UNION SELECT actor_id FROM tv_actors WHERE actor_id IS NOT NULL)")
    db.execute("DELETE FROM director WHERE id NOT IN (SELECT director_id FROM film_directors WHERE director_id IS NOT NULL "
               "UNION SELECT director_id FROM tv_directors WHERE director_id IS NOT NULL)")
    print(f"Deleted {total} title(s).")


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Sync the Jellyfin library into team_netflix.db.")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    ap.add_argument("--no-people", action="store_true", help="skip cast and director import")
    ap.add_argument("--prune", action="store_true",
                    help="delete database titles that are not in Jellyfin (asks first)")
    ap.add_argument("--yes", action="store_true", help="don't ask for confirmation with --prune")
    args = ap.parse_args()

    if not BASE or not KEY:
        sys.exit('Set both variables first, then run again:\n'
                 '  export JELLYFIN_URL="http://192.168.1.50:8096"\n'
                 '  export JELLYFIN_API_KEY="your-key"\n'
                 "Create the key in Jellyfin under Dashboard -> API Keys.")
    if not DB_PATH.exists():
        sys.exit(f"Database not found: {DB_PATH}\nPut this script next to team_netflix.db.")

    info = jf("/System/Info") or {}
    print(f"Connected to Jellyfin {info.get('Version', '?')} "
          f"('{info.get('ServerName', BASE)}')" + ("   [DRY RUN: nothing will be saved]" if args.dry_run else ""))

    db = sqlite3.connect(DB_PATH, isolation_level=None)  # manual transactions
    db.row_factory = sqlite3.Row
    first_run = not has_column(db, "film", "jellyfin_id")
    if not args.dry_run and (first_run or args.prune):
        bak = DB_PATH.with_name(f"{DB_PATH.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        dest = sqlite3.connect(bak)
        db.backup(dest)
        dest.close()
        print(f"Backup saved: {bak.name}")

    stats = {k: Counter() for k in KINDS}
    seen = {k: set() for k in KINDS}
    db.execute("BEGIN")
    try:
        ensure_columns(db)
        for kind, meta in KINDS.items():
            print(f"\n{meta['label']}:")
            for item in fetch_items(meta["item_type"], not args.no_people):
                if not (item.get("Name") or "").strip():
                    continue
                seen[kind].add(item["Id"])
                row_id, action = upsert_title(db, meta, item)
                stats[kind][action] += 1
                print(f"  {action:7} {item['Name']}")
                if not args.no_people:
                    sync_people(db, meta, row_id, item.get("People") or [])
        if args.prune:
            prune(db, seen, args.yes, args.dry_run)
    except BaseException:
        db.execute("ROLLBACK")
        raise
    db.execute("ROLLBACK" if args.dry_run else "COMMIT")
    db.close()

    print("\nDone." + (" (dry run, nothing saved)" if args.dry_run else " Changes saved."))
    for kind, meta in KINDS.items():
        c = stats[kind]
        print(f"  {meta['label']}: {c['added']} added, {c['linked']} linked to existing, {c['updated']} refreshed")
    print('\nNext: start the frontend with  export JELLYFIN_URL="' + BASE + '"  to get the Play button.')
    if not args.no_people:
        print("Cast and directors come from Jellyfin's metadata, so they are only as complete as your library's.")


if __name__ == "__main__":
    main()
