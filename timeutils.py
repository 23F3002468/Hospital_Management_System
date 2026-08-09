"""Time helpers for the hospital's local clock.

The app deliberately runs two clocks, and mixing them is what caused the bugs this
module exists to prevent:

* **Hospital wall clock** - ``hospital_now()`` / ``hospital_today()``. Use for anything
  a person at the hospital would call "today" or "now": which appointments are today,
  whether a slot is in the past, how old a patient is. The zone comes from
  ``Config.timezone`` (``Asia/Kolkata``), the same setting Celery beat schedules against,
  so an 08:00 reminder job and the "today" it queries for agree.

* **UTC** - ``datetime.utcnow()``, left in place for audit columns (``created_at``,
  ``updated_at``, ``cancelled_at``, ``registration_timestamp``). Those record when a row
  was written and should not move with the hospital's location.

Both return *naive* datetimes because every ``DateTime`` column in ``models.py`` is
naive; returning aware ones would raise on comparison with values loaded from the DB.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from config import Config

HOSPITAL_TZ = ZoneInfo(Config.timezone)


def hospital_now():
    """Current wall-clock time at the hospital, as a naive datetime.

    Naive so it compares cleanly against the naive values stored in the database -
    ``Appointment.appointment_date`` and ``appointment_time`` are already local
    wall-clock values, since that is what a patient picked in the booking form.
    """
    return datetime.now(HOSPITAL_TZ).replace(tzinfo=None)


def hospital_today():
    """Today's date at the hospital.

    This is the one that matters: ``datetime.utcnow().date()`` is a day behind for the
    5.5 hours between 18:30 and midnight IST.
    """
    return datetime.now(HOSPITAL_TZ).date()
