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
- **Redis caching** for read-heavy routes via the `@cached_route` decorator

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
app.py               Application factory, HTML routes, Celery wiring
config.py            Config classes, loads .env
models.py            SQLAlchemy models
init_db.py           Creates tables and seeds the default admin
cache.py             Flask-Caching setup and @cached_route decorator
celery_app.py        Celery instance and beat schedule
celery_worker.py     Worker entrypoint; task and email helper definitions
test_email.py        Manual script to fire the email tasks
routes/              auth, admin, doctor and patient API blueprints
routes/errors.py     Shared server_error() helper for 500 responses
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
# 1. Flask app  -> http://localhost:5000
python app.py

# 2. Celery worker
celery -A celery_worker.celery worker --loglevel=info --pool=solo

# 3. Celery beat (scheduler)
celery -A celery_worker.celery beat --loglevel=info
```

`--pool=solo` is required on Windows; drop it on macOS/Linux.

Default admin login is created by `init_db.py` — see `ADMIN_USERNAME` /
`ADMIN_PASSWORD` in `config.py`. Change these before deploying anywhere real.

## Scheduled tasks

| Task                                | Schedule            |
| ----------------------------------- | ------------------- |
| `send_daily_appointment_reminders`  | Daily at 08:00      |
| `send_monthly_doctor_reports`       | 1st of month, 09:00 |
| `export_patient_treatment_history_csv` | On demand        |

Timezone is `Asia/Kolkata` (set in `celery_app.py`).

To trigger the email tasks manually without waiting for the schedule:

```bash
python test_email.py
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
