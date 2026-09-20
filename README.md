# CampusConnect (prototype, phase 1)

One place for college announcements, events and lost-and-found.
Built with **Flask + SQLite + Jinja templates + plain CSS/JS**.

## Run it

```bash
cd campusconnect
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The first run creates `campusconnect.db` and loads sample data.
To start fresh, stop the app, delete `campusconnect.db`, and run it again.

## Demo accounts (also shown on the login page)

| Role    | Email          | Password   | Can do |
|---------|----------------|------------|--------|
| Student | yash@its.edu   | student123 | view notices, register for events, post lost/found |
| Club    | club@its.edu   | club123    | everything a student can, plus create events and see attendees |
| Admin   | admin@its.edu  | admin123   | post/delete notices, create/delete events, moderate lost & found |

New students can register themselves (department and year decide which notices they see first).

## Project structure

```
app.py               all routes, database schema, sample data, helpers
templates/           Jinja HTML pages (base.html is the shared layout)
static/style.css     styling (navy + coral, mobile-first)
static/app.js        small enhancements (auto-apply filters, confirm delete)
requirements.txt     Flask
campusconnect.db     created automatically on first run
```

## How the three modules work

- **Announcements**: admin posts a notice for a department and year (or everyone).
  Students see notices for their own department and year by default and can change the filters or search. Important notices are pinned to the top.
- **Events**: admin/club creates an event; students tap Register (tap again to cancel). The creator can open the attendee list.
- **Lost & found**: any student posts a lost or found item; the poster (or admin) marks it as found/returned or deletes it.

## Database tables

`users`, `announcements`, `events`, `event_registrations`, `lost_found` (see `SCHEMA` in `app.py`).

## Security basics included

Passwords are hashed (Werkzeug), every form has a CSRF token, all SQL uses parameters (no string-built queries), and role checks guard admin/club actions.

## Optional settings (environment variables)

- `SECRET_KEY`: set a long random value when deploying.
- `DEMO_MODE=0`: hide the demo accounts box on the login page.
- `ALLOWED_EMAIL_DOMAIN=its.edu`: only allow registration with that email domain.
- `FLASK_DEBUG=0`: turn off debug mode.

## Not in this prototype (planned)

Notes sharing, clubs directory, anonymous issue reporting, emergency contacts, email verification, event reminders.
