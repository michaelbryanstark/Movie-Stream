#!/usr/bin/env python3
"""
Build a fresh demo database for a public site (PythonAnywhere, Render, ...) from your schema and
seed data. Your real team_netflix.db is never read or changed.

Put this file next to team_netflix.sql and seed.sql, then:
    python3 build_demo_db.py                      # writes demo/team_netflix.db
    export TMDB_TOKEN="your-tmdb-key"
    python3 populate_images.py --db demo/team_netflix.db     # real posters (run this on your own computer)

Then upload demo/team_netflix.db to your host. See DEPLOY_PYTHONANYWHERE.md.
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
IMAGE_COLUMNS = {"film": ["poster_url", "backdrop_url", "jellyfin_id"],
                 "tv_show": ["poster_url", "backdrop_url", "jellyfin_id"],
                 "actor": ["photo_url"], "director": ["photo_url"]}


def main():
    ap = argparse.ArgumentParser(description="Build a fresh demo database.")
    ap.add_argument("--out", default=str(HERE / "demo" / "team_netflix.db"),
                    help="where to write the database (default: demo/team_netflix.db)")
    ap.add_argument("--force", action="store_true", help="overwrite the output file if it exists")
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    schema_file, seed_file = HERE / "team_netflix.sql", HERE / "seed.sql"
    for f in (schema_file, seed_file):
        if not f.exists():
            sys.exit(f"Missing {f.name}. Put this script in the same folder as team_netflix.sql and seed.sql.")
    if out.exists() and not args.force:
        sys.exit(f"{out} already exists. Use --force to replace it.")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    # seed.sql is written for MySQL; drop the three MySQL-only statements, the rest is plain SQL.
    seed = re.sub(r"(?im)^\s*(CREATE\s+DATABASE|USE|SOURCE)\b[^;]*;\s*$", "", seed_file.read_text())

    db = sqlite3.connect(out)
    try:
        db.executescript(schema_file.read_text())
        db.executescript(seed)
        for table, cols in IMAGE_COLUMNS.items():
            have = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
            for col in cols:
                if col not in have:
                    db.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" VARCHAR(500)')
        db.commit()
        counts = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in ("account", "profile", "film", "tv_show", "actor", "director")}
    except sqlite3.Error as e:
        db.close()
        out.unlink(missing_ok=True)
        sys.exit(f"Could not build the database: {e}")
    db.close()

    print(f"Built {out}")
    print("  " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    print("\nNext: fill in posters on your own computer:")
    print(f'  export TMDB_TOKEN="your-tmdb-key"\n  python3 populate_images.py --db "{out}"')


if __name__ == "__main__":
    main()
