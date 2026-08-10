"""The demo doctor seed.

The point of `demo_data.py` is that a fresh clone is explorable from the patient
side without anyone first logging in as admin to create a doctor. These tests
assert exactly that: after seeding, a patient can see doctors in every
department and book one.
"""

from datetime import timedelta

import pytest

from conftest import login
from demo_data import DEMO_DOCTOR_PASSWORD, DEMO_DOCTORS, create_demo_doctors
from models import Department, Doctor, DoctorAvailability, User, db
from timeutils import hospital_today

DEPARTMENT_NAMES = [
    'Cardiology', 'Neurology', 'Orthopedics', 'Pediatrics', 'Dermatology',
    'General Medicine', 'Gynecology', 'ENT (Otolaryngology)', 'Ophthalmology',
    'Psychiatry',
]


@pytest.fixture
def demo(app, monkeypatch):
    """Seed the default departments, then the demo doctors, then a patient."""
    import demo_data
    from werkzeug.security import generate_password_hash

    from conftest import FIXTURE_HASH_METHOD

    # Twelve scrypt hashes per test put this module at 20s on its own. The
    # algorithm is recorded in the hash string, so login still works.
    monkeypatch.setattr(
        demo_data, 'generate_password_hash',
        lambda password: generate_password_hash(password, method=FIXTURE_HASH_METHOD))

    with app.app_context():
        db.session.add_all(Department(name=name) for name in DEPARTMENT_NAMES)
        db.session.commit()

        created, skipped, slots = create_demo_doctors(verbose=False)

        from conftest import make_patient
        make_patient('pat1')
        db.session.commit()

    return created, skipped, slots


# ---------------------------------------------------------------------------
# The seed itself
# ---------------------------------------------------------------------------

def test_seeding_creates_at_least_ten_doctors(app, demo):
    created, _, _ = demo
    assert created >= 10

    with app.app_context():
        assert Doctor.query.count() == len(DEMO_DOCTORS)


def test_every_department_gets_at_least_one_doctor(app, demo):
    with app.app_context():
        for name in DEPARTMENT_NAMES:
            department = Department.query.filter_by(name=name).one()
            assert department.doctors_count >= 1, f'{name} has no doctor'


def test_demo_doctors_are_active_and_can_log_in(app, demo):
    client = app.test_client()
    response = client.post('/api/auth/login',
                           json={'username': 'dr.otho', 'password': DEMO_DOCTOR_PASSWORD})
    assert response.status_code == 200
    assert response.get_json()['user']['role'] == 'doctor'
    assert response.get_json()['user']['profile']['department'] == 'Orthopedics'


def test_names_carry_no_dr_prefix(app, demo):
    """Two templates render `Dr. {{ name }}`; a stored prefix reads "Dr. Dr. Otho"."""
    with app.app_context():
        prefixed = [
            user.full_name for user in User.query.filter_by(role='doctor').all()
            if user.full_name.lower().startswith('dr')
        ]
    assert not prefixed, f'stored names must omit the title: {prefixed}'


def test_the_naming_convention_echoes_the_department(app, demo):
    """Dr. Otho in Orthopedics, Dr. Cardia in Cardiology - see demo_data.py."""
    with app.app_context():
        by_username = {
            doctor.user.username: doctor.department.name
            for doctor in Doctor.query.join(User).all()
        }
    assert by_username['dr.otho'] == 'Orthopedics'
    assert by_username['dr.cardia'] == 'Cardiology'
    assert by_username['dr.pedia'] == 'Pediatrics'


def test_seeding_is_idempotent(app, demo):
    with app.app_context():
        before = Doctor.query.count()
        created, skipped, slots = create_demo_doctors(verbose=False)

        assert created == 0
        assert skipped == len(DEMO_DOCTORS)
        assert slots == 0
        assert Doctor.query.count() == before


def test_seeding_without_departments_fails_loudly(app):
    """Better than silently creating nothing and leaving an empty dashboard."""
    with app.app_context():
        with pytest.raises(RuntimeError, match='Run init_db.py first'):
            create_demo_doctors(verbose=False)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def test_every_demo_doctor_has_slots_from_today_onwards(app, demo):
    today = hospital_today()
    with app.app_context():
        for doctor in Doctor.query.all():
            slots = DoctorAvailability.query.filter(
                DoctorAvailability.doctor_id == doctor.id,
                DoctorAvailability.date >= today,
            ).count()
            assert slots > 0, f'doctor {doctor.id} has an empty calendar'


def test_availability_covers_the_seven_day_booking_window(app, demo):
    """The patient availability endpoint queries today .. today + 7."""
    today = hospital_today()
    with app.app_context():
        doctor = Doctor.query.join(User).filter(User.username == 'dr.otho').one()
        dates = {
            slot.date for slot in
            DoctorAvailability.query.filter_by(doctor_id=doctor.id).all()
        }
    for offset in range(8):
        assert today + timedelta(days=offset) in dates


def test_topping_up_adds_nothing_when_the_calendar_is_already_full(app, demo):
    with app.app_context():
        before = DoctorAvailability.query.count()
        create_demo_doctors(verbose=False)
        assert DoctorAvailability.query.count() == before


# ---------------------------------------------------------------------------
# What a patient actually sees - the reason this seed exists
# ---------------------------------------------------------------------------

def test_a_patient_sees_doctors_in_every_department_immediately(app, demo):
    client = app.test_client()
    login(client, 'pat1')

    departments = client.get('/api/patient/departments').get_json()['departments']
    assert len(departments) == len(DEPARTMENT_NAMES)
    assert all(department['doctors_count'] >= 1 for department in departments)
    assert all(department['available_doctors'] >= 1 for department in departments), \
        'every department should have a doctor available today'

    doctors = client.get('/api/patient/doctors').get_json()['doctors']
    assert len(doctors) == len(DEMO_DOCTORS)
    assert all(doctor['qualification'] and doctor['bio'] for doctor in doctors)


def test_a_patient_can_book_a_demo_doctor_without_any_admin_setup(app, demo):
    client = app.test_client()
    login(client, 'pat1')

    doctors = client.get('/api/patient/doctors').get_json()['doctors']
    orthopedist = next(d for d in doctors if d['department'] == 'Orthopedics')

    availability = client.get(
        f"/api/patient/doctors/{orthopedist['id']}/availability").get_json()
    assert availability['availability'], 'no bookable slots for the next 7 days'

    # Tomorrow's morning block - today's may already be in the past.
    tomorrow = (hospital_today() + timedelta(days=1)).isoformat()
    slot = next(s for s in availability['availability'] if s['date'] == tomorrow)

    response = client.post('/api/patient/appointments/book', json={
        'doctor_id': orthopedist['id'],
        'appointment_date': slot['date'],
        'appointment_time': slot['start_time'],
        'reason_for_visit': 'Knee pain',
    })
    assert response.status_code == 201, response.get_json()
    assert response.get_json()['appointment']['department'] == 'Orthopedics'
