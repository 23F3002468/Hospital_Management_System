"""What a doctor is allowed to see.

Regression cover for security finding 03: `/api/doctor/patients/<id>/history`
resolved the patient by raw id, so any doctor could read any patient's medical
history and allergies by changing the number in the URL. The appointment list
in the same response was correctly scoped, which is what made the bug easy to
miss - half the handler was right.
"""

from datetime import time, timedelta

import pytest

from conftest import add_appointment, login, make_patient
from models import Appointment, Patient, Treatment, db
from timeutils import hospital_today


@pytest.fixture
def patients(app, seed):
    """Two patients: one who has seen doc1, one who never has."""
    with app.app_context():
        mine = make_patient('mine', date_of_birth=None)
        mine.blood_group = 'O+'
        mine.medical_history = 'Hypertension since 2019'
        mine.allergies = 'Penicillin'

        stranger = make_patient('stranger')
        stranger.blood_group = 'AB-'
        stranger.medical_history = 'Confidential - never met doc1'
        stranger.allergies = 'Sulfa drugs'
        db.session.flush()

        # `mine` books with doc1; `stranger` books with doc2.
        appointment = add_appointment(mine.id, seed.doc1_id, hospital_today() - timedelta(days=7),
                                      time(10, 0), status='Completed')
        db.session.add(Treatment(appointment_id=appointment.id, diagnosis='Angina',
                                 prescription='Aspirin'))
        add_appointment(stranger.id, seed.doc2_id, hospital_today() - timedelta(days=7),
                        time(11, 0), status='Completed')
        db.session.commit()

        return {'mine': mine.id, 'stranger': stranger.id}


def test_a_doctor_reads_the_history_of_their_own_patient(app, patients):
    client = app.test_client()
    login(client, 'doc1')

    response = client.get(f"/api/doctor/patients/{patients['mine']}/history")
    assert response.status_code == 200

    body = response.get_json()
    assert body['patient']['medical_history'] == 'Hypertension since 2019'
    assert body['patient']['allergies'] == 'Penicillin'
    assert len(body['appointment_history']) == 1
    assert body['appointment_history'][0]['treatment']['diagnosis'] == 'Angina'


def test_a_doctor_cannot_read_a_stranger_patients_history(app, patients):
    """The bug: this returned 200 with the full clinical record."""
    client = app.test_client()
    login(client, 'doc1')

    response = client.get(f"/api/doctor/patients/{patients['stranger']}/history")
    assert response.status_code == 404


def test_no_clinical_field_leaks_in_the_refusal(app, patients):
    """A 404 that still ships the data would be no fix at all."""
    client = app.test_client()
    login(client, 'doc1')

    body = client.get(
        f"/api/doctor/patients/{patients['stranger']}/history").get_data(as_text=True)

    for secret in ('Confidential', 'AB-', 'Sulfa drugs', 'Stranger'):
        assert secret not in body, f'refusal leaked {secret!r}'


def test_an_unknown_patient_id_is_a_404(app, patients):
    client = app.test_client()
    login(client, 'doc1')
    assert client.get('/api/doctor/patients/999999/history').status_code == 404


def test_the_history_route_agrees_with_the_patient_list(app, patients, seed):
    """Whatever /patients returns must be exactly what /patients/<id>/history opens.

    The two used different predicates, which is how they drifted apart.
    """
    client = app.test_client()
    login(client, 'doc1')

    listed = {p['id'] for p in client.get('/api/doctor/patients').get_json()['patients']}
    assert listed == {patients['mine']}

    for patient_id in (patients['mine'], patients['stranger']):
        expected = 200 if patient_id in listed else 404
        response = client.get(f'/api/doctor/patients/{patient_id}/history')
        assert response.status_code == expected


def test_a_future_booking_is_enough_to_open_the_file(app, patients, seed):
    """A doctor needs to prepare for an appointment they have not held yet."""
    with app.app_context():
        upcoming = make_patient('upcoming')
        upcoming.medical_history = 'Asthma'
        db.session.flush()
        add_appointment(upcoming.id, seed.doc1_id, hospital_today() + timedelta(days=3),
                        time(9, 0))
        db.session.commit()
        upcoming_id = upcoming.id

    client = app.test_client()
    login(client, 'doc1')

    response = client.get(f'/api/doctor/patients/{upcoming_id}/history')
    assert response.status_code == 200
    assert response.get_json()['patient']['medical_history'] == 'Asthma'


def test_a_cancelled_booking_still_counts_as_a_relationship(app, patients, seed):
    """They met, or were about to; the record is legitimately theirs to see."""
    with app.app_context():
        cancelled = make_patient('cancelled_pat')
        db.session.flush()
        add_appointment(cancelled.id, seed.doc1_id, hospital_today() - timedelta(days=2),
                        time(9, 0), status='Cancelled')
        db.session.commit()
        cancelled_id = cancelled.id

    client = app.test_client()
    login(client, 'doc1')
    assert client.get(f'/api/doctor/patients/{cancelled_id}/history').status_code == 200


def test_two_appointments_do_not_produce_a_duplicate_patient(app, patients, seed):
    """The join can match twice; the response must still describe one person."""
    with app.app_context():
        add_appointment(patients['mine'], seed.doc1_id,
                        hospital_today() - timedelta(days=3), time(15, 0),
                        status='Completed')
        db.session.commit()

    client = app.test_client()
    login(client, 'doc1')

    body = client.get(f"/api/doctor/patients/{patients['mine']}/history").get_json()
    assert body['patient']['id'] == patients['mine']
    assert len(body['appointment_history']) == 2
