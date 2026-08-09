"""The single Celery instance, shared by the web process and the worker.

Import ``celery`` from this module - never construct another instance. Broker and
backend come from ``config.Config`` so ``REDIS_URL`` in ``.env`` is honoured.

The web process dispatches work by task *name* (``celery.send_task``) and so never
imports ``celery_worker``; the worker imports this module to register its tasks
against the same instance. That keeps a single source of truth for the beat schedule.
"""

from celery import Celery
from celery.schedules import crontab

from config import Config

celery = Celery(
    'hospital_tasks',
    broker=Config.broker_url,
    backend=Config.result_backend,
)

celery.conf.update(
    task_serializer=Config.task_serializer,
    accept_content=Config.accept_content,
    result_serializer=Config.result_serializer,
    timezone=Config.timezone,
    enable_utc=Config.enable_utc,
    broker_connection_retry_on_startup=True,
)

# Periodic jobs. Task names must match the name= given to @celery.task in
# celery_worker.py.
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
