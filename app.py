"""CampusConnect - prototype (Phase 1)
Modules: login, announcements, events, lost-and-found.
Stack: Flask + SQLite (built-in sqlite3) + Jinja templates.
Run:  python app.py   ->  http://127.0.0.1:5000
"""
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("CAMPUSCONNECT_DB", os.path.join(BASE_DIR, "campusconnect.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me-in-production")
# Show demo accounts on the login page (turn off with DEMO_MODE=0).
app.config["DEMO_MODE"] = os.environ.get("DEMO_MODE", "1") == "1"
# Optional: only allow registration with a college email, e.g. ALLOWED_EMAIL_DOMAIN=its.edu
ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "").strip().lower()

DEPARTMENTS = {
    "CSE": "CSE",
    "CSE-AIML": "CSE (AI & ML)",
    "IT": "IT",
    "ECE": "ECE",
    "ME": "Mechanical",
    "CE": "Civil",
}
YEARS = [1, 2, 3, 4]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','club','admin')),
    department    TEXT NOT NULL DEFAULT 'ALL',
    year          INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    department  TEXT NOT NULL DEFAULT 'ALL',
    year        INTEGER NOT NULL DEFAULT 0,
    important   INTEGER NOT NULL DEFAULT 0,
    author_id   INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    venue       TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    event_time  TEXT NOT NULL,
    organiser   TEXT NOT NULL,
    creator_id  INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_registrations (
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (event_id, user_id)
);
CREATE TABLE IF NOT EXISTS lost_found (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL CHECK (kind IN ('lost','found')),
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL,
    item_date   TEXT NOT NULL,
    contact     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    user_id     INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL
);
"""


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now_str():
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def init_db():
    """Create tables and, on the very first run, load demo data."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed(db)
    db.commit()
    db.close()


def seed(db):
    """Sample data so the app never looks empty in a demo."""
    now = datetime.now()
    today = date.today()

    def ts(days=0, hours=0):
        return (now - timedelta(days=days, hours=hours)).isoformat(sep=" ", timespec="seconds")

    def d(offset):
        return (today + timedelta(days=offset)).isoformat()

    def user(name, email, pw, role, dept, year):
        cur = db.execute(
            "INSERT INTO users (name,email,password_hash,role,department,year,created_at) VALUES (?,?,?,?,?,?,?)",
            (name, email, generate_password_hash(pw), role, dept, year, ts(30)))
        return cur.lastrowid

    admin = user("Student Affairs Office", "admin@its.edu", "admin123", "admin", "ALL", 0)
    club = user("Tech Club", "club@its.edu", "club123", "club", "CSE", 3)
    yash = user("Yash", "yash@its.edu", "student123", "student", "CSE-AIML", 4)
    riya = user("Riya Sharma", "riya@its.edu", "student123", "student", "ECE", 2)
    aman = user("Aman Verma", "aman@its.edu", "student123", "student", "IT", 3)

    notices = [
        ("Exam form submission closes this Friday",
         "All students must submit the odd-semester examination form on the ERP portal before 5 PM on Friday. "
         "Forms submitted after the deadline will attract a late fee.", "ALL", 0, 1, admin, ts(0, 3)),
        ("Placement briefing for final-year students",
         "Pre-placement talk in the seminar hall on Monday, 11 AM. Bring your updated resume. "
         "Attendance is compulsory for students who registered with the training and placement cell.",
         "CSE-AIML", 4, 1, admin, ts(1)),
        ("Library timings extended during exams",
         "The central library will stay open until 9 PM on all working days until the end of the exam schedule.",
         "ALL", 0, 0, admin, ts(2)),
        ("Machine Learning lab: batch changes",
         "Batch B and Batch C will swap lab slots this week. Check the revised timetable outside Lab 3.",
         "CSE-AIML", 3, 0, admin, ts(3)),
        ("First-year orientation: bring your documents",
         "First-year students should carry original marksheets and two ID photographs for verification on Wednesday.",
         "ALL", 1, 0, admin, ts(4)),
        ("ECE circuits lab: submit the record file",
         "Second-year ECE students must submit the completed circuits lab record to the lab in-charge by Thursday.",
         "ECE", 2, 0, admin, ts(5)),
        ("Scholarship applications open",
         "The state scholarship portal is open for the new session. Collect the verification letter from the "
         "accounts office before applying.", "ALL", 0, 0, admin, ts(6)),
    ]
    db.executemany(
        "INSERT INTO announcements (title,body,department,year,important,author_id,created_at) VALUES (?,?,?,?,?,?,?)",
        notices)

    events = [
        ("CodeSprint 24-hour Hackathon",
         "Team up (up to 4 members) and build a working prototype in 24 hours. Themes: campus, health, education. "
         "Certificates for all participants and prizes for the top three teams.",
         "Computer Lab Block, Block C", d(5), "10:00", "Tech Club", club),
        ("Cultural Fest Auditions",
         "Auditions for singing, dance and stand-up. Bring your own tracks on a pen drive.",
         "Open Air Theatre", d(3), "16:00", "Cultural Committee", admin),
        ("Guest Lecture: AI in Healthcare",
         "An industry speaker explains how machine learning is used in medical imaging and diagnosis. "
         "Open to all departments, with Q&A at the end.",
         "Seminar Hall", d(9), "11:30", "CSE (AI & ML) Department", admin),
        ("Blood Donation Camp",
         "Organised with a local hospital. Carry your college ID card. Refreshments provided.",
         "Main Auditorium", d(12), "09:30", "NSS Unit", admin),
        ("Tech Talk: Git and GitHub for beginners",
         "A hands-on session on version control. Bring your laptop.",
         "Room 204, Block A", d(-4), "15:00", "Tech Club", club),
    ]
    ev_ids = []
    for e in events:
        cur = db.execute(
            "INSERT INTO events (title,description,venue,event_date,event_time,organiser,creator_id,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (*e, ts(7)))
        ev_ids.append(cur.lastrowid)
    for eid, uid in [(ev_ids[0], yash), (ev_ids[0], aman), (ev_ids[0], riya), (ev_ids[1], riya),
                     (ev_ids[2], yash), (ev_ids[2], aman), (ev_ids[3], aman)]:
        db.execute("INSERT INTO event_registrations (event_id,user_id,created_at) VALUES (?,?,?)", (eid, uid, ts(1)))

    items = [
        ("lost", "Blue steel water bottle", "Blue bottle with a small dent near the base and a sticker on the side.",
         "Central Library, reading hall", d(-1), "riya@its.edu", "open", riya, ts(1)),
        ("found", "Black leather wallet", "Found on a bench. Contains cards and some cash. Can be collected from the security desk.",
         "Canteen", d(0), "aman@its.edu", "open", aman, ts(0, 5)),
        ("lost", "Casio scientific calculator", "fx-991EX with my initials 'YK' on the back.",
         "Lab 3, Block C", d(-2), "yash@its.edu", "open", yash, ts(2)),
        ("found", "College ID card", "ID card of a second-year IT student. Handed to the security office.",
         "Block B, ground floor corridor", d(-1), "admin@its.edu", "open", admin, ts(1, 4)),
        ("lost", "Black umbrella", "Foldable umbrella with a wooden handle.",
         "Bus stop near Gate 2", d(-6), "aman@its.edu", "resolved", aman, ts(6)),
    ]
    db.executemany(
        "INSERT INTO lost_found (kind,title,description,location,item_date,contact,status,user_id,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)", items)


# ------------------------------------------------------------------ helpers
def parse_dt(value):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except (TypeError, ValueError):
            continue
    return None


@app.template_filter("day")
def f_day(value):
    dt = parse_dt(value)
    return str(dt.day) if dt else ""


@app.template_filter("mon")
def f_mon(value):
    dt = parse_dt(value)
    return dt.strftime("%b") if dt else ""


@app.template_filter("longdate")
def f_longdate(value):
    dt = parse_dt(value)
    return f"{dt.strftime('%a')}, {dt.day} {dt.strftime('%b')}" if dt else ""


@app.template_filter("clock")
def f_clock(value):
    try:
        t = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        return value
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


@app.template_filter("timeago")
def f_timeago(value):
    dt = parse_dt(value)
    if not dt:
        return ""
    secs = int((datetime.now() - dt).total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    if secs < 86400 * 7:
        days = secs // 86400
        return f"{days} day{'s' if days != 1 else ''} ago"
    return f"{dt.day} {dt.strftime('%b')}"


@app.template_filter("dept_label")
def f_dept(code):
    return "All departments" if code == "ALL" else DEPARTMENTS.get(code, code)


@app.template_filter("year_label")
def f_year(n):
    n = int(n or 0)
    return "All years" if n == 0 else {1: "1st year", 2: "2nd year", 3: "3rd year", 4: "4th year"}.get(n, f"Year {n}")


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.context_processor
def inject_globals():
    return {"DEPARTMENTS": DEPARTMENTS, "YEARS": YEARS, "today_iso": date.today().isoformat()}


@app.before_request
def load_user_and_check_csrf():
    uid = session.get("user_id")
    g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone() if uid else None
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400, "Your session expired. Go back, refresh the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Sign in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return deco


def field(name, maxlen):
    return (request.form.get(name) or "").strip()[:maxlen]


def safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def http_error(err):
    messages = {400: "That request could not be processed.", 403: "You do not have permission to do this.",
                404: "We could not find that page."}
    detail = err.description if err.code == 400 else messages[err.code]
    return render_template("error.html", code=err.code, message=detail), err.code


# ----------------------------------------------------------------- accounts
@app.route("/")
def index():
    return redirect(url_for("announcements" if g.user else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("announcements"))
    if request.method == "POST":
        name = field("name", 80)
        email = field("email", 120).lower()
        password = request.form.get("password") or ""
        dept = request.form.get("department", "")
        year = request.form.get("year", "")
        errors = []
        if len(name) < 2:
            errors.append("Enter your full name.")
        if not EMAIL_RE.match(email):
            errors.append("Enter a valid email address.")
        elif ALLOWED_EMAIL_DOMAIN and not email.endswith("@" + ALLOWED_EMAIL_DOMAIN):
            errors.append(f"Use your college email (ending in @{ALLOWED_EMAIL_DOMAIN}).")
        if len(password) < 6:
            errors.append("Choose a password with at least 6 characters.")
        if dept not in DEPARTMENTS:
            errors.append("Select your department.")
        if year not in [str(y) for y in YEARS]:
            errors.append("Select your year.")
        db = get_db()
        if not errors and db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            errors.append("An account with this email already exists. Sign in instead.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", form=request.form), 400
        cur = db.execute(
            "INSERT INTO users (name,email,password_hash,role,department,year,created_at) VALUES (?,?,?,?,?,?,?)",
            (name, email, generate_password_hash(password), "student", dept, int(year), now_str()))
        db.commit()
        session.clear()
        session["user_id"] = cur.lastrowid
        flash(f"Welcome to CampusConnect, {name.split()[0]}.", "success")
        return redirect(url_for("announcements"))
    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("announcements"))
    if request.method == "POST":
        email = field("email", 120).lower()
        password = request.form.get("password") or ""
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(safe_next(request.args.get("next")) or url_for("announcements"))
        flash("Email or password is incorrect.", "error")
        return render_template("login.html", email=email), 401
    return render_template("login.html", email="")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


# ------------------------------------------------------------ announcements
@app.route("/announcements")
@login_required
def announcements():
    user = g.user
    default_dept = "all" if user["department"] == "ALL" else user["department"]
    default_year = "all" if user["year"] == 0 else str(user["year"])
    dept = request.args.get("dept", default_dept)
    year = request.args.get("year", default_year)
    q = request.args.get("q", "").strip()[:80]
    if dept != "all" and dept not in DEPARTMENTS:
        dept = "all"
    if year != "all" and year not in [str(y) for y in YEARS]:
        year = "all"

    sql = ("SELECT a.*, u.name AS author FROM announcements a JOIN users u ON u.id = a.author_id WHERE 1=1")
    params = []
    if dept != "all":
        sql += " AND a.department IN ('ALL', ?)"
        params.append(dept)
    if year != "all":
        sql += " AND a.year IN (0, ?)"
        params.append(int(year))
    if q:
        sql += " AND (a.title LIKE ? OR a.body LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY a.important DESC, a.created_at DESC"
    rows = get_db().execute(sql, params).fetchall()
    return render_template("announcements.html", notices=rows, dept=dept, year=year, q=q,
                           filtered=(dept, year) != ("all", "all") or bool(q))


@app.route("/announcements/new", methods=["GET", "POST"])
@roles_required("admin")
def announcement_new():
    if request.method == "POST":
        title, body = field("title", 140), field("body", 2000)
        dept = request.form.get("department", "ALL")
        year = request.form.get("year", "0")
        errors = []
        if len(title) < 3:
            errors.append("Add a title (at least 3 characters).")
        if len(body) < 5:
            errors.append("Write the notice text.")
        if dept != "ALL" and dept not in DEPARTMENTS:
            errors.append("Choose who this notice is for.")
        if year not in ["0"] + [str(y) for y in YEARS]:
            errors.append("Choose the year this notice is for.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("announcement_form.html", form=request.form), 400
        db = get_db()
        db.execute("INSERT INTO announcements (title,body,department,year,important,author_id,created_at) "
                   "VALUES (?,?,?,?,?,?,?)",
                   (title, body, dept, int(year), 1 if request.form.get("important") else 0, g.user["id"], now_str()))
        db.commit()
        flash("Notice published.", "success")
        return redirect(url_for("announcements", dept="all", year="all"))
    return render_template("announcement_form.html", form={})


@app.route("/announcements/<int:notice_id>/delete", methods=["POST"])
@roles_required("admin")
def announcement_delete(notice_id):
    db = get_db()
    db.execute("DELETE FROM announcements WHERE id = ?", (notice_id,))
    db.commit()
    flash("Notice deleted.", "success")
    return redirect(url_for("announcements", dept="all", year="all"))


# ------------------------------------------------------------------- events
@app.route("/events")
@login_required
def events():
    show_past = request.args.get("show") == "past"
    op, order = ("<", "DESC") if show_past else (">=", "ASC")
    rows = get_db().execute(
        f"""SELECT e.*,
                   (SELECT COUNT(*) FROM event_registrations r WHERE r.event_id = e.id) AS reg_count,
                   EXISTS(SELECT 1 FROM event_registrations r WHERE r.event_id = e.id AND r.user_id = ?) AS registered
            FROM events e WHERE e.event_date {op} ?
            ORDER BY e.event_date {order}, e.event_time {order}""",
        (g.user["id"], date.today().isoformat())).fetchall()
    return render_template("events.html", events=rows, show_past=show_past)


@app.route("/events/new", methods=["GET", "POST"])
@roles_required("admin", "club")
def event_new():
    if request.method == "POST":
        title, desc = field("title", 140), field("description", 2000)
        venue, organiser = field("venue", 120), field("organiser", 100)
        ev_date, ev_time = request.form.get("event_date", ""), request.form.get("event_time", "")
        errors = []
        if len(title) < 3:
            errors.append("Add an event title (at least 3 characters).")
        if len(desc) < 5:
            errors.append("Describe the event.")
        if not venue:
            errors.append("Add the venue.")
        if not organiser:
            errors.append("Add the organiser (club or department).")
        try:
            if date.fromisoformat(ev_date) < date.today():
                errors.append("Pick today or a future date.")
        except ValueError:
            errors.append("Pick a valid date.")
        try:
            datetime.strptime(ev_time, "%H:%M")
        except ValueError:
            errors.append("Pick a valid start time.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("event_form.html", form=request.form), 400
        db = get_db()
        db.execute("INSERT INTO events (title,description,venue,event_date,event_time,organiser,creator_id,created_at) "
                   "VALUES (?,?,?,?,?,?,?,?)", (title, desc, venue, ev_date, ev_time, organiser, g.user["id"], now_str()))
        db.commit()
        flash("Event created. Students can now register.", "success")
        return redirect(url_for("events"))
    return render_template("event_form.html", form={"organiser": g.user["name"] if g.user["role"] == "club" else ""})


def get_event_or_404(event_id):
    ev = get_db().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if ev is None:
        abort(404)
    return ev


def can_manage_event(ev):
    return g.user["role"] == "admin" or ev["creator_id"] == g.user["id"]


@app.route("/events/<int:event_id>/register", methods=["POST"])
@login_required
def event_register(event_id):
    ev = get_event_or_404(event_id)
    db = get_db()
    exists = db.execute("SELECT 1 FROM event_registrations WHERE event_id = ? AND user_id = ?",
                        (event_id, g.user["id"])).fetchone()
    if exists:
        db.execute("DELETE FROM event_registrations WHERE event_id = ? AND user_id = ?", (event_id, g.user["id"]))
        flash(f"Registration cancelled for {ev['title']}.", "success")
    elif ev["event_date"] < date.today().isoformat():
        flash("This event has already taken place.", "error")
    else:
        db.execute("INSERT INTO event_registrations (event_id,user_id,created_at) VALUES (?,?,?)",
                   (event_id, g.user["id"], now_str()))
        flash(f"You are registered for {ev['title']}.", "success")
    db.commit()
    return redirect(url_for("events") + f"#event-{event_id}")


@app.route("/events/<int:event_id>/attendees")
@login_required
def event_attendees(event_id):
    ev = get_event_or_404(event_id)
    if not can_manage_event(ev):
        abort(403)
    people = get_db().execute(
        """SELECT u.name, u.email, u.department, u.year, r.created_at FROM event_registrations r
           JOIN users u ON u.id = r.user_id WHERE r.event_id = ? ORDER BY r.created_at""", (event_id,)).fetchall()
    return render_template("attendees.html", event=ev, people=people)


@app.route("/events/<int:event_id>/delete", methods=["POST"])
@login_required
def event_delete(event_id):
    ev = get_event_or_404(event_id)
    if not can_manage_event(ev):
        abort(403)
    db = get_db()
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()
    flash("Event deleted.", "success")
    return redirect(url_for("events"))


# -------------------------------------------------------------- lost & found
@app.route("/lost-and-found")
@login_required
def lostfound():
    kind = request.args.get("kind", "all")
    status = request.args.get("status", "open")
    q = request.args.get("q", "").strip()[:80]
    sql, params = "SELECT l.*, u.name AS poster FROM lost_found l JOIN users u ON u.id = l.user_id WHERE 1=1", []
    if kind in ("lost", "found"):
        sql += " AND l.kind = ?"
        params.append(kind)
    else:
        kind = "all"
    if status != "all":
        status = "open"
        sql += " AND l.status = 'open'"
    if q:
        sql += " AND (l.title LIKE ? OR l.description LIKE ? OR l.location LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY l.status ASC, l.created_at DESC"
    items = get_db().execute(sql, params).fetchall()
    return render_template("lostfound.html", items=items, kind=kind, status=status, q=q)


@app.route("/lost-and-found/new", methods=["GET", "POST"])
@login_required
def lostfound_new():
    if request.method == "POST":
        kind = request.form.get("kind", "")
        title, desc = field("title", 100), field("description", 600)
        location, contact = field("location", 120), field("contact", 120)
        item_date = request.form.get("item_date", "")
        errors = []
        if kind not in ("lost", "found"):
            errors.append("Choose whether you lost or found the item.")
        if len(title) < 3:
            errors.append("Name the item (at least 3 characters).")
        if not location:
            errors.append("Say where it was lost or found.")
        if not contact:
            errors.append("Add a way for people to reach you.")
        try:
            if date.fromisoformat(item_date) > date.today():
                errors.append("The date cannot be in the future.")
        except ValueError:
            errors.append("Pick a valid date.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("lostfound_form.html", form=request.form), 400
        db = get_db()
        db.execute("INSERT INTO lost_found (kind,title,description,location,item_date,contact,user_id,created_at) "
                   "VALUES (?,?,?,?,?,?,?,?)", (kind, title, desc, location, item_date, contact, g.user["id"], now_str()))
        db.commit()
        flash("Your post is live on the lost and found board.", "success")
        return redirect(url_for("lostfound"))
    return render_template("lostfound_form.html",
                           form={"kind": request.args.get("kind", "lost"), "contact": g.user["email"],
                                 "item_date": date.today().isoformat()})


def get_item_or_404(item_id):
    item = get_db().execute("SELECT * FROM lost_found WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    if item["user_id"] != g.user["id"] and g.user["role"] != "admin":
        abort(403)
    return item


@app.route("/lost-and-found/<int:item_id>/resolve", methods=["POST"])
@login_required
def lostfound_resolve(item_id):
    item = get_item_or_404(item_id)
    db = get_db()
    db.execute("UPDATE lost_found SET status = 'resolved' WHERE id = ?", (item_id,))
    db.commit()
    flash("Marked as resolved. Thanks for keeping the board up to date.", "success")
    return redirect(url_for("lostfound"))


@app.route("/lost-and-found/<int:item_id>/delete", methods=["POST"])
@login_required
def lostfound_delete(item_id):
    get_item_or_404(item_id)
    db = get_db()
    db.execute("DELETE FROM lost_found WHERE id = ?", (item_id,))
    db.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("lostfound"))


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
