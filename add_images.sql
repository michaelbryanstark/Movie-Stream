-- Migration: add image support to team_netflix.db
-- Run ONCE:  sqlite3 team_netflix.db < add_images.sql
-- (SQLite has no "ADD COLUMN IF NOT EXISTS", so a second run errors harmlessly.)

-- Titles: a portrait poster for the browse grid, a wide backdrop for the detail page.
-- Store a URL (or a relative path like /static/posters/dune.jpg), never the image bytes.
ALTER TABLE film    ADD COLUMN poster_url   VARCHAR(500);
ALTER TABLE film    ADD COLUMN backdrop_url VARCHAR(500);
ALTER TABLE tv_show ADD COLUMN poster_url   VARCHAR(500);
ALTER TABLE tv_show ADD COLUMN backdrop_url VARCHAR(500);

-- Optional: headshots for the cast and directors.
ALTER TABLE actor    ADD COLUMN photo_url VARCHAR(500);
ALTER TABLE director ADD COLUMN photo_url VARCHAR(500);

-- profile.profile_picture already exists in your schema; nothing to add there.
