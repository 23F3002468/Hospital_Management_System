"""Appointment booking, cancellation and completion.

Regression cover for:
  #8  double-booking race - a partial unique index makes the slot rule safe
      under concurrency, and losing the race must read like a normal rejection
  #11 date logic runs on Asia/Kolkata, not UTC
  the widened duplicate check - a patient cannot hold two bookings at the same
      minute, whichever doctors they are with
"""

from datetime import datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query

from conftest import add_appointment, book, login
from models import Appointment, db
from timeutils import hospital_today


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_booking_an_available_slot_succeeds(app, patient_client, seed):
    response = book(patient_client, seed.doc1_id, seed.slot_date, '10:00',
                    reason_for_visit='Chest pain')
    assert response.status_code == 201

    body = response.get_json()['appointment']
    assert body['date'] == seed.slot_date.isoformat()
    assert body['time'] == '10:00'
    assert body['status'] == 'Booked'

    with app.app_context():
        appointment = db.session.get(Appointment, body['id'])
        assert appointment.patient_id == seed.pat1_id
        assert appointment.doctor_id == seed.doc1_id
        assert appointment.reason_for_visit == 'Chest pain'


def test_a_booked_appointment_shows_up_in_the_patients_list(patient_client, seed):
    book(patient_client, seed.doc1_id, seed.slot_date, '10:00')
    response = patient_client.get('/api/patient/appointments')
    assert response.status_code == 200
    appointments = response.get_json()['appointments']
    assert len(appointments) == 1
    assert appointments[0]['doctor_name'] == 'Doc1'


def test_a_booked_appointment_shows_up_on_the_doctors_list(app, patient_client, seed):
    book(patient_client, seed.doc1_id, seed.slot_date, '10:00')

    doctor_client = app.test_client()
    login(doctor_client, 'doc1')
    response = doctor_client.get('/api/doctor/appointments')
    assert response.status_code == 200
    assert len(response.get_json()['appointments']) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('missing', ['doctor_id', 'appointment_date', 'appointment_time'])
def test_booking_requires_doctor_date_and_time(patient_client, seed, missing):
    payload = {
        'doctor_id': seed.doc1_id,
        'appointment_date': seed.slot_date.isoformat(),
        'appointment_time': '10:00',
    }
    del payload[missing]
    response = patient_client.post('/api/patient/appointments/book', json=payload)
    assert response.status_code == 400


def test_booking_an_unknown_doctor_is_a_404(patient_client, seed):
    response = book(patient_client, 999999, seed.slot_date)
    assert response.status_code == 404


def test_booking_an_inactive_doctor_is_refused(patient_client, seed):
    response = book(patient_client, seed.doc3_id, seed.slot_date)
    assert response.status_code == 404
    assert 'inactive' in response.get_json()['error']


def test_booking_outside_the_doctors_hours_is_refused(patient_client, seed):
    """The seeded slot runs 09:00-17:00."""
    response = book(patient_client, seed.doc1_id, seed.slot_date, '18:00')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Doctor is not available at this time'


def test_booking_a_day_the_doctor_has_no_slot_for_is_refused(patient_client, seed):
    other_day = seed.slot_date + timedelta(days=1)
    response = book(patient_client, seed.doc1_id, other_day, '10:00')
    assert response.status_code == 400


def test_booking_in_the_past_is_refused(app, patient_client, seed):
    """Issue #11: the guard compares against hospital time, not UTC.

    Between 18:30 and midnight IST the two clocks disagree about the date, and
    the old ``utcnow()`` comparison accepted slots that had already passed.
    """
    yesterday = hospital_today() - timedelta(days=1)
    with app.app_context():
        db.session.add(_slot_for(seed.doc1_id, yesterday))
        db.session.commit()

    response = book(patient_client, seed.doc1_id, yesterday, '10:00')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Cannot book appointments in the past'


def _slot_for(doctor_id, on_date):
    from models import DoctorAvailability
    return DoctorAvailability(
        doctor_id=doctor_id, date=on_date,
        start_time=time(9, 0), end_time=time(17, 0),
        is_available=True, max_appointments=10,
    )


# ---------------------------------------------------------------------------
# Slot exclusivity - issue #8
# ---------------------------------------------------------------------------

def test_a_taken_slot_is_refused(app, patient_client, seed):
    assert book(patient_client, seed.doc1_id, seed.slot_date, '10:00').status_code == 201

    other = app.test_client()
    login(other, 'pat2')
    response = book(other, seed.doc1_id, seed.slot_date, '10:00')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'This time slot is already booked'


def test_losing_the_race_reads_like_an_ordinary_rejection(app, patient_client, seed, monkeypatch):
    """Force the check-then-act window open and land on the IntegrityError branch.

    Patching ``count`` to 0 makes the application-level check pass even though
    the slot is taken, which is exactly what a concurrent request would see.
    The database index is then the only thing standing in the way.
    """
    with app.app_context():
        add_appointment(seed.pat2_id, seed.doc1_id, seed.slot_date, time(10, 0))
        db.session.commit()

    monkeypatch.setattr(Query, 'count', lambda self: 0)

    response = book(patient_client, seed.doc1_id, seed.slot_date, '10:00')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'This time slot is already booked'


def test_the_unique_index_exists_on_a_freshly_created_schema(app):
    """``db.create_all()`` must produce the index; it is the race guard."""
    with app.app_context():
        indexes = {index.name for index in Appointment.__table__.indexes}
    assert 'uq_appointment_doctor_slot' in indexes


def test_the_database_refuses_two_live_bookings_for_one_slot(app, seed):
    with app.app_context():
        add_appointment(seed.pat1_id, seed.doc1_id, seed.slot_date, time(11, 0))
        db.session.commit()

        with pytest.raises(IntegrityError):
            # add_appointment flushes, so the index fires here rather than at
            # commit time.
            add_appointment(seed.pat2_id, seed.doc1_id, seed.slot_date, time(11, 0))
            db.session.commit()
        db.session.rollback()


def test_the_index_is_partial_so_a_cancelled_slot_can_be_rebooked(app, seed):
    """A plain unique constraint would burn the slot forever."""
    with app.app_context():
        first = add_appointment(seed.pat1_id, seed.doc1_id, seed.slot_date, time(12, 0))
        db.session.commit()

        first.status = 'Cancelled'
        db.session.commit()

        add_appointment(seed.pat2_id, seed.doc1_id, seed.slot_date, time(12, 0))
        db.session.commit()  # must not raise

        live = Appointment.query.filter_by(
            doctor_id=seed.doc1_id, appointment_time=time(12, 0), status='Booked'
        ).count()
        assert live == 1


def test_cancelling_frees_the_slot_through_the_api(app, patient_client, seed):
    booked = book(patient_client, seed.doc1_id, seed.slot_date, '10:00')
    appointment_id = booked.get_json()['appointment']['id']

    assert patient_client.post(
        f'/api/patient/appointments/{appointment_id}/cancel').status_code == 200

    other = app.test_client()
    login(other, 'pat2')
    assert book(other, seed.doc1_id, seed.slot_date, '10:00').status_code == 201


# ---------------------------------------------------------------------------
# One patient, one place at a time - the widened duplicate check
# ---------------------------------------------------------------------------

def test_a_patient_cannot_book_the_same_minute_with_a_second_doctor(patient_client, seed):
    """This returned 201 before the check was widened."""
    assert book(patient_client, seed.doc1_id, seed.slot_date, '10:00').status_code == 201

    response = book(patient_client, seed.doc2_id, seed.slot_date, '10:00')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'You already have an appointment at this time'


def test_a_patient_can_still_see_two_doctors_on_the_same_day(patient_client, seed):
    assert book(patient_client, seed.doc1_id, seed.slot_date, '10:00').status_code == 201
    assert book(patient_client, seed.doc2_id, seed.slot_date, '11:00').status_code == 201


def test_a_cancelled_booking_does_not_block_the_patients_next_one(app, patient_client, seed):
    first = book(patient_client, seed.doc1_id, seed.slot_date, '10:00')
    patient_client.post(
        f"/api/patient/appointments/{first.get_json()['appointment']['id']}/cancel")

    assert book(patient_client, seed.doc2_id, seed.slot_date, '10:00').status_code == 201


# ---------------------------------------------------------------------------
# Cancellation and completion
# ---------------------------------------------------------------------------

def test_a_patient_cannot_cancel_someone_elses_appointment(app, patient_client, seed):
    with app.app_context():
        appointment = add_appointment(seed.pat2_id, seed.doc1_id, seed.slot_date, time(14, 0))
        db.session.commit()
        appointment_id = appointment.id

    response = patient_client.post(f'/api/patient/appointments/{appointment_id}/cancel')
    assert response.status_code == 404


def test_a_past_appointment_cannot_be_cancelled(app, patient_client, seed):
    with app.app_context():
        appointment = add_appointment(
            seed.pat1_id, seed.doc1_id, hospital_today() - timedelta(days=1), time(10, 0))
        db.session.commit()
        appointment_id = appointment.id

    response = patient_client.post(f'/api/patient/appointments/{appointment_id}/cancel')
    assert response.status_code == 400


def test_a_doctor_completes_an_appointment_and_records_a_treatment(app, patient_client, seed):
    appointment_id = book(
        patient_client, seed.doc1_id, seed.slot_date, '10:00'
    ).get_json()['appointment']['id']

    doctor_client = app.test_client()
    login(doctor_client, 'doc1')
    response = doctor_client.post(
        f'/api/doctor/appointments/{appointment_id}/complete',
        json={'diagnosis': 'Angina', 'prescription': 'Aspirin', 'notes': 'Review in a month'},
    )
    assert response.status_code == 200

    history = patient_client.get('/api/patient/treatment-history').get_json()['treatments']
    assert len(history) == 1
    assert history[0]['diagnosis'] == 'Angina'
    assert history[0]['doctor_name'] == 'Doc1'


def test_completing_requires_a_diagnosis(app, patient_client, seed):
    appointment_id = book(
        patient_client, seed.doc1_id, seed.slot_date, '10:00'
    ).get_json()['appointment']['id']

    doctor_client = app.test_client()
    login(doctor_client, 'doc1')
    response = doctor_client.post(
        f'/api/doctor/appointments/{appointment_id}/complete', json={'prescription': 'Aspirin'})
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Diagnosis is required'


def test_a_doctor_cannot_complete_another_doctors_appointment(app, patient_client, seed):
    appointment_id = book(
        patient_client, seed.doc1_id, seed.slot_date, '10:00'
    ).get_json()['appointment']['id']

    other_doctor = app.test_client()
    login(other_doctor, 'doc2')
    response = other_doctor.post(
        f'/api/doctor/appointments/{appointment_id}/complete', json={'diagnosis': 'X'})
    assert response.status_code == 404


def test_a_cancelled_appointment_cannot_be_completed(app, patient_client, seed):
    appointment_id = book(
        patient_client, seed.doc1_id, seed.slot_date, '10:00'
    ).get_json()['appointment']['id']
    patient_client.post(f'/api/patient/appointments/{appointment_id}/cancel')

    doctor_client = app.test_client()
    login(doctor_client, 'doc1')
    response = doctor_client.post(
        f'/api/doctor/appointments/{appointment_id}/complete', json={'diagnosis': 'X'})
    assert response.status_code == 400
