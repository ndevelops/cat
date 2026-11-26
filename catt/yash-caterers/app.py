"""YASH CATERERS – mobile-first catering website with a private owner dashboard.

Run:  python app.py            (development, http://localhost:5000)
      gunicorn -w 2 app:app    (production)
"""
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("YASH_DATA_DIR", os.path.join(BASE_DIR, "instance"))
DB_PATH = os.path.join(DATA_DIR, "yash_caterers.db")
os.makedirs(DATA_DIR, exist_ok=True)

IST = timezone(timedelta(hours=5, minutes=30))

# PBKDF2-SHA256 hash of the owner's initial password. Only the hash lives in the
# code / database – the plain password is never stored or sent to the browser.
INITIAL_ADMIN_HASH = (
    "pbkdf2:sha256:600000$0mPJPm5mo5AC7Q62$"
    "ef130fe554d9371cea833267d7e71de51c0ad71f03a9f3565a68efbb7ca168c2"
)

PHONES = [
    {"number": "8828611354", "wa": "918828611354"},
    {"number": "7039675226", "wa": "917039675226"},
]
WA_MESSAGE = "Hello Yash Caterers, I would like to enquire about your catering services."

# Menu exactly as shown in the uploaded videos (no invented items).
MENU = [
    {"category": "Veg Special", "items": [
        "Mattar Paneer", "Paneer Masala", "Paneer Angara", "Veg Kolhapuri",
        "Chana Masala", "Veg Pulao", "Veg Biryani", "Paneer Biryani", "Dal",
        "Bhat", "Ghavli Bhaji", "Watana Bhaji", "Batata Bhaji", "Puri",
        "Chapati", "Bhakri"]},
    {"category": "Non-Veg Special", "items": [
        "Chicken Gravy", "Chicken Sukkha", "Mutton Gravy", "Chicken Biryani",
        "Green Chicken", "Chicken Angara", "Butter Chicken"]},
    {"category": "Starters – Veg", "items": [
        "HaraBhara Kebab", "Cheese Balls", "Spring Roll", "Aaloo Tikki"]},
    {"category": "Starters – Non Veg", "items": [
        "Chicken Pakode", "Chicken Lollypop"]},
    {"category": "Sweets", "items": [
        "Gulab Jamun", "Rabdi Jalebi", "Jalebi", "Gajar Halwa", "Basundi"]},
    {"category": "Ice-Cream (As per your order)", "items": ["Ice-Cream"]},
    {"category": "Juices", "items": [
        "Watermelon", "Pineapple", "Peru", "Chikoo",
        "Kharbuj (Muskmelon)", "Mojito"]},
]
MENU_ITEMS = {i for c in MENU for i in c["items"]}
UNITS = ["kg", "grams", "litres", "plates", "pieces", "trays", "Other"]
EVENT_TYPES = ["Wedding", "Birthday", "Engagement", "Anniversary",
               "Corporate Event", "Party", "Other"]
PEOPLE_PRESETS = [50, 100, 200, 300, 500, 750, 1000, 2000, 3000, 5000]
STATUSES = ["New", "Contacted", "Confirmed", "Completed", "Cancelled"]

app = Flask(__name__)


def _load_secret_key():
    env = os.environ.get("YASH_SECRET_KEY")
    if env:
        return env
    path = os.path.join(DATA_DIR, "secret_key")
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app.config.update(
    SECRET_KEY=_load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("YASH_SECURE_COOKIES") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=256 * 1024,
)

# --------------------------------------------------------------------------- DB
SCHEMA = """
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    address TEXT NOT NULL,
    event_date TEXT NOT NULL,
    event_time TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_type_other TEXT,
    people_count INTEGER,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'New',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enquiry_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_pk INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    position INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_enq ON enquiry_items(enquiry_pk);
CREATE INDEX IF NOT EXISTS idx_enq_date ON enquiries(event_date);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = connect()
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    if not con.execute("SELECT 1 FROM admin WHERE id = 1").fetchone():
        con.execute("INSERT INTO admin (id, password_hash) VALUES (1, ?)",
                    (INITIAL_ADMIN_HASH,))
    con.commit()
    con.close()


def db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    con = g.pop("db", None)
    if con is not None:
        con.close()


init_db()

# ------------------------------------------------------------------- security
_hits = {}


def too_many(key, limit, window):
    """Tiny in-memory rate limiter (per process)."""
    now = time.time()
    hits = [t for t in _hits.get(key, []) if now - t < window]
    _hits[key] = hits
    return len(hits) >= limit


def note_hit(key):
    _hits.setdefault(key, []).append(time.time())


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


def csrf_ok():
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    return bool(sent) and secrets.compare_digest(sent, session.get("csrf", ""))


def admin_required(api=False):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("admin"):
                if api:
                    return jsonify(error="Not authorised"), 401
                return redirect(url_for("admin_login"))
            if api and request.method not in ("GET", "HEAD") and not csrf_ok():
                return jsonify(error="Invalid request token"), 403
            return fn(*a, **kw)
        return wrapper
    return deco


@app.after_request
def headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/admin") or request.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------ customer
@app.route("/")
def index():
    return render_template(
        "index.html", phones=PHONES, wa_message=WA_MESSAGE, menu=MENU,
        units=UNITS, event_types=EVENT_TYPES, people_presets=PEOPLE_PRESETS,
        today=datetime.now(IST).strftime("%Y-%m-%d"))


def _clean(s, maxlen):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:maxlen]


def validate_enquiry(d):
    """Return (clean_dict, errors{field: message})."""
    err = {}
    out = {}

    out["name"] = _clean(d.get("name"), 100)
    if len(out["name"]) < 2:
        err["name"] = "Please enter your full name."

    digits = re.sub(r"\D", "", str(d.get("mobile") or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        err["mobile"] = "Please enter a valid 10-digit mobile number."
    out["mobile"] = digits

    out["address"] = _clean(d.get("address"), 500)
    if len(out["address"]) < 5:
        err["address"] = "Please enter the event / venue address."

    ed = str(d.get("event_date") or "")
    try:
        parsed = datetime.strptime(ed, "%Y-%m-%d").date()
        if parsed < datetime.now(IST).date():
            err["event_date"] = "Event date cannot be in the past."
    except ValueError:
        err["event_date"] = "Please choose the event date."
    out["event_date"] = ed

    et = str(d.get("event_time") or "")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", et):
        err["event_time"] = "Please choose the event timing."
    out["event_time"] = et

    out["event_type"] = str(d.get("event_type") or "")
    if out["event_type"] not in EVENT_TYPES:
        err["event_type"] = "Please select the event type."
    out["event_type_other"] = (_clean(d.get("event_type_other"), 80)
                               if out["event_type"] == "Other" else "")

    # Total people (optional, any custom number)
    people = d.get("people_count")
    out["people_count"] = None
    if people not in (None, ""):
        try:
            p = int(str(people).replace(",", "").strip())
            if not 1 <= p <= 1_000_000:
                raise ValueError
            out["people_count"] = p
        except ValueError:
            err["people_count"] = "Please enter a valid number of people."

    # Food items – each with its own quantity & unit
    items, seen = [], set()
    raw_items = d.get("items") or []
    if not isinstance(raw_items, list) or len(raw_items) > 100:
        err["items"] = "Too many food items."
        raw_items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "")
        if not name and not it.get("quantity"):
            continue  # untouched empty row
        if name not in MENU_ITEMS:
            err["items"] = "Please choose a food item from the list for every row."
            break
        if name in seen:
            err["items"] = f"“{name}” was selected more than once."
            break
        seen.add(name)
        try:
            qty = float(str(it.get("quantity")).replace(",", ""))
            if not (0 < qty <= 10_000_000) or qty != qty:
                raise ValueError
        except ValueError:
            err["items"] = f"Please enter a valid quantity for “{name}”."
            break
        unit = str(it.get("unit") or "")
        if unit == "Other":
            unit = _clean(it.get("unit_other"), 30)
            if not unit:
                err["items"] = f"Please type the unit for “{name}”."
                break
        elif unit not in UNITS:
            err["items"] = f"Please choose a unit for “{name}”."
            break
        items.append({"name": name, "quantity": qty, "unit": unit})
    out["items"] = items

    if not items and out["people_count"] is None and "items" not in err \
            and "people_count" not in err:
        err["items"] = ("Please add at least one food item with quantity "
                        "or enter the total number of people.")

    out["notes"] = str(d.get("notes") or "").strip()[:2000]
    return out, err


def new_enquiry_id(con):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    day = datetime.now(IST).strftime("%Y%m%d")
    while True:
        eid = f"YC-{day}-" + "".join(secrets.choice(alphabet) for _ in range(5))
        if not con.execute("SELECT 1 FROM enquiries WHERE enquiry_id = ?",
                           (eid,)).fetchone():
            return eid


@app.post("/api/enquiries")
def submit_enquiry():
    ip = request.remote_addr or "?"
    if too_many(f"submit:{ip}", 15, 3600):
        return jsonify(error="Too many submissions. Please call us instead."), 429
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify(error="Invalid request."), 400
    data, errors = validate_enquiry(d)
    if errors:
        return jsonify(error="Please correct the highlighted fields.",
                       fields=errors), 422

    con = db()
    eid = new_enquiry_id(con)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with con:
        cur = con.execute(
            """INSERT INTO enquiries (enquiry_id, name, mobile, address,
               event_date, event_time, event_type, event_type_other,
               people_count, notes, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'New', ?)""",
            (eid, data["name"], data["mobile"], data["address"],
             data["event_date"], data["event_time"], data["event_type"],
             data["event_type_other"], data["people_count"], data["notes"],
             created))
        con.executemany(
            "INSERT INTO enquiry_items (enquiry_pk, item_name, quantity, unit, position)"
            " VALUES (?,?,?,?,?)",
            [(cur.lastrowid, i["name"], i["quantity"], i["unit"], n)
             for n, i in enumerate(data["items"])])
    note_hit(f"submit:{ip}")
    return jsonify(ok=True, enquiry_id=eid), 201


# --------------------------------------------------------------------- admin
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_dashboard"))
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if too_many(f"login:{ip}", 5, 600):
            error = "Too many failed attempts. Please wait a few minutes."
        elif not csrf_ok():
            error = "Session expired. Please try again."
        else:
            row = db().execute("SELECT password_hash FROM admin WHERE id = 1").fetchone()
            pw = request.form.get("password", "")
            if row and check_password_hash(row["password_hash"], pw):
                session.clear()
                session["admin"] = True
                session.permanent = True
                return redirect(url_for("admin_dashboard"))
            note_hit(f"login:{ip}")
            error = "Incorrect password."
    return render_template("admin_login.html", error=error)


@app.post("/admin/logout")
def admin_logout():
    if csrf_ok():
        session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required()
def admin_dashboard():
    return render_template("admin.html", statuses=STATUSES)


def _serialise(con, rows):
    ids = [r["id"] for r in rows]
    items = {}
    if ids:
        q = ",".join("?" * len(ids))
        for it in con.execute(
                f"SELECT * FROM enquiry_items WHERE enquiry_pk IN ({q}) ORDER BY position",
                ids):
            items.setdefault(it["enquiry_pk"], []).append(
                {"name": it["item_name"], "quantity": it["quantity"], "unit": it["unit"]})
    return [{
        "enquiry_id": r["enquiry_id"], "name": r["name"], "mobile": r["mobile"],
        "address": r["address"], "event_date": r["event_date"],
        "event_time": r["event_time"], "event_type": r["event_type"],
        "event_type_other": r["event_type_other"],
        "people_count": r["people_count"], "notes": r["notes"],
        "status": r["status"], "created_at": r["created_at"],
        "items": items.get(r["id"], []),
    } for r in rows]


@app.get("/admin/api/enquiries")
@admin_required(api=True)
def admin_list():
    con = db()
    where, args = [], []
    q = (request.args.get("q") or "").strip()
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clause = "name LIKE ? ESCAPE '\\'"
        args.append(f"%{esc}%")
        digits = re.sub(r"\D", "", q)
        if digits:
            clause += " OR mobile LIKE ?"
            args.append(f"%{digits}%")
        where.append(f"({clause})")
    d = (request.args.get("date") or "").strip()
    if d:
        where.append("event_date = ?")
        args.append(d)
    sql = "SELECT * FROM enquiries"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    rows = con.execute(sql, args).fetchall()
    counts = {s: 0 for s in STATUSES}
    for r in con.execute("SELECT status, COUNT(*) c FROM enquiries GROUP BY status"):
        counts[r["status"]] = r["c"]
    return jsonify(enquiries=_serialise(con, rows),
                   stats={"total": sum(counts.values()), **counts})


@app.patch("/admin/api/enquiries/<enquiry_id>/status")
@admin_required(api=True)
def admin_status(enquiry_id):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in STATUSES:
        return jsonify(error="Invalid status"), 400
    con = db()
    with con:
        cur = con.execute("UPDATE enquiries SET status = ? WHERE enquiry_id = ?",
                          (status, enquiry_id))
    if cur.rowcount == 0:
        return jsonify(error="Enquiry not found"), 404
    return jsonify(ok=True, status=status)


@app.delete("/admin/api/enquiries/<enquiry_id>")
@admin_required(api=True)
def admin_delete(enquiry_id):
    con = db()
    with con:
        cur = con.execute("DELETE FROM enquiries WHERE enquiry_id = ?", (enquiry_id,))
    if cur.rowcount == 0:
        return jsonify(error="Enquiry not found"), 404
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
