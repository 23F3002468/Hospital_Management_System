# Hospital Management System

A Flask-based hospital management application with role-based dashboards for
admins, doctors and patients. Redis backs both the cache and the Celery queue
that handles scheduled reminders, monthly reports and CSV exports.

## Features

- **Session-based auth** with Flask-Login and three roles: admin, doctor, patient
- **Admin dashboard** — manage departments, doctors, patients and appointments
- **Doctor dashboard** — view the day's appointments and record treatments
- **Patient dashboard** — book appointments and browse treatment history
- **Background jobs (Celery + Redis)**
  - Daily appointment reminders, emailed at 08:00
  - Monthly doctor activity reports on the 1st at 09:00
  - On-demand CSV export of a patient's treatment history
- **Redis caching** of the department list, invalidated whenever an admin adds,
  edits, deactivates or deletes a doctor

## Tech stack

| Layer      | Choice                                        |
| ---------- | --------------------------------------------- |
| Backend    | Flask 3, Flask-SQLAlchemy, Flask-Login         |
| Frontend   | Jinja templates with Vue.js served from `static/` |
| Database   | SQLite (`hospital.db`)                         |
| Jobs/Cache | Celery 5, Redis                                |
| Email      | Flask-Mail via Mailtrap sandbox                |

## Project layout

```
app.py               Application factory and HTML routes
config.py            Config classes, loads .env
models.py            SQLAlchemy models
init_db.py           Creates tables and seeds the admin, departments and demo doctors
demo_data.py         The demo doctors and their availability; runnable standalone
cache.py             The Flask-Caching instance, cache keys and invalidation
celery_app.py        The Celery instance and beat schedule
celery_worker.py     Worker entrypoint; task and email helper definitions
timeutils.py         Hospital-local date/time helpers
send_test_email.py   Manual script to fire the email tasks (not a pytest test)
routes/              auth, admin, doctor and patient API blueprints
routes/errors.py     Shared server_error() helper for 500 responses
tests/               pytest suite; conftest.py holds the fixtures
templates/           Jinja/Vue pages
static/              CSS and JS assets
exports/             Generated CSV exports (gitignored)
```

## Setup

**Prerequisites:** Python 3.12+ and a running Redis server.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

`MAIL_USERNAME` and `MAIL_PASSWORD` come from your
[Mailtrap](https://mailtrap.io/inboxes) sandbox inbox. `.env` is gitignored —
never commit real credentials.

Initialise the database:

```bash
python init_db.py
```

## Running

Three processes, each in its own terminal:

```bash
# 1. Flask app  -> http://127.0.0.1:5000
python app.py

# 2. Celery worker
celery -A celery_worker.celery worker --loglevel=info --pool=solo

# 3. Celery beat (scheduler)
celery -A celery_worker.celery beat --loglevel=info
```

`--pool=solo` is required on Windows; drop it on macOS/Linux.

`python app.py` starts Flask's **development** server: debug mode on, bound to
localhost. To reach it from another device on your network, set
`FLASK_RUN_HOST=0.0.0.0` — but only on a network you trust, because the debugger
that comes with debug mode executes Python on the server.

## Deploying

Do **not** deploy with `python app.py`. It refuses to start when
`FLASK_ENV=production`, and for good reason: the development server is
single-threaded and ships an interactive debugger. Use a real WSGI server:

```bash
# Windows
waitress-serve --host=0.0.0.0 --port=8000 app:app

# Linux / macOS
gunicorn --bind 0.0.0.0:8000 app:app
```

Set these in the environment first:

```bash
FLASK_ENV=production
SECRET_KEY=<64 hex chars, e.g. python -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=<your database>
REDIS_URL=<your redis>
TRUST_PROXY_HOPS=1        # only if a reverse proxy sits in front; see below
CORS_ORIGINS=             # leave empty unless the frontend is on another domain
```

`FLASK_ENV=production` loads `ProductionConfig`, which turns debug off and marks
the session and "remember me" cookies `Secure`, `HttpOnly` and `SameSite=Lax`.

**TLS is not optional.** `Secure` means the browser will not send the login
cookie over plain `http://`, so an HTTPS-less deployment is one where nobody can
log in. That is the intended failure — the alternative is a session cookie
travelling in clear text.

**Behind a reverse proxy**, set `TRUST_PROXY_HOPS` to the number of proxies in
front of the app. Without it Flask sees the proxy's address and `http://`, so
redirects come out wrong. With it, `X-Forwarded-For` / `-Proto` / `-Host` are
honoured. Leave it unset when nothing is in front — those headers can be spoofed
by anyone talking to the app directly.

**CORS is off by default.** The Vue pages are served by this same app and call
relative paths, so every request is same-origin and needs no CORS headers. If you
move the frontend to its own domain, set `CORS_ORIGINS` to a comma-separated list
of the exact origins allowed — never a wildcard. Credentials stay off, so a
cross-origin frontend cannot send the session cookie; making that work needs CSRF
tokens and `SameSite=None`, neither of which this app has yet.

## Demo logins

`init_db.py` seeds enough data to explore the app straight away — no need to log
in as admin and create a doctor first.

| Role | Username | Password |
| --- | --- | --- |
| Admin | `admin` | `admin123` |
| Doctor | `dr.otho`, `dr.cardia`, `dr.neura`, … | `doctor123` |
| Patient | register your own from the landing page | — |

Twelve doctors cover all ten departments, each with morning and afternoon
availability for the next seven days, so a freshly registered patient can browse
departments and book an appointment immediately. Their names follow the
department — Dr. Otho in Orthopedics, Dr. Cardia in Cardiology — so it is obvious
who is who while clicking around. The full list is in `demo_data.py`.

If a demo database has been sitting unused for more than a week its availability
will have aged out. Top it back up without touching anything else:

```bash
python demo_data.py
```

It is idempotent — existing doctors are left alone and only missing availability
is added.

Change these credentials before deploying anywhere real; they exist so the
project can be reviewed in one click.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

No Redis and no database server needed — `TestingConfig` runs on an in-memory
SQLite and an in-process cache, and every test builds its own app with
`create_app('testing')`. The suite covers the API end to end through
`test_client()`: authentication and role guards, booking rules, admin doctor
management, the department cache, and the model properties behind the
dashboards.

## Scheduled tasks

| Task                                | Schedule            |
| ----------------------------------- | ------------------- |
| `send_daily_appointment_reminders`  | Daily at 08:00      |
| `send_monthly_doctor_reports`       | 1st of month, 09:00 |
| `export_patient_treatment_history_csv` | On demand        |

Timezone is `Asia/Kolkata`, set once as `timezone` in `config.py`. Both the beat
schedule and the app's own date logic read it, so "today" means the same thing to
the scheduler and to a doctor's dashboard. `timeutils.hospital_today()` /
`hospital_now()` return that local clock; `created_at`-style audit columns stay in UTC.

To trigger the email tasks manually without waiting for the schedule:

```bash
python send_test_email.py
```

Sent mail lands in your Mailtrap inbox rather than real inboxes.

## API endpoints

| Prefix         | Purpose                       |
| -------------- | ----------------------------- |
| `/api/health`  | Health check                  |
| `/api/auth`    | Login, logout, registration   |
| `/api/admin`   | Admin operations              |
| `/api/doctor`  | Doctor operations             |
| `/api/patient` | Patient operations            |
