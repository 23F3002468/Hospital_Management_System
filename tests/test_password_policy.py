"""The password floor.

Regression cover for security finding 11. `change_password` enforced six
characters while `register` and `add_doctor` enforced nothing at all - the rule
applied at the one moment a user is least likely to pick a weak password and was
skipped at the two moments they are most likely to. All three now share
`routes/validators.password_error`.
"""

import pytest

from conftest import PASSWORD, login
from models import User, db
from routes.validators import MIN_PASSWORD_LENGTH, password_error

REGISTRATION = {
    'username': 'newpatient',
    'email': 'new@example.com',
    'full_name': 'New Patient',
    'phone': '9000000000',
}

NEW_DOCTOR = {
    'username': 'doc_new',
    'email': 'doc_new@example.com',
    'full_name': 'Doc New',
    'phone': '9111111111',
}

TOO_SHORT = 'a' * (MIN_PASSWORD_LENGTH - 1)
JUST_LONG_ENOUGH = 'a' * MIN_PASSWORD_LENGTH


def test_the_floor_is_eight_characters():
    assert MIN_PASSWORD_LENGTH == 8


# ---------------------------------------------------------------------------
# The validator itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('password', ['', None, 'a', TOO_SHORT])
def test_validator_rejects_short_and_empty(password):
    assert password_error(password) is not None


@pytest.mark.parametrize('password', [JUST_LONG_ENOUGH, 'correct horse battery staple'])
def test_validator_accepts_long_enough(password):
    assert password_error(password) is None


def test_the_message_names_the_requirement():
    """A rejection the user cannot act on is a bad rejection."""
    message = password_error(TOO_SHORT)
    assert str(MIN_PASSWORD_LENGTH) in message
    assert 'characters' in message


def test_no_composition_rules_are_imposed():
    """Deliberately length-only - see the docstring in validators.py."""
    assert password_error('aaaaaaaaaa') is None       # no digit, no symbol, no caps


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_registration_rejects_a_short_password(app, client, seed):
    response = client.post('/api/auth/register',
                           json={**REGISTRATION, 'password': TOO_SHORT})
    assert response.status_code == 400
    assert str(MIN_PASSWORD_LENGTH) in response.get_json()['error']

    with app.app_context():
        assert User.query.filter_by(username='newpatient').first() is None


def test_registration_accepts_a_password_at_the_floor(client, seed):
    response = client.post('/api/auth/register',
                           json={**REGISTRATION, 'password': JUST_LONG_ENOUGH})
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Admin-created doctors
# ---------------------------------------------------------------------------

def test_admin_cannot_create_a_doctor_with_a_short_password(app, admin_client, seed):
    response = admin_client.post('/api/admin/doctors/add', json={
        **NEW_DOCTOR, 'password': TOO_SHORT, 'department_id': seed.cardiology_id})
    assert response.status_code == 400

    with app.app_context():
        assert User.query.filter_by(username='doc_new').first() is None


def test_admin_can_create_a_doctor_at_the_floor(admin_client, seed):
    response = admin_client.post('/api/admin/doctors/add', json={
        **NEW_DOCTOR, 'password': JUST_LONG_ENOUGH, 'department_id': seed.cardiology_id})
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Changing a password
# ---------------------------------------------------------------------------

def test_change_password_uses_the_same_floor(patient_client):
    """It used to allow six characters - two fewer than registration now does."""
    response = patient_client.post('/api/auth/change-password',
                                   json={'old_password': PASSWORD,
                                         'new_password': 'sixchr'})
    assert response.status_code == 400
    assert str(MIN_PASSWORD_LENGTH) in response.get_json()['error']


def test_change_password_accepts_the_floor(app, patient_client):
    response = patient_client.post('/api/auth/change-password',
                                   json={'old_password': PASSWORD,
                                         'new_password': JUST_LONG_ENOUGH})
    assert response.status_code == 200

    fresh = app.test_client()
    assert login(fresh, 'pat1', JUST_LONG_ENOUGH).status_code == 200


def test_all_three_routes_agree(app, admin_client, client, patient_client, seed):
    """One floor, three entry points. They drifted once; assert they cannot again."""
    register = client.post('/api/auth/register',
                           json={**REGISTRATION, 'password': TOO_SHORT})
    add_doctor = admin_client.post('/api/admin/doctors/add', json={
        **NEW_DOCTOR, 'password': TOO_SHORT, 'department_id': seed.cardiology_id})
    change = patient_client.post('/api/auth/change-password',
                                 json={'old_password': PASSWORD, 'new_password': TOO_SHORT})

    assert [register.status_code, add_doctor.status_code, change.status_code] == [400, 400, 400]

    messages = {
        register.get_json()['error'],
        add_doctor.get_json()['error'],
        change.get_json()['error'],
    }
    assert len(messages) == 1, f'three routes, three different messages: {messages}'


# ---------------------------------------------------------------------------
# Existing accounts
# ---------------------------------------------------------------------------

def test_existing_short_passwords_still_log_in(app, seed):
    """The floor applies to new passwords, not retroactively - nobody is locked out.

    The seeded fixtures use a two-character password, which is exactly the case.
    """
    client = app.test_client()
    assert login(client, 'pat1').status_code == 200


def test_the_demo_credentials_still_clear_the_floor():
    """admin123 is 8 characters and doctor123 is 9 - the demo logins survive."""
    from demo_data import DEMO_DOCTOR_PASSWORD

    from config import Config

    assert password_error(Config.ADMIN_PASSWORD) is None
    assert password_error(DEMO_DOCTOR_PASSWORD) is None
