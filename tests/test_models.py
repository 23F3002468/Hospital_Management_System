"""Model properties and the two clocks.

Regression cover for:
  #9  the count properties were rewritten from Python loops into aggregates -
      these pin the values so a future rewrite cannot drift
  #11 "today" means today at the hospital (Asia/Kolkata), not in UTC
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from conftest import add_appointment, make_doctor, make_patient
from config import Config
from models import Appointment, Department, Doctor, DoctorAvailability, Patient, db
from timeutils import HOSPITAL_TZ, hospital_now, hospital_today


# ---------------------------------------------------------------------------
# Department counts
# ---------------------------------------------------------------------------

def test_doctors_count_ignores_inactive_doctors(app, seed):
    with app.app_context():
        cardiology = db.session.get(Department, seed.cardiology_id)
        assert cardiology.doctors_count == 2

        db.session.get(Doctor, seed.doc1_id).user.is_active = False
        db.session.commit()
        assert cardiology.doctors_count == 1


def test_doctors_count_is_zero_for_an_empty_department(app, seed):
    with app.app_context():
        # Neurology holds only the inactive doc3.
        assert db.session.get(Department, seed.neurology_id).doctors_count == 0


def test_available_doctors_count_only_counts_slots_for_today(app, seed):
    with app.app_context():
        cardiology = db.session.get(Department, seed.cardiology_id)
        # The seeded slots are two days out.
        assert cardiology.available_doctors_count == 0

        db.session.add(DoctorAvailability(
            doctor_id=seed.doc1_id, date=hospital_today(),
            start_time=time(9, 0), end_time=time(17, 0), is_available=True))
        db.session.commit()
        assert cardiology.available_doctors_count == 1


def test_available_doctors_count_does_not_double_count_multiple_slots(app, seed):
    with app.app_context():
        today = hospital_today()
        db.session.add_all([
            DoctorAvailability(doctor_id=seed.doc1_id, date=today,
                               start_time=time(9, 0), end_time=time(12, 0), is_available=True),
            DoctorAvailability(doctor_id=seed.doc1_id, date=today,
                               start_time=time(14, 0), end_time=time(17, 0), is_available=True),
        ])
        db.session.commit()
        assert db.session.get(Department, seed.cardiology_id).available_doctors_count == 1


def test_available_doctors_count_skips_unavailable_slots(app, seed):
    with app.app_context():
        db.session.add(DoctorAvailability(
            doctor_id=seed.doc1_id, date=hospital_today(),
            start_time=time(9, 0), end_time=time(17, 0), is_available=False))
        db.session.commit()
        assert db.session.get(Department, seed.cardiology_id).available_doctors_count == 0


# ---------------------------------------------------------------------------
# Doctor counts
# ---------------------------------------------------------------------------

def test_doctor_appointment_counts(app, seed):
    with app.app_context():
        today = hospital_today()
        add_appointment(seed.pat1_id, seed.doc1_id, today + timedelta(days=1), time(9, 0))
        add_appointment(seed.pat2_id, seed.doc1_id, today + timedelta(days=2), time(9, 0))
        add_appointment(seed.pat1_id, seed.doc1_id, today - timedelta(days=1), time(9, 0),
                        status='Completed')
        add_appointment(seed.pat2_id, seed.doc1_id, today - timedelta(days=2), time(9, 0),
                        status='Completed')
        add_appointment(seed.pat1_id, seed.doc1_id, today + timedelta(days=3), time(9, 0),
                        status='Cancelled')
        db.session.commit()

        doctor = db.session.get(Doctor, seed.doc1_id)
        assert doctor.upcoming_appointments_count == 2   # cancelled one excluded
        assert doctor.completed_appointments_count == 2


def test_doctor_counts_are_scoped_to_that_doctor(app, seed):
    with app.app_context():
        add_appointment(seed.pat1_id, seed.doc2_id, hospital_today() + timedelta(days=1),
                        time(9, 0))
        db.session.commit()
        assert db.session.get(Doctor, seed.doc1_id).upcoming_appointments_count == 0
        assert db.session.get(Doctor, seed.doc2_id).upcoming_appointments_count == 1


def test_todays_appointments_count_as_upcoming(app, seed):
    """The boundary that broke at 18:30 IST under the old UTC logic."""
    with app.app_context():
        add_appointment(seed.pat1_id, seed.doc1_id, hospital_today(), time(23, 0))
        db.session.commit()
        assert db.session.get(Doctor, seed.doc1_id).upcoming_appointments_count == 1


def test_is_available_on_date(app, seed):
    with app.app_context():
        doctor = db.session.get(Doctor, seed.doc1_id)
        assert doctor.is_available_on_date(seed.slot_date) is True
        assert doctor.is_available_on_date(seed.slot_date + timedelta(days=1)) is False


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------

def test_patient_age_is_computed_from_the_hospital_date(app, seed):
    with app.app_context():
        patient = db.session.get(Patient, seed.pat1_id)
        today = hospital_today()
        born = date(1990, 6, 15)
        expected = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        assert patient.age == expected


def test_patient_age_is_none_without_a_date_of_birth(app, seed):
    with app.app_context():
        assert db.session.get(Patient, seed.pat2_id).age is None


def test_patient_age_the_day_before_a_birthday(app, seed):
    """Off-by-one around birthdays was one of the #11 symptoms."""
    with app.app_context():
        today = hospital_today()
        patient = make_patient('birthday_kid',
                               date_of_birth=date(2000, today.month, today.day))
        db.session.commit()
        assert patient.age == today.year - 2000


def test_upcoming_and_history_split_correctly(app, seed):
    with app.app_context():
        today = hospital_today()
        add_appointment(seed.pat1_id, seed.doc1_id, today + timedelta(days=1), time(9, 0))
        add_appointment(seed.pat1_id, seed.doc2_id, today + timedelta(days=2), time(9, 0))
        add_appointment(seed.pat1_id, seed.doc1_id, today - timedelta(days=5), time(9, 0),
                        status='Completed')
        add_appointment(seed.pat1_id, seed.doc1_id, today + timedelta(days=4), time(9, 0),
                        status='Cancelled')
        db.session.commit()

        patient = db.session.get(Patient, seed.pat1_id)
        assert len(patient.upcoming_appointments) == 2
        # Past appointments plus anything completed or cancelled.
        assert len(patient.appointment_history) == 2


def test_upcoming_appointments_come_back_in_chronological_order(app, seed):
    with app.app_context():
        today = hospital_today()
        add_appointment(seed.pat1_id, seed.doc1_id, today + timedelta(days=3), time(9, 0))
        add_appointment(seed.pat1_id, seed.doc2_id, today + timedelta(days=1), time(9, 0))
        db.session.commit()

        dates = [a.appointment_date for a in db.session.get(Patient, seed.pat1_id).upcoming_appointments]
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------

def test_is_upcoming_and_can_be_cancelled(app, seed):
    with app.app_context():
        future = add_appointment(seed.pat1_id, seed.doc1_id,
                                 hospital_today() + timedelta(days=1), time(9, 0))
        past = add_appointment(seed.pat1_id, seed.doc2_id,
                               hospital_today() - timedelta(days=1), time(9, 0))
        db.session.commit()

        assert future.is_upcoming is True
        assert future.can_be_cancelled is True
        assert past.is_upcoming is False
        assert past.can_be_cancelled is False


def test_a_cancelled_appointment_cannot_be_cancelled_again(app, seed):
    with app.app_context():
        appointment = add_appointment(seed.pat1_id, seed.doc1_id,
                                      hospital_today() + timedelta(days=1), time(9, 0),
                                      status='Cancelled')
        db.session.commit()
        assert appointment.can_be_cancelled is False


# ---------------------------------------------------------------------------
# The two clocks - issue #11
# ---------------------------------------------------------------------------

def test_the_hospital_timezone_comes_from_the_celery_config():
    """If these drift, the 08:00 reminder job queries the wrong day."""
    assert str(HOSPITAL_TZ) == Config.timezone


def test_hospital_now_is_naive():
    """Every DateTime column is naive; an aware value would raise on comparison."""
    assert hospital_now().tzinfo is None


def test_hospital_today_follows_the_hospital_clock():
    assert hospital_today() == datetime.now(ZoneInfo(Config.timezone)).date()


def test_hospital_now_is_offset_from_utc_by_the_zone():
    """Asia/Kolkata is UTC+5:30, so the two clocks are genuinely different."""
    delta = hospital_now() - datetime.utcnow()
    assert timedelta(hours=5, minutes=25) < delta < timedelta(hours=5, minutes=35)


def test_audit_columns_stay_on_utc(app, seed):
    """Deliberate split: storage in UTC, display logic in hospital time."""
    with app.app_context():
        appointment = add_appointment(seed.pat1_id, seed.doc1_id, seed.slot_date, time(9, 0))
        db.session.commit()
        drift = abs(appointment.created_at - datetime.utcnow())
        assert drift < timedelta(minutes=1), 'created_at should be UTC, not hospital time'
