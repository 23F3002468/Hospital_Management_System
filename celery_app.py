"""The single Celery instance, shared by the web process and the worker.

Import ``celery`` from this module - never construct another instance. Broker and
backend come from ``config.Config`` so ``REDIS_URL`` in ``.env`` is honoured.

The web process dispatches work by task *name* (``celery.send_task``) and so never
imports ``celery_worker``; the worker imports this module to register its tasks
against the same instance. That keeps a single source of truth for the beat schedule.
"""

from celery import Celery
from celery.schedules import crontab

# Create Celery instance
celery = Celery(
    'hospital_tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Configure Celery
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    broker_connection_retry_on_startup=True,  # Fix the warning
)

# Configure Celery beat schedule
celery.conf.beat_schedule = {
    'send-daily-reminders': {
        'task': 'tasks.send_daily_appointment_reminders',
        'schedule': crontab(hour=8, minute=0),  # Every day at 8:00 AM
    },
    'send-monthly-reports': {
        'task': 'tasks.send_monthly_doctor_reports',
        'schedule': crontab(day_of_month=1, hour=9, minute=0),  # 1st of month at 9 AM
    },
}
