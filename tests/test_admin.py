"""Admin doctor/patient management and the department cache.

Regression cover for:
  #7  the department list is cached and must be invalidated by every admin
      change that alters a department's doctor counts
  #12 deleting a doctor who has appointments must be refused, not attempted
  #17 a deliberate 404 must not come back as a 500
"""

from datetime import time

import pytest

from conftest import add_appointment, login
from cache import DEPARTMENTS_KEY, cache
from models import Appointment, Doctor, Treatment, User, db

NEW_DOCTOR = {
    'username': 'doc_new',
    'email': 'doc_new@example.com',
    'password': 'secret123',
    'full_name': 'Doc New',
    'phone': '9111111111',
    'qualification': 'MD',
    'experience_years': 3,
}


# ---------------------------------------------------------------------------
# Dashboard and listings
# ---------------------------------------------------------------------------

def test_dashboard_reports_the_headline_numbers(app, admin_client, seed, patient_client):
    from conftest import book
    book(patient_client, seed.doc1_id, seed.slot_date, '10:00')

    stats = admin_client.get('/api/admin/dashboard').get_json()['statistics']
    assert stats['total_doctors'] == 2      # doc3 is inactive
    assert stats['total_patients'] == 2
    assert stats['total_appointments'] == 1
    assert stats['upcoming_appointments'] == 1
    assert stats['completed_appointments'] == 0


def test_doctor_listing_can_be_searched(admin_client, seed):
    response = admin_client.get('/api/admin/doctors?search=Doc1')
    assert response.status_code == 200
    names = [doctor['name'] for doctor in response.get_json()['doctors']]
    assert names == ['Doc1']


def test_appointment_listing_joins_in_the_related_names(app, admin_client, seed):
    with app.app_context():
        add_appointment(seed.pat1_id, seed.doc1_id, seed.slot_date, time(10, 0))
        db.session.commit()

    appointments = admin_client.get('/api/admin/appointments').get_json()['appointments']
    assert len(appointments) == 1
    assert appointments[0]['patient_name'] == 'Pat1'
    assert appointments[0]['doctor_name'] == 'Doc1'
    assert appointments[0]['department'] == 'Cardiology'


# ---------------------------------------------------------------------------
# Adding and toggling doctors
# ---------------------------------------------------------------------------

def test_admin_adds_a_doctor(app, admin_client, seed):
    response = admin_client.post('/api/admin/doctors/add',
                                 json={**NEW_DOCTOR, 'department_id': seed.cardiology_id})
    assert response.status_code == 201

    with app.app_context():
        user = User.query.filter_by(username='doc_new').one()
        assert user.role == 'doctor'
        assert user.doctor_profile.department_id == seed.cardiology_id


def test_adding_a_doctor_to_an_unknown_department_is_a_404(admin_client, seed):
    response = admin_client.post('/api/admin/doctors/add',
                                 json={**NEW_DOCTOR, 'department_id': 9999})
    assert response.status_code == 404


def test_adding_a_doctor_requires_the_mandatory_fields(admin_client, seed):
    payload = {**NEW_DOCTOR, 'department_id': seed.cardiology_id}
    del payload['email']
    response = admin_client.post('/api/admin/doctors/add', json=payload)
    assert response.status_code == 400


def test_toggle_status_flips_the_active_flag(app, admin_client, seed):
    assert admin_client.post(
        f'/api/admin/doctors/{seed.doc1_id}/toggle-status').status_code == 200
    with app.app_context():
        assert db.session.get(User, seed.doc1_user_id).is_active is False

    assert admin_client.post(
        f'/api/admin/doctors/{seed.doc1_id}/toggle-status').status_code == 200
    with app.app_context():
        assert db.session.get(User, seed.doc1_user_id).is_active is True


def test_a_deactivated_doctor_disappears_from_the_active_listing(admin_client, seed):
    admin_client.post(f'/api/admin/doctors/{seed.doc1_id}/toggle-status')
    doctors = admin_client.get('/api/admin/doctors?status=active').get_json()['doctors']
    assert 'Doc1' not in [doctor['name'] for doctor in doctors]


# ---------------------------------------------------------------------------
# Deleting doctors - issue #12
# ---------------------------------------------------------------------------

def test_deleting_a_doctor_with_no_history_succeeds(app, admin_client, seed):
    response = admin_client.delete(f'/api/admin/doctors/{seed.doc3_id}')
    assert response.status_code == 200

    with app.app_context():
        assert db.session.get(Doctor, seed.doc3_id) is None


def test_deleting_a_doctor_with_appointments_is_refused(app, admin_client, seed):
    with app.app_context():
        add_appointment(seed.pat1_id, seed.doc1_id, seed.slot_date, time(10, 0))
        db.session.commit()

    response = admin_client.delete(f'/api/admin/doctors/{seed.doc1_id}')
    assert response.status_code == 409
    assert 'Deactivate the doctor instead' in response.get_json()['error']


def test_a_refused_delete_leaves_the_records_intact(app, admin_client, seed):
    """The point of refusing: a patient's treatment history must survive."""
    with app.app_context():
        appointment = add_appointment(
            seed.pat1_id, seed.doc1_id, seed.slot_date, time(10, 0), status='Completed')
        db.session.add(Treatment(appointment_id=appointment.id, diagnosis='Angina'))
        db.session.commit()

    admin_client.delete(f'/api/admin/doctors/{seed.doc1_id}')

    with app.app_context():
        assert db.session.get(Doctor, seed.doc1_id) is not None
        assert Appointment.query.count() == 1
        assert Treatment.query.count() == 1
        orphans = Appointment.query.filter(
            ~Appointment.doctor_id.in_(db.session.query(Doctor.id))).count()
        assert orphans == 0


def test_a_cancelled_appointment_still_blocks_the_delete(app, admin_client, seed):
    with app.app_context():
        add_appointment(seed.pat1_id, seed.doc1_id, seed.slot_date, time(10, 0),
                        status='Cancelled')
        db.session.commit()

    assert admin_client.delete(f'/api/admin/doctors/{seed.doc1_id}').status_code == 409


def test_deleting_a_doctor_removes_their_user_account(app, admin_client, seed):
    with app.app_context():
        doc3_user_id = db.session.get(Doctor, seed.doc3_id).user_id

    admin_client.delete(f'/api/admin/doctors/{seed.doc3_id}')

    with app.app_context():
        assert db.session.get(User, doc3_user_id) is None


# ---------------------------------------------------------------------------
# Deliberate 404s - issue #17
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('method,path', [
    ('get', '/api/admin/doctors/9999'),
    ('put', '/api/admin/doctors/9999'),
    ('delete', '/api/admin/doctors/9999'),
    ('post', '/api/admin/doctors/9999/toggle-status'),
    ('get', '/api/admin/patients/9999'),
])
def test_a_missing_row_is_a_404_not_a_500(admin_client, seed, method, path):
    response = getattr(admin_client, method)(path, json={})
    assert response.status_code == 404, 'abort(404) was being swallowed into a 500'


# ---------------------------------------------------------------------------
# Department cache - issue #7
# ---------------------------------------------------------------------------

def read_cache(app):
    with app.app_context():
        return cache.get(DEPARTMENTS_KEY)


def test_the_department_list_is_cached_after_the_first_read(app, patient_client, seed):
    assert read_cache(app) is None

    response = patient_client.get('/api/patient/departments')
    assert response.status_code == 200
    assert read_cache(app) is not None


def test_the_cached_counts_are_correct(patient_client, seed):
    departments = patient_client.get('/api/patient/departments').get_json()['departments']
    by_name = {department['name']: department for department in departments}
    assert by_name['Cardiology']['doctors_count'] == 2
    assert by_name['Neurology']['doctors_count'] == 0  # doc3 is inactive


@pytest.mark.parametrize('mutate', [
    'toggle',
    'add',
    'delete',
], ids=['toggle-status', 'add-doctor', 'delete-doctor'])
def test_admin_doctor_changes_invalidate_the_department_cache(
        app, admin_client, patient_client, seed, mutate):
    patient_client.get('/api/patient/departments')
    assert read_cache(app) is not None

    if mutate == 'toggle':
        admin_client.post(f'/api/admin/doctors/{seed.doc1_id}/toggle-status')
    elif mutate == 'add':
        admin_client.post('/api/admin/doctors/add',
                          json={**NEW_DOCTOR, 'department_id': seed.cardiology_id})
    else:
        admin_client.delete(f'/api/admin/doctors/{seed.doc3_id}')

    assert read_cache(app) is None, 'a stale department list survived an admin change'


def test_a_patient_sees_the_new_count_immediately_after_an_admin_change(
        app, admin_client, patient_client, seed):
    """The end-to-end version: no 5-minute wait for the TTL."""
    before = patient_client.get('/api/patient/departments').get_json()['departments']
    assert next(d for d in before if d['name'] == 'Cardiology')['doctors_count'] == 2

    admin_client.post(f'/api/admin/doctors/{seed.doc1_id}/toggle-status')

    after = patient_client.get('/api/patient/departments').get_json()['departments']
    assert next(d for d in after if d['name'] == 'Cardiology')['doctors_count'] == 1


def test_updating_a_doctors_department_invalidates_the_cache(
        app, admin_client, patient_client, seed):
    patient_client.get('/api/patient/departments')
    response = admin_client.put(f'/api/admin/doctors/{seed.doc1_id}',
                                json={'department_id': seed.neurology_id})
    assert response.status_code == 200
    assert read_cache(app) is None
