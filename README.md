Streaming Site Practice

A Netflix-style web app for browsing a personal movie and TV collection. It has sign-in, multiple profiles per account, search and filters, likes and watched lists, and a one-click Play on Jellyfin button for titles imported from your own Jellyfin server.
Requires a Jellyfin account to login and watch on the local server, can be used as a template to create your own app/server.

Built with Flask and SQLite. No JavaScript build step, one Python dependency.

Features
Accounts: sign up and sign in, with hashed passwords, a login rate limit (5 failed attempts per 5 minutes per email), and automatic upgrade of any plain-text seed passwords on first login.
Profiles: up to 5 per account. Add, edit, and delete profiles; set a name and a kids flag; set a picture by uploading an image (PNG, JPG, GIF or WebP, up to 2 MB) or pasting a URL.
Browse: search by title, filter by films or shows and by genre, with poster tiles that fall back to a colored letter tile when there's no image.
Title pages: backdrop, poster, runtime, genre, cast, and directors.
Likes and watched: toggle either on any title. A My list page shows both lists with a Remove button.
Jellyfin integration: import your library (titles, posters, cast) and play titles on your server.
Project layout
your-project/
├── netflix_frontend.py     The web app (run this)
├── sync_jellyfin.py        Imports your Jellyfin library into the database
├── populate_images.py      Optional: fills posters and photos from TMDB
├── team_netflix.db         SQLite database (the app reads and writes this)
├── team_netflix.sql        Database schema
├── seed.sql                Demo data (MySQL syntax, see Database below)
├── add_images.sql          Adds image columns (the app also does this automatically)
├── seed_images.sql         Placeholder images for the demo data
└── static/avatars/         Uploaded profile pictures (created automatically)
Quick start

Requires Python 3 and Flask.

pip install flask
python3 netflix_frontend.py

Open http://127.0.0.1:5001. Keep team_netflix.db in the same folder as the script. On startup the app adds any missing image or Jellyfin columns to the database, so older databases keep working.

Connecting a Jellyfin server
In Jellyfin, open Dashboard → API Keys, click +, name it, and copy the key.
Set two environment variables in your terminal, using your server's LAN address (not localhost):
   export JELLYFIN_URL="http://192.168.1.50:8096"
   export JELLYFIN_API_KEY="paste-key-here"
Preview, then import:
   python3 sync_jellyfin.py --dry-run
   python3 sync_jellyfin.py
Start the app with JELLYFIN_URL still set. Open any imported title and use the red Play on Jellyfin button above the cast list.

export only applies to the terminal window you typed it in. Re-enter it in new windows, or put the lines in ~/.bashrc or a .env file you load yourself (the scripts don't read .env on their own).

What the sync does
Movies go into film and series into tv_show, with title, runtime in minutes, first genre, poster, and backdrop. Series use their first episode's runtime.
Cast (top 10 actors) and directors are imported and reused if they already exist.
Each item's Jellyfin ID is stored in jellyfin_id. That is what powers the Play button.
A Jellyfin title whose name matches an existing database title is linked to that row, so its likes and watched marks are kept.
It is safe to re-run after adding movies. Nothing is duplicated, and Jellyfin is the source of truth for the imported fields, so a re-run overwrites hand edits to them.
The first run saves a backup next to the database (team_netflix.db.bak-…).
Sync options
Option	Effect
--dry-run	Show what would happen and save nothing
--no-people	Skip cast and director import
--prune	After syncing, delete database titles that are not in Jellyfin (such as the demo data), along with their likes and watched marks. Asks for confirmation, and refuses to run if Jellyfin returns no titles at all
--yes	Skip the --prune confirmation prompt
Tips for a clean library
Jellyfin must see TV episodes as a series. Keep them in a TV Shows library with a Show Name/Season 01/ folder layout, or they will import as individual movies.
Files with raw names (for example SOMETHING_t00.mkv) have no metadata. Rename them like Movie Name (2006).mkv, or use Identify on the item in Jellyfin.
Optional: posters from TMDB

If your titles don't have images (or you aren't using Jellyfin), populate_images.py fills posters, backdrops, and optionally cast photos from The Movie Database.

export TMDB_TOKEN="your-tmdb-key"
python3 populate_images.py --dry-run
python3 populate_images.py

Options: --people also fills actor and director photos, --force overwrites images that are already set. Without --force it only fills blank entries and demo placeholders, so it won't replace Jellyfin posters.

Configuration
Variable	Used by	Purpose
JELLYFIN_URL	frontend, sync	Your Jellyfin address, for example http://192.168.1.50:8096
JELLYFIN_API_KEY	sync	Jellyfin API key
JELLYFIN_ITEM_PATH	frontend	Item page path. Default /web/#/details?id={id} (Jellyfin 10.9 and later). Older servers: /web/index.html#!/details?id={id}
TMDB_TOKEN	populate_images	TMDB API key or read access token
SECRET_KEY	frontend	Keeps users signed in across app restarts. Random each start if unset
Database

The schema is in team_netflix.sql: account, subscription, profile, film, tv_show, actor, director, watched, liked, and the link tables film_actors, tv_actors, film_directors, tv_directors. Image and Jellyfin columns (poster_url, backdrop_url, photo_url, jellyfin_id) are added by the app and scripts as needed.

team_netflix.db is SQLite. seed.sql is written for MySQL (it uses CREATE DATABASE, USE, and SOURCE), so remove those lines if you load it into SQLite.

Notes and limitations
Likes and watched are per account, not per profile, because those tables only store account_id. All profiles on an account share them. Jellyfin's own watch history is separate and is not synced.
Local use only as shipped. The app runs on port 5001 with Flask's debug mode on. Before exposing it to other devices or the internet, turn debug off, serve it with a production server, and set SECRET_KEY.
Uploaded pictures are stored on local disk in static/avatars/, which won't persist on hosts with temporary storage.
The login rate limiter lives in memory and resets when the app restarts.
Troubleshooting
No Play button: the button only appears on a title's detail page, and only if JELLYFIN_URL was set when the app started and the title has a jellyfin_id. Check with sqlite3 team_netflix.db "SELECT title, jellyfin_id FROM film WHERE jellyfin_id IS NOT NULL LIMIT 5;". No rows means the real sync (not --dry-run) hasn't run.
Posters show only a colored letter: the device you're browsing from can't reach the Jellyfin address. Use the server's LAN IP, not localhost.
Sync can't connect: check that the server is running and port 8096 is reachable. On Fedora: sudo firewall-cmd --add-port=8096/tcp --permanent && sudo firewall-cmd --reload.
Play opens a page that doesn't show the title: set JELLYFIN_ITEM_PATH for your server version (see Configuration).
Credits

Movie and TV metadata and images, when filled with populate_images.py, come from TMDB. This product uses the TMDB API but is not endorsed or certified by TMDB. Display the TMDB logo and this notice in your app's About or Credits section if you use that data.

Library data and playback come from your own Jellyfin server.

