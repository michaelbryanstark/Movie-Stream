#!/usr/bin/env python3
"""
Fill team_netflix.db with poster / backdrop / photo URLs from the TMDB API.

Setup (macOS / Linux terminal):
    1. Get a free key: themoviedb.org -> Settings -> API.
    2. export TMDB_TOKEN="paste-your-key-or-read-access-token-here"
    3. python populate_images.py --dry-run      # preview matches, writes nothing
    4. python populate_images.py                # fill films and TV shows
       python populate_images.py --people       # also actor and director photos

Never put the key in this file or commit it: your repo is public.
Standard library only; nothing to pip install.

Options:
    --dry-run   print what would be written, change nothing
    --force     overwrite images that are already set (default: only fill empty
                ones and the picsum.photos placeholders from seed_images.sql)
    --people    also fill actor.photo_url and director.photo_url

TMDB requires attribution: show the TMDB logo and a notice that the product uses
the TMDB API but is not endorsed or certified by TMDB, e.g. in an About/Credits section.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DB_PATH = Path(__file__).parent / "team_netflix.db"
API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"          # + size + path; sizes: w185, w500, w1280, original
CREDENTIAL = os.environ.get("TMDB_TOKEN", "").strip()
PAUSE = 0.12                                # seconds between calls, well under TMDB's limits


def tmdb(path, **params):
    """GET one TMDB endpoint and return parsed JSON, or None on a non-fatal failure."""
    headers = {"accept": "application/json"}
    if len(CREDENTIAL) > 60:                # long JWT = v4 read access token -> Bearer header
        headers["Authorization"] = f"Bearer {CREDENTIAL}"
    else:                                   # short hex string = v3 API key -> query parameter
        params["api_key"] = CREDENTIAL
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("TMDB rejected the credential (401). Check TMDB_TOKEN: use the API Read Access "
                         "Token or the v3 API key from themoviedb.org/settings/api.")
            if e.code == 429:               # rate limited: wait as long as TMDB asks, then retry
                time.sleep(int(e.headers.get("Retry-After", "2")) + 1)
                continue
            print(f"  HTTP {e.code} from {path}")
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  network problem: {e}")
            time.sleep(2)
    return None


def has_column(db, table, column):
    return column in {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}


def fill_titles(db, table, endpoint, date_key, force, dry):
    where = "" if force else (" WHERE poster_url IS NULL OR poster_url = '' "
                              "OR poster_url LIKE '%picsum.photos%'")
    rows = db.execute(f'SELECT id, title FROM "{table}"{where} ORDER BY id').fetchall()
    print(f"\n{table}: {len(rows)} to fill")
    missed = []
    for row in rows:
        data = tmdb(endpoint, query=row["title"], include_adult="false")
        hits = [h for h in (data or {}).get("results", []) if h.get("poster_path")]
        if not hits:
            missed.append(row["title"])
            print(f"  {row['title']!r}: no match")
            continue
        hit = hits[0]                       # TMDB lists the best match first
        shown = hit.get("title") or hit.get("name")
        year = (hit.get(date_key) or "")[:4]
        poster = f"{IMG}/w500{hit['poster_path']}"
        backdrop = f"{IMG}/w1280{hit['backdrop_path']}" if hit.get("backdrop_path") else None
        print(f"  {row['title']!r} -> {shown!r} ({year or '?'})")
        if not dry:
            db.execute(f'UPDATE "{table}" SET poster_url = ?, backdrop_url = ? WHERE id = ?',
                       (poster, backdrop, row["id"]))
        time.sleep(PAUSE)
    return missed


def fill_people(db, table, department, force, dry):
    where = "" if force else " WHERE photo_url IS NULL OR photo_url = ''"
    rows = db.execute(f'SELECT id, first_name, last_name FROM "{table}"{where} ORDER BY id').fetchall()
    print(f"\n{table}: {len(rows)} to fill")
    missed = []
    for row in rows:
        name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
        data = tmdb("/search/person", query=name, include_adult="false")
        hits = [h for h in (data or {}).get("results", []) if h.get("profile_path")]
        # Prefer someone in the right line of work (Acting / Directing) over a namesake.
        hits.sort(key=lambda h: h.get("known_for_department") != department)
        if not hits:
            missed.append(name)
            print(f"  {name!r}: no match")
            continue
        photo = f"{IMG}/w185{hits[0]['profile_path']}"
        print(f"  {name!r} -> {hits[0].get('name')!r} ({hits[0].get('known_for_department', '?')})")
        if not dry:
            db.execute(f'UPDATE "{table}" SET photo_url = ? WHERE id = ?', (photo, row["id"]))
        time.sleep(PAUSE)
    return missed


def main():
    ap = argparse.ArgumentParser(description="Fill image URLs in team_netflix.db from TMDB.")
    ap.add_argument("--dry-run", action="store_true", help="show matches, write nothing")
    ap.add_argument("--force", action="store_true", help="overwrite images that are already set")
    ap.add_argument("--people", action="store_true", help="also fill actor and director photos")
    args = ap.parse_args()

    if not CREDENTIAL:
        sys.exit('TMDB_TOKEN is not set. Get a key at themoviedb.org/settings/api, then run:\n'
                 '  export TMDB_TOKEN="your-key-here"\nand run this script again.')
    if not DB_PATH.exists():
        sys.exit(f"Database not found: {DB_PATH}\nPut this script next to team_netflix.db.")

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    needed = [("film", "poster_url"), ("tv_show", "poster_url")]
    if args.people:
        needed += [("actor", "photo_url"), ("director", "photo_url")]
    for table, col in needed:
        if not has_column(db, table, col):
            sys.exit(f"{table}.{col} is missing. Run netflix_frontend.py once (it adds the image "
                     "columns) or run add_images.sql, then try again.")

    print(f"Database: {DB_PATH}" + ("   [DRY RUN: nothing will be saved]" if args.dry_run else ""))
    missed = []
    missed += fill_titles(db, "film", "/search/movie", "release_date", args.force, args.dry_run)
    missed += fill_titles(db, "tv_show", "/search/tv", "first_air_date", args.force, args.dry_run)
    if args.people:
        missed += fill_people(db, "actor", "Acting", args.force, args.dry_run)
        missed += fill_people(db, "director", "Directing", args.force, args.dry_run)
    if not args.dry_run:
        db.commit()
    db.close()

    print("\nDone." + ("" if args.dry_run else " Changes saved."))
    if missed:
        print(f"No match for {len(missed)}: {', '.join(map(repr, missed))}")
        print("Those keep the colored letter tile. Fix the spelling in the database and re-run.")
    print("Reminder: show the TMDB logo and attribution notice somewhere in your app (About/Credits).")


if __name__ == "__main__":
    main()
