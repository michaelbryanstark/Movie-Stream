"""
Team Netflix - viewer-facing frontend (login, profiles, browse, search, detail, like / watched).

Setup (put this file next to team_netflix.db):
    pip install flask
    python netflix_frontend.py
Then open http://127.0.0.1:5001

Your existing netflix_app.py (admin CRUD) can keep running on port 5000.
"""
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, g, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(__file__).parent / "team_netflix.db"
app = Flask(__name__)

# Optional Jellyfin link: export JELLYFIN_URL="http://192.168.1.50:8096" to get a "Play on Jellyfin"
# button on titles imported by sync_jellyfin.py. Use your server's LAN address, never "localhost".
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "").strip().rstrip("/")
if JELLYFIN_URL and "://" not in JELLYFIN_URL:
    JELLYFIN_URL = "http://" + JELLYFIN_URL
# Jellyfin 10.9+ item page. Older servers use "/web/index.html#!/details?id={id}".
JELLYFIN_ITEM_PATH = os.environ.get(
    "JELLYFIN_ITEM_PATH", "/web/#/details?id={id}")


def load_secret_key():
    """SECRET_KEY from the environment, else a random key saved to .secret_key so sessions survive
    restarts and every worker process on a host shares the same key. Keep .secret_key out of git."""
    env = os.environ.get("SECRET_KEY", "").strip()
    if env:
        return env
    path = Path(__file__).parent / ".secret_key"
    try:
        if path.exists() and path.read_text().strip():
            return path.read_text().strip()
        key = secrets.token_hex(32)
        path.write_text(key)
        os.chmod(path, 0o600)
        return key
    except OSError:
        return secrets.token_hex(32)


app.secret_key = load_secret_key()

# Public demo mode: export DEMO_MODE=1. Shows a banner and TMDB credit, and turns off image uploads
# so visitors can't fill the disk. DEMO_LOGIN="email:password" shows a sign-in hint on the login page.
DEMO_MODE = os.environ.get(
    "DEMO_MODE", "").strip().lower() in ("1", "true", "yes")
_email, _sep, _pw = os.environ.get("DEMO_LOGIN", "").partition(":")
DEMO_LOGIN = (_email.strip(), _pw.strip()) if _sep and _email.strip() else None
UPLOADS_ENABLED = not DEMO_MODE
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  MAX_CONTENT_LENGTH=3 * 1024 * 1024)

# Fixed whitelist: table/column names are never taken from user input.
KINDS = {
    "film": {"table": "film", "actors": "film_actors", "directors": "film_directors", "col": "film_id"},
    "show": {"table": "tv_show", "actors": "tv_actors", "directors": "tv_directors", "col": "tv_show_id"},
}
FLAGS = {"liked": "is_liked", "watched": "is_watched"}

MAX_PROFILES = 5
# Pages that only need a logged-in account (no profile picked yet).
ACCOUNT_ONLY = {"profiles", "pick_profile", "logout", "manage_profiles", "new_profile",
                "edit_profile", "delete_profile"}
# Picture: blank, an http(s) URL, or a file name / path ending in an image extension.
AVATAR_DIR = Path(__file__).parent / "static" / "avatars"
AVATAR_URL = "/static/avatars/"
MAX_UPLOAD = 2 * 1024 * 1024
PIC_OK = re.compile(
    r"^(https?://\S+|/?[\w./-]+\.(png|jpe?g|gif|webp|svg))$", re.I)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_account(db):
    aid = session.get("account_id")
    if aid and db.execute("SELECT 1 FROM account WHERE id = ?", (aid,)).fetchone():
        return aid
    return None


def status_sets(db, acct):
    """{'liked': {('film', 3), ...}, 'watched': {...}} for one account."""
    out = {"liked": set(), "watched": set()}
    if not acct:
        return out
    for table, flag in FLAGS.items():
        rows = db.execute(
            f"SELECT film_id, tv_show_id FROM {table} WHERE account_id = ? AND {flag} = 1", (acct,))
        for r in rows:
            if r["film_id"] is not None:
                out[table].add(("film", r["film_id"]))
            if r["tv_show_id"] is not None:
                out[table].add(("show", r["tv_show_id"]))
    return out


def hue(text):
    return sum(ord(c) for c in (text or "?")) * 37 % 360


def current_profile(db):
    acct, pid = current_account(db), session.get("profile_id")
    if not (acct and pid):
        return None
    return db.execute(
        "SELECT profile_id, profile_name, profile_picture, is_kid_profile FROM profile "
        "WHERE profile_id = ? AND account_id = ?", (pid, acct)).fetchone()


@app.context_processor
def shared():
    db = get_db()
    return {"acct": current_account(db), "prof": current_profile(db), "hue": hue,
            "demo": DEMO_MODE, "demo_login": DEMO_LOGIN, "uploads": UPLOADS_ENABLED}


# ---------- authentication ----------
PUBLIC = {"login", "signup", "static"}
# equalises timing for unknown emails
DUMMY_HASH = generate_password_hash("not-a-real-password")
# email -> (count, first_failure_time); in-memory, resets on restart
FAILS = {}


@app.before_request
def require_login():
    if request.endpoint in PUBLIC:
        return
    db = get_db()
    if not current_account(db):
        return redirect(url_for("login"))
    if request.endpoint not in ACCOUNT_ONLY and not current_profile(db):
        return redirect(url_for("profiles"))


def too_many_failures(email):
    n, first = FAILS.get(email, (0, 0.0))
    if time.time() - first > 300:
        FAILS.pop(email, None)
        return False
    return n >= 5


def record_failure(email):
    n, first = FAILS.get(email, (0, time.time()))
    FAILS[email] = (n + 1, first)


def verify_password(db, row, pw):
    stored = row["password"] or ""
    if stored.startswith(("scrypt:", "pbkdf2:")):
        return check_password_hash(stored, pw)
    # Legacy plain-text password from the seed data: compare, then upgrade to a hash.
    if hmac.compare_digest(stored.encode(), pw.encode()):
        db.execute("UPDATE account SET password = ? WHERE id = ?",
                   (generate_password_hash(pw), row["id"]))
        db.commit()
        return True
    return False


def start_session(account_id):
    session.clear()
    session["account_id"] = account_id


@app.route("/login", methods=["GET", "POST"])
def login():
    db, error = get_db(), None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if too_many_failures(email):
            error = "Too many failed attempts. Try again in a few minutes."
        else:
            row = db.execute(
                "SELECT id, password FROM account WHERE lower(email) = ?", (email,)).fetchone()
            if row is None:
                check_password_hash(DUMMY_HASH, pw)
                ok = False
            else:
                ok = verify_password(db, row, pw)
            if ok:
                FAILS.pop(email, None)
                start_session(row["id"])
                return redirect(url_for("profiles"))
            record_failure(email)
            error = "Incorrect email or password."
    return render_template_string(PAGE, view="login", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    db, error, email = get_db(), None, ""
    plans = db.execute(
        "SELECT id, subscription_type, subscription_price FROM subscription ORDER BY id").fetchall()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        phone = request.form.get("phone", "").strip() or None
        plan = request.form.get("subscription_id", type=int)
        if "@" not in email or len(email) > 255:
            error = "Enter a valid email address."
        elif len(pw) < 8:
            error = "Password must be at least 8 characters."
        elif plan not in [p["id"] for p in plans]:
            error = "Choose a plan."
        elif db.execute("SELECT 1 FROM account WHERE lower(email) = ?", (email,)).fetchone():
            error = "That email is already registered."
        else:
            aid = db.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM account").fetchone()[0]
            pid = db.execute(
                "SELECT COALESCE(MAX(profile_id), 0) + 1 FROM profile").fetchone()[0]
            db.execute(
                "INSERT INTO account (id, email, password, phone_number, subscription_id, account_created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (aid, email, generate_password_hash(pw), phone, plan, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db.execute(
                "INSERT INTO profile (account_id, profile_id, profile_name, profile_picture, is_kid_profile) "
                "VALUES (?, ?, ?, NULL, 0)", (aid, pid, email.split("@")[0].title()))
            db.commit()
            start_session(aid)
            return redirect(url_for("profiles"))
    return render_template_string(PAGE, view="signup", error=error, email=email, plans=plans)


@app.get("/profiles")
def profiles():
    db = get_db()
    rows = db.execute(
        "SELECT profile_id, profile_name, profile_picture, is_kid_profile FROM profile "
        "WHERE account_id = ? ORDER BY profile_id", (current_account(db),)).fetchall()
    return render_template_string(PAGE, view="profiles", plist=rows)


@app.post("/profiles/<int:pid>")
def pick_profile(pid):
    db = get_db()
    if not db.execute("SELECT 1 FROM profile WHERE profile_id = ? AND account_id = ?",
                      (pid, current_account(db))).fetchone():
        abort(404)
    session["profile_id"] = pid
    return redirect(url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def home():
    db = get_db()
    q = request.args.get("q", "").strip()
    genre = request.args.get("genre", "")
    kind = request.args.get("kind", "")
    items = []
    for k, meta in KINDS.items():
        if kind and kind != k:
            continue
        sql, args = f"SELECT id, title, duration, genre, poster_url FROM {meta['table']} WHERE 1=1", [
        ]
        if q:
            sql += " AND title LIKE ?"
            args.append(f"%{q}%")
        if genre:
            sql += " AND genre = ?"
            args.append(genre)
        items += [dict(r, kind=k)
                  for r in db.execute(sql + " ORDER BY title", args)]
    genres = sorted({r[0] for m in KINDS.values() for r in db.execute(
        f"SELECT DISTINCT genre FROM {m['table']} WHERE genre IS NOT NULL AND genre != ''")})
    st = status_sets(db, current_account(db))
    return render_template_string(PAGE, view="home", items=items, genres=genres, q=q, genre=genre,
                                  kind=kind, st=st)


@app.route("/title/<kind>/<int:tid>")
def title(kind, tid):
    if kind not in KINDS:
        abort(404)
    m, db = KINDS[kind], get_db()
    item = db.execute(
        f"SELECT id, title, duration, genre, poster_url, backdrop_url, jellyfin_id FROM {m['table']} WHERE id = ?", (tid,)).fetchone()
    if item is None:
        abort(404)
    cast = [r[0] for r in db.execute(
        f"SELECT a.first_name || ' ' || a.last_name FROM actor a JOIN {m['actors']} x ON x.actor_id = a.id "
        f"WHERE x.{m['col']} = ? ORDER BY a.last_name", (tid,))]
    directors = [r[0] for r in db.execute(
        f"SELECT d.first_name || ' ' || d.last_name FROM director d JOIN {m['directors']} x ON x.director_id = d.id "
        f"WHERE x.{m['col']} = ? ORDER BY d.last_name", (tid,))]
    st = status_sets(db, current_account(db))
    play_url = None
    if JELLYFIN_URL and item["jellyfin_id"]:
        play_url = JELLYFIN_URL + \
            JELLYFIN_ITEM_PATH.replace(
                "{id}", quote(item["jellyfin_id"], safe=""))
    return render_template_string(PAGE, view="title", item=dict(item, kind=kind), cast=cast,
                                  directors=directors, st=st, play_url=play_url)


@app.post("/toggle/<what>/<kind>/<int:tid>")
def toggle(what, kind, tid):
    if what not in FLAGS or kind not in KINDS:
        abort(404)
    db = get_db()
    acct = current_account(db)
    if not acct:
        abort(403)
    col, flag = KINDS[kind]["col"], FLAGS[what]
    row = db.execute(
        f"SELECT {flag} FROM {what} WHERE account_id = ? AND {col} = ?", (acct, tid)).fetchone()
    if row is None:
        db.execute(
            f"INSERT INTO {what} (account_id, {flag}, {col}) VALUES (?, 1, ?)", (acct, tid))
    else:
        db.execute(
            f"UPDATE {what} SET {flag} = 1 - {flag} WHERE account_id = ? AND {col} = ?", (acct, tid))
    db.commit()
    return redirect(request.referrer or url_for("title", kind=kind, tid=tid))


def own_profile(db, pid):
    return db.execute(
        "SELECT profile_id, profile_name, profile_picture, is_kid_profile FROM profile "
        "WHERE profile_id = ? AND account_id = ?", (pid, current_account(db))).fetchone()


def sniff_image(data):
    """Identify the real image type from the file's first bytes (never trust the file name).
    SVG is deliberately not allowed: it can carry scripts."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_upload(data, ext):
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.{ext}"
    (AVATAR_DIR / name).write_bytes(data)
    return AVATAR_URL + name


def cleanup_picture(db, url):
    """Delete an uploaded avatar file once no profile uses it any more."""
    if not url or not url.startswith(AVATAR_URL):
        return
    name = url[len(AVATAR_URL):]
    if not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|gif|webp)", name):
        return  # only ever remove files this app generated
    if db.execute("SELECT 1 FROM profile WHERE profile_picture = ?", (url,)).fetchone():
        return
    (AVATAR_DIR / name).unlink(missing_ok=True)


@app.errorhandler(413)
def too_large(_e):
    return ("That file is too large (2 MB maximum). Go back and choose a smaller image.", 413)


def read_profile_form(form, files):
    """Returns (name, picture, kid, error, upload). upload is (bytes, ext) or None;
    the caller saves it only after everything validates."""
    name = form.get("profile_name", "").strip()
    pic = form.get("profile_picture", "").strip()
    kid = 1 if form.get("is_kid_profile") else 0
    error, upload = None, None
    if not name:
        error = "Give the profile a name."
    elif len(name) > 30:
        error = "Profile names can be at most 30 characters."
    elif pic and (len(pic) > 500 or not PIC_OK.match(pic)):
        error = "Picture must be an image URL (https://...) or left blank."
    f = files.get("picture_file") if UPLOADS_ENABLED else None
    if not error and f and f.filename:
        data = f.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            error = "That image is larger than 2 MB."
        elif sniff_image(data) is None:
            error = "Upload a PNG, JPG, GIF or WebP image."
        else:
            upload = (data, sniff_image(data))
    if form.get("remove_picture") and not upload:
        pic = ""
    return name, pic or None, kid, error, upload


@app.get("/profiles/manage")
def manage_profiles():
    db = get_db()
    rows = db.execute(
        "SELECT profile_id, profile_name, profile_picture, is_kid_profile FROM profile "
        "WHERE account_id = ? ORDER BY profile_id", (current_account(db),)).fetchall()
    return render_template_string(PAGE, view="profiles", plist=rows, manage=True,
                                  can_add=len(rows) < MAX_PROFILES)


@app.route("/profiles/new", methods=["GET", "POST"])
def new_profile():
    db, error = get_db(), None
    acct = current_account(db)
    count = db.execute(
        "SELECT COUNT(*) FROM profile WHERE account_id = ?", (acct,)).fetchone()[0]
    if count >= MAX_PROFILES:
        abort(403)
    form = {"profile_name": "", "profile_picture": "", "is_kid_profile": 0}
    if request.method == "POST":
        name, pic, kid, error, upload = read_profile_form(
            request.form, request.files)
        form = {"profile_name": name,
                "profile_picture": pic or "", "is_kid_profile": kid}
        if not error:
            if upload:
                pic = save_upload(*upload)
            pid = db.execute(
                "SELECT COALESCE(MAX(profile_id), 0) + 1 FROM profile").fetchone()[0]
            db.execute(
                "INSERT INTO profile (account_id, profile_id, profile_name, profile_picture, is_kid_profile) "
                "VALUES (?, ?, ?, ?, ?)", (acct, pid, name, pic, kid))
            db.commit()
            return redirect(url_for("manage_profiles"))
    return render_template_string(PAGE, view="profile_form", form=form, error=error, editing=None, can_delete=False)


@app.route("/profiles/<int:pid>/edit", methods=["GET", "POST"])
def edit_profile(pid):
    db, error = get_db(), None
    row = own_profile(db, pid)
    if row is None:
        abort(404)
    form = {"profile_name": row["profile_name"], "profile_picture": row["profile_picture"] or "",
            "is_kid_profile": row["is_kid_profile"]}
    if request.method == "POST":
        name, pic, kid, error, upload = read_profile_form(
            request.form, request.files)
        form = {"profile_name": name,
                "profile_picture": pic or "", "is_kid_profile": kid}
        if not error:
            if upload:
                pic = save_upload(*upload)
            db.execute("UPDATE profile SET profile_name = ?, profile_picture = ?, is_kid_profile = ? "
                       "WHERE profile_id = ? AND account_id = ?", (name, pic, kid, pid, current_account(db)))
            db.commit()
            if row["profile_picture"] != pic:
                cleanup_picture(db, row["profile_picture"])
            return redirect(url_for("manage_profiles"))
    count = db.execute("SELECT COUNT(*) FROM profile WHERE account_id = ?",
                       (current_account(db),)).fetchone()[0]
    return render_template_string(PAGE, view="profile_form", form=form, error=error, editing=row,
                                  can_delete=count > 1)


@app.post("/profiles/<int:pid>/delete")
def delete_profile(pid):
    db = get_db()
    acct = current_account(db)
    row = own_profile(db, pid)
    if row is None:
        abort(404)
    count = db.execute(
        "SELECT COUNT(*) FROM profile WHERE account_id = ?", (acct,)).fetchone()[0]
    if count <= 1:
        abort(400)  # an account always keeps at least one profile
    db.execute(
        "DELETE FROM profile WHERE profile_id = ? AND account_id = ?", (pid, acct))
    db.commit()
    cleanup_picture(db, row["profile_picture"])
    if session.get("profile_id") == pid:
        session.pop("profile_id", None)
    return redirect(url_for("manage_profiles"))


@app.get("/mylist")
def mylist():
    db = get_db()
    acct = current_account(db)
    tab = request.args.get("tab", "liked")
    if tab not in FLAGS:
        tab = "liked"
    lists = {}
    for what, flag in FLAGS.items():          # names come from the fixed whitelists above
        items = []
        for k, m in KINDS.items():
            items += [dict(r, kind=k) for r in db.execute(
                f"SELECT t.id, t.title, t.duration, t.genre, t.poster_url FROM {what} f "
                f"JOIN {m['table']} t ON t.id = f.{m['col']} "
                f"WHERE f.account_id = ? AND f.{flag} = 1", (acct,))]
        items.sort(key=lambda i: (i["title"] or "").lower())
        lists[what] = items
    return render_template_string(PAGE, view="mylist", tab=tab, items=lists[tab],
                                  counts={w: len(v) for w, v in lists.items()})


PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mikeflix</title>
<style>
:root{--bg:#141414;--card:#1f1f1f;--text:#ececec;--muted:#9b9b9b;--line:#333;--accent:#e50914}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,sans-serif}
a{color:inherit;text-decoration:none}
header{display:flex;flex-wrap:wrap;gap:1rem;align-items:center;padding:.8rem 1.5rem;
 background:linear-gradient(#000,transparent)}
.brand{color:var(--accent);font-weight:800;letter-spacing:.08em;font-size:1.3rem;margin-right:auto}
input,select,button{font:inherit;padding:.5rem .7rem;border-radius:6px;border:1px solid var(--line);
 background:var(--card);color:var(--text)}
button{cursor:pointer}button.primary{background:var(--accent);border-color:var(--accent)}
button.on{background:#fff;color:#000}
main{max-width:1200px;margin:0 auto;padding:1rem 1.5rem 3rem}
.filters{display:flex;flex-wrap:wrap;gap:.6rem;margin-bottom:1.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:1rem}
.tile{border-radius:8px;overflow:hidden;background:var(--card);transition:transform .15s}
.tile:hover{transform:scale(1.04)}
.poster{position:relative;overflow:hidden;aspect-ratio:2/3;display:flex;align-items:center;justify-content:center;font-size:3.5rem;font-weight:800}
.poster img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.hero{width:100%;max-height:260px;object-fit:cover;border-radius:10px;margin-bottom:1.2rem}
.avatar{width:22px;height:22px;border-radius:50%;object-fit:cover;vertical-align:middle;margin-right:.4rem}
.auth{max-width:380px;margin:3rem auto;background:var(--card);padding:1.5rem 2rem;border-radius:10px}
.auth label{display:block;margin:.8rem 0 .3rem;color:var(--muted)}.auth input,.auth select{width:100%}
.err{color:#ff6b6b}.who{display:flex;gap:1.5rem;flex-wrap:wrap;justify-content:center}
.who button{background:none;border:0;color:var(--text)}
.av{position:relative;overflow:hidden;width:130px;height:130px;border-radius:8px;display:flex;align-items:center;
 justify-content:center;font-size:3rem;font-weight:800;margin-bottom:.5rem}
.av img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.meta{padding:.6rem .7rem}.meta b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.muted{color:var(--muted);font-size:.85rem}.badge{font-size:.75rem;margin-right:.4rem}
.detail{display:flex;flex-wrap:wrap;gap:2rem}.detail .poster{width:260px;border-radius:10px}
.detail h1{margin:.2rem 0 .5rem}.chips{display:flex;gap:.5rem;flex-wrap:wrap;margin:.4rem 0 1rem}
.chip{background:var(--card);border:1px solid var(--line);border-radius:99px;padding:.25rem .8rem;font-size:.85rem}
.who a{display:block;text-align:center}.who button{text-align:center}
.av.add{background:var(--card);border:2px dashed var(--line);color:var(--muted)}
.tabs{display:flex;gap:.6rem;margin-bottom:1.2rem}
.tabs a{padding:.4rem 1rem;border-radius:99px;border:1px solid var(--line)}.tabs a.on{background:#fff;color:#000}
.tile form{padding:0 .7rem .7rem}.tile form button{width:100%;font-size:.85rem}
.auth input[type=checkbox]{width:auto;margin-right:.5rem}.row{display:flex;gap:.6rem;margin-top:1rem}
button.danger{color:#ff6b6b;border-color:#ff6b6b;background:none}
a.play{display:inline-block;background:var(--accent);padding:.6rem 1.2rem;border-radius:6px;font-weight:600}
.demo{background:#222;border-bottom:1px solid var(--line);padding:.5rem 1.5rem;font-size:.85rem;color:var(--muted);text-align:center}
.foot{padding:1.5rem;text-align:center;font-size:.8rem;color:var(--muted)}
</style></head><body>
<header>
  <a class="brand" href="{{ url_for('home') }}">TEAM NETFLIX</a>
  {% if acct %}
    {% if prof %}<span class="chip">{% if prof.profile_picture %}<img class="avatar" src="{{ prof.profile_picture }}" alt="" onerror="this.remove()">{% endif %}{{ prof.profile_name }}{% if prof.is_kid_profile %} (kids){% endif %}</span>
    <a class="muted" href="{{ url_for('mylist') }}">My list</a>
    <a class="muted" href="{{ url_for('edit_profile', pid=prof.profile_id) }}">Edit profile</a>
    <a class="muted" href="{{ url_for('profiles') }}">Switch profile</a>{% endif %}
    <form method="post" action="{{ url_for('logout') }}"><button>Sign out</button></form>
  {% endif %}
</header>
{% if demo %}<div class="demo">Demo site with sample data. Please don't enter real personal information or passwords.
  {% if demo_login and view in ('login', 'signup') %}Try signing in as <b>{{ demo_login[0] }}</b> / <b>{{ demo_login[1] }}</b>.{% endif %}</div>{% endif %}
<main>
{% if view == 'login' %}
  <form class="auth" method="post">
    <h2>Sign in</h2>
    {% if error %}<p class="err">{{ error }}</p>{% endif %}
    <label for="email">Email</label><input id="email" name="email" type="email" required autofocus>
    <label for="password">Password</label><input id="password" name="password" type="password" required>
    <p><button class="primary" style="width:100%">Sign in</button></p>
    <p class="muted">New here? <a style="text-decoration:underline" href="{{ url_for('signup') }}">Create an account</a></p>
  </form>
{% elif view == 'signup' %}
  <form class="auth" method="post">
    <h2>Create account</h2>
    {% if error %}<p class="err">{{ error }}</p>{% endif %}
    <label for="email">Email</label><input id="email" name="email" type="email" value="{{ email }}" required autofocus>
    <label for="password">Password (8+ characters)</label><input id="password" name="password" type="password" minlength="8" required>
    <label for="phone">Phone (optional)</label><input id="phone" name="phone" type="tel">
    <label for="subscription_id">Plan</label>
    <select id="subscription_id" name="subscription_id" required>
      {% for p in plans %}<option value="{{ p.id }}">{{ p.subscription_type|title }} - ${{ p.subscription_price }}/mo</option>{% endfor %}
    </select>
    <p><button class="primary" style="width:100%">Sign up</button></p>
    <p class="muted">Already a member? <a style="text-decoration:underline" href="{{ url_for('login') }}">Sign in</a></p>
  </form>
{% elif view == 'profiles' %}
  <h2 style="text-align:center;margin:3rem 0 2rem">{{ 'Manage profiles' if manage else "Who's watching?" }}</h2>
  <div class="who">
    {% for p in plist %}
    {% if manage %}<a href="{{ url_for('edit_profile', pid=p.profile_id) }}">
    {% else %}<form method="post" action="{{ url_for('pick_profile', pid=p.profile_id) }}"><button>{% endif %}
      <div class="av" style="background:hsl({{ hue(p.profile_name) }},45%,35%)">{% if p.profile_picture %}<img src="{{ p.profile_picture }}" alt="" onerror="this.remove()">{% endif %}{{ p.profile_name[:1] }}</div>
      {{ p.profile_name }}{% if p.is_kid_profile %} &middot; Kids{% endif %}{% if manage %}<br><span class="muted">&#9998; Edit</span>{% endif %}
    {% if manage %}</a>{% else %}</button></form>{% endif %}
    {% endfor %}
    {% if manage and can_add %}<a href="{{ url_for('new_profile') }}"><div class="av add">+</div>Add profile</a>{% endif %}
  </div>
  <p style="text-align:center;margin-top:2rem">
    {% if manage %}<a class="muted" style="text-decoration:underline" href="{{ url_for('profiles') }}">Done</a>
    {% else %}<a class="muted" style="text-decoration:underline" href="{{ url_for('manage_profiles') }}">Manage profiles</a>{% endif %}</p>
{% elif view == 'profile_form' %}
  <form class="auth" method="post" enctype="multipart/form-data">
    <h2>{{ 'Edit profile' if editing else 'Add profile' }}</h2>
    {% if error %}<p class="err">{{ error }}</p>{% endif %}
    <label for="profile_name">Name</label>
    <input id="profile_name" name="profile_name" maxlength="30" value="{{ form.profile_name }}" required autofocus>
    {% if form.profile_picture %}<div class="av" style="width:90px;height:90px;margin:1rem 0 0;background:hsl({{ hue(form.profile_name) }},45%,35%)"><img src="{{ form.profile_picture }}" alt="Current picture" onerror="this.remove()"></div>
    <label style="margin-top:.4rem"><input type="checkbox" name="remove_picture" value="1">Remove current picture</label>{% endif %}
    {% if uploads %}<label for="picture_file">Upload a picture (PNG, JPG, GIF or WebP, up to 2 MB)</label>
    <input id="picture_file" name="picture_file" type="file" accept="image/png,image/jpeg,image/gif,image/webp">{% endif %}
    <label for="profile_picture">{{ '...or paste an image URL (optional)' if uploads else 'Picture URL (optional)' }}</label>
    <input id="profile_picture" name="profile_picture" maxlength="500" value="{{ form.profile_picture }}" placeholder="https://...">
    <label><input type="checkbox" name="is_kid_profile" value="1" {{ 'checked' if form.is_kid_profile }}>Kids profile</label>
    <div class="row"><button class="primary">Save</button>
      <a href="{{ url_for('manage_profiles') }}"><button type="button">Cancel</button></a></div>
  </form>
  {% if editing and can_delete %}
  <form class="auth" style="margin-top:0" method="post" action="{{ url_for('delete_profile', pid=editing.profile_id) }}"
        onsubmit="return confirm('Delete this profile?')">
    <button class="danger" style="width:100%">Delete profile</button>
  </form>{% endif %}
{% elif view == 'mylist' %}
  <h2>My list</h2>
  <div class="tabs">
    <a class="{{ 'on' if tab == 'liked' }}" href="{{ url_for('mylist', tab='liked') }}">&#9829; Liked ({{ counts.liked }})</a>
    <a class="{{ 'on' if tab == 'watched' }}" href="{{ url_for('mylist', tab='watched') }}">&#10003; Watched ({{ counts.watched }})</a>
  </div>
  {% if items %}<div class="grid">
    {% for i in items %}
    <div class="tile">
      <a href="{{ url_for('title', kind=i.kind, tid=i.id) }}">
        <div class="poster" style="background:hsl({{ hue(i.genre) }},45%,28%)">{% if i.poster_url %}<img src="{{ i.poster_url }}" alt="" loading="lazy" onerror="this.remove()">{% endif %}{{ i.title[:1] }}</div>
        <div class="meta"><b>{{ i.title }}</b>
          <span class="muted">{{ 'Film' if i.kind == 'film' else 'Series' }}{% if i.genre %} · {{ i.genre }}{% endif %}</span></div></a>
      <form method="post" action="{{ url_for('toggle', what=tab, kind=i.kind, tid=i.id) }}"><button>Remove from {{ tab }}</button></form>
    </div>
    {% endfor %}</div>
  {% else %}<p class="muted">Nothing here yet. Open a title and use the Like or Watched button.</p>{% endif %}
{% elif view == 'home' %}
  <form class="filters" method="get">
    <input name="q" value="{{ q }}" placeholder="Search titles" type="search">
    <select name="kind"><option value="">Films &amp; shows</option>
      <option value="film" {{ 'selected' if kind=='film' }}>Films</option>
      <option value="show" {{ 'selected' if kind=='show' }}>TV shows</option></select>
    <select name="genre"><option value="">All genres</option>
      {% for g in genres %}<option {{ 'selected' if g == genre }}>{{ g }}</option>{% endfor %}</select>
    <button class="primary">Search</button>
  </form>
  {% if items %}<div class="grid">
    {% for i in items %}
    <a class="tile" href="{{ url_for('title', kind=i.kind, tid=i.id) }}">
      <div class="poster" style="background:hsl({{ hue(i.genre) }},45%,28%)">{% if i.poster_url %}<img src="{{ i.poster_url }}" alt="" loading="lazy" onerror="this.remove()">{% endif %}{{ i.title[:1] }}</div>
      <div class="meta"><b>{{ i.title }}</b>
        <span class="muted">{{ 'Film' if i.kind == 'film' else 'Series' }}{% if i.genre %} · {{ i.genre }}{% endif %}</span><br>
        {% if (i.kind, i.id) in st.liked %}<span class="badge">&#9829; Liked</span>{% endif %}
        {% if (i.kind, i.id) in st.watched %}<span class="badge">&#10003; Watched</span>{% endif %}
      </div></a>
    {% endfor %}</div>
  {% else %}<p class="muted">No titles match.</p>{% endif %}
{% else %}
  <p><a class="muted" href="{{ url_for('home') }}">&larr; Back to browse</a></p>
  {% if item.backdrop_url %}<img class="hero" src="{{ item.backdrop_url }}" alt="" onerror="this.remove()">{% endif %}
  <div class="detail">
    <div class="poster" style="background:hsl({{ hue(item.genre) }},45%,28%)">{% if item.poster_url %}<img src="{{ item.poster_url }}" alt="" loading="lazy" onerror="this.remove()">{% endif %}{{ item.title[:1] }}</div>
    <div style="flex:1;min-width:260px">
      <h1>{{ item.title }}</h1>
      <div class="muted">{{ 'Film' if item.kind == 'film' else 'TV series' }}
        {% if item.genre %} · {{ item.genre }}{% endif %}{% if item.duration %} · {{ item.duration }} min{% endif %}</div>
      <div class="chips" style="margin-top:1rem">
        {% for what, label in (('liked', 'Like'), ('watched', 'Watched')) %}
        <form method="post" action="{{ url_for('toggle', what=what, kind=item.kind, tid=item.id) }}">
          <button {{ 'disabled' if not acct }} class="{{ 'on' if (item.kind, item.id) in st[what] }}">{{ label }}</button>
        </form>{% endfor %}
      </div>
      
      {% if play_url %}<p><a class="play" href="{{ play_url }}" target="_blank" rel="noopener">&#9654; Play on Jellyfin</a></p>{% endif %}
      <h3>Cast</h3>
      <div class="chips">{% for c in cast %}<span class="chip">{{ c }}</span>{% else %}<span class="muted">No cast listed.</span>{% endfor %}</div>
      <h3>Directed by</h3>
      <div class="chips">{% for d in directors %}<span class="chip">{{ d }}</span>{% else %}<span class="muted">No director listed.</span>{% endfor %}</div>
    </div>
  </div>
{% endif %}
</main>
{% if demo %}<footer class="foot">Movie and TV images and metadata: this product uses the TMDB API but is not endorsed or certified by TMDB.</footer>{% endif %}
</body></html>
"""


def ensure_image_columns():
    """Add the image columns if the database predates them (same as add_images.sql; safe to repeat)."""
    wanted = {"film": ("poster_url", "backdrop_url"), "tv_show": ("poster_url", "backdrop_url"),
              "actor": ("photo_url",), "director": ("photo_url",)}
    wanted["film"] += ("jellyfin_id",)
    wanted["tv_show"] += ("jellyfin_id",)
    db = sqlite3.connect(DB_PATH)
    for table, cols in wanted.items():
        have = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
        for col in cols:
            if col not in have:
                try:
                    db.execute(
                        f'ALTER TABLE "{table}" ADD COLUMN "{col}" VARCHAR(500)')
                    print(f"Added column {table}.{col}")
                except sqlite3.OperationalError:  # another worker added it first
                    pass
    db.commit()
    db.close()


# Runs when a host (PythonAnywhere, gunicorn...) imports this file, not only when you run it directly.
if DB_PATH.exists():
    ensure_image_columns()


if __name__ == "__main__":
    if not DB_PATH.exists():
        raise SystemExit(
            f"Database not found: {DB_PATH}\nPut this file next to team_netflix.db.")
    print(f"Using database: {DB_PATH}")
    app.run(debug=True, port=5001)
