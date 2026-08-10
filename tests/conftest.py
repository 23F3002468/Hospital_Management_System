"""Shared fixtures for the test suite.

Two rules govern everything here, both learned the hard way:

1. **Never issue a test request from inside an app context.** Flask reuses an
   already-pushed app context for test requests and Flask-Login caches the
   resolved user on ``g``. Two clients inside one ``with app.app_context():``
   bleed into each other - a patient session starts returning 403 once an admin
   logs in. Fixtures set data up inside a context and leave it before any
   request is made; tests that need to inspect the database afterwards push
   their own short-lived context.

2. **Always build the app with ``create_app('testing')``.** Setting
   ``SQLALCHEMY_DATABASE_URI`` on an app that already exists does nothing,
   because Flask-SQLAlchemy binds its engine at ``init_app()`` time - a test
   doing that writes into the real ``hospital.db``.
"""

from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from cache import cache
from models import (
    Appointment,
    Department,
    Doctor,
    DoctorAvailability,
    Patient,
    Treatment,
    User,
    db,
)
from timeutils import hospital_today

PASSWORD = 'pw'

# Werkzeug defaults to scrypt, which is deliberately slow - seeding a few dozen
# users with it dominated the runtime of the whole suite. Fixture users get a
# cheap hash instead; check_password_hash reads the algorithm back out of the
# stored string, so the login path under test is unchanged. Anything the
# application hashes itself (registration, change-password) still uses the
# real default.
FIXTURE_HASH_METHOD = 'pbkdf2:sha256:1'


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """A fresh app with an empty in-memory database, one per test."""
    application = create_app('testing')

    with application.app_context():
        db.create_all()
        # The Cache object is a module-level singleton shared by every app, so
        # a stale department list can survive into the next test.
        cache.clear()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """An unauthenticated client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def make_user(username, role, active=True, **kwargs):
    """Create and flush a User. Returns the instance."""
    user = User(
        username=username,
        email=f'{username}@example.com',
        password=generate_password_hash(PASSWORD, method=FIXTURE_HASH_METHOD),
        role=role,
        full_name=kwargs.pop('full_name', username.replace('_', ' ').title()),
        phone=kwargs.pop('phone', '9999999999'),
        is_active=active,
        **kwargs,
    )
    db.session.add(user)
    db.session.flush()
    return user


def make_doctor(username, department, active=True, with_slot_on=None):
    """Create a doctor, optionally with a 09:00-17:00 availability slot."""
    user = make_user(username, 'doctor', active=active)
    doctor = Doctor(
        user_id=user.id,
        department_id=department.id,
        qualification='MBBS',
        experience_years=5,
        consultation_fee=500.0,
    )
    db.session.add(doctor)
    db.session.flush()
    if with_slot_on is not None:
        db.session.add(DoctorAvailability(
            doctor_id=doctor.id,
            date=with_slot_on,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_available=True,
            max_appointments=10,
        ))
        db.session.flush()
    return doctor


def make_patient(username, active=True, date_of_birth=None):
    user = make_user(username, 'patient', active=active)
    patient = Patient(
        user_id=user.id,
        date_of_birth=date_of_birth,
        blood_group='O+',
    )
    db.session.add(patient)
    db.session.flush()
    return patient


@pytest.fixture
def seed(app):
    """A small hospital.

    Two departments, an admin, three doctors (two active in Cardiology with
    availability, one inactive in Neurology) and two patients. Returns the ids
    - not the ORM objects, which would be detached once the setup context exits.
    """
    slot_date = hospital_today() + timedelta(days=2)

    with app.app_context():
        cardiology = Department(name='Cardiology', description='Heart')
        neurology = Department(name='Neurology', description='Brain')
        db.session.add_all([cardiology, neurology])
        db.session.flush()

        admin = make_user('admin', 'admin')
        doc1 = make_doctor('doc1', cardiology, with_slot_on=slot_date)
        doc2 = make_doctor('doc2', cardiology, with_slot_on=slot_date)
        doc3 = make_doctor('doc3', neurology, active=False)
        pat1 = make_patient('pat1', date_of_birth=date(1990, 6, 15))
        pat2 = make_patient('pat2')

        db.session.commit()

        ids = SimpleNamespace(
            slot_date=slot_date,
            cardiology_id=cardiology.id,
            neurology_id=neurology.id,
            admin_id=admin.id,
            doc1_id=doc1.id,
            doc2_id=doc2.id,
            doc3_id=doc3.id,
            doc1_user_id=doc1.user_id,
            pat1_id=pat1.id,
            pat2_id=pat2.id,
            pat1_user_id=pat1.user_id,
        )

    # Context is closed before any request is issued - see rule 1 above.
    return ids


# ---------------------------------------------------------------------------
# Authenticated clients
# ---------------------------------------------------------------------------

def login(client, username, password=PASSWORD):
    return client.post(
        '/api/auth/login',
        json={'username': username, 'password': password},
    )


def logged_in_client(app, username):
    c = app.test_client()
    response = login(c, username)
    assert response.status_code == 200, f'fixture login failed: {response.get_json()}'
    return c


@pytest.fixture
def admin_client(app, seed):
    return logged_in_client(app, 'admin')


@pytest.fixture
def doctor_client(app, seed):
    return logged_in_client(app, 'doc1')


@pytest.fixture
def patient_client(app, seed):
    return logged_in_client(app, 'pat1')


# ---------------------------------------------------------------------------
# Helpers used by more than one module
# ---------------------------------------------------------------------------

def book(client, doctor_id, on_date, at_time='10:00', **extra):
    """POST a booking. ``on_date`` may be a date or an ISO string."""
    payload = {
        'doctor_id': doctor_id,
        'appointment_date': on_date.isoformat() if hasattr(on_date, 'isoformat') else on_date,
        'appointment_time': at_time,
    }
    payload.update(extra)
    return client.post('/api/patient/appointments/book', json=payload)


def add_appointment(patient_id, doctor_id, on_date, at_time, status='Booked'):
    """Insert an appointment directly, bypassing the booking rules."""
    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=on_date,
        appointment_time=at_time,
        status=status,
    )
    db.session.add(appointment)
    db.session.flush()
    return appointment


__all__ = [
    'PASSWORD',
    'add_appointment',
    'book',
    'login',
    'make_doctor',
    'make_patient',
    'make_user',
    'Appointment',
    'Department',
    'Doctor',
    'DoctorAvailability',
    'Patient',
    'Treatment',
    'User',
    'db',
]
