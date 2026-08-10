"""Registration, login, session lifetime and role guards.

Regression cover for:
  #3  deactivating a user must end their live session, not wait for the cookie
  #14 a one-to-one backref is always present and may be None, so the old
      ``hasattr`` guard let a missing profile row through and 500'd
"""

import pytest

from conftest import PASSWORD, login, make_user
from models import Patient, User, db

REGISTRATION = {
    'username': 'newpatient',
    'email': 'new@example.com',
    'password': 'secret123',
    'full_name': 'New Patient',
    'phone': '9000000000',
    'date_of_birth': '1995-03-01',
    'blood_group': 'A+',
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_creates_a_user_and_a_patient_profile(app, client, seed):
    response = client.post('/api/auth/register', json=REGISTRATION)
    assert response.status_code == 201
    assert response.get_json()['user']['role'] == 'patient'

    with app.app_context():
        user = User.query.filter_by(username='newpatient').one()
        assert user.patient_profile is not None
        assert user.patient_profile.blood_group == 'A+'
        # The password is hashed, never stored as given.
        assert user.password != REGISTRATION['password']


@pytest.mark.parametrize('field', ['username', 'email', 'password', 'full_name', 'phone'])
def test_register_requires_every_mandatory_field(client, seed, field):
    payload = {key: value for key, value in REGISTRATION.items() if key != field}
    response = client.post('/api/auth/register', json=payload)
    assert response.status_code == 400
    assert field in response.get_json()['error']


def test_register_rejects_a_duplicate_username(client, seed):
    response = client.post('/api/auth/register', json={**REGISTRATION, 'username': 'pat1'})
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Username already exists'


def test_register_rejects_a_duplicate_email(client, seed):
    response = client.post('/api/auth/register', json={**REGISTRATION, 'email': 'pat1@example.com'})
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Email already exists'


def test_registration_does_not_leave_a_half_written_user(app, client, seed):
    """A rejected registration must not commit the User row on its own."""
    client.post('/api/auth/register', json={**REGISTRATION, 'username': 'pat1'})
    with app.app_context():
        assert User.query.filter_by(email=REGISTRATION['email']).first() is None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_succeeds_and_returns_the_profile(client, seed):
    response = login(client, 'pat1')
    assert response.status_code == 200
    body = response.get_json()['user']
    assert body['role'] == 'patient'
    assert body['profile']['blood_group'] == 'O+'


def test_login_rejects_a_wrong_password(client, seed):
    response = login(client, 'pat1', 'not-the-password')
    assert response.status_code == 401
    assert response.get_json()['error'] == 'Invalid username or password'


def test_login_rejects_an_unknown_user(client, seed):
    response = login(client, 'nobody')
    assert response.status_code == 401


def test_login_does_not_reveal_whether_the_username_exists(client, seed):
    """Both failures must be indistinguishable to the caller."""
    unknown = login(client, 'nobody')
    wrong_password = login(client, 'pat1', 'wrong')
    assert unknown.get_json() == wrong_password.get_json()
    assert unknown.status_code == wrong_password.status_code


def test_login_rejects_a_deactivated_account(client, seed):
    response = login(client, 'doc3')  # seeded inactive
    assert response.status_code == 403
    assert 'deactivated' in response.get_json()['error']


def test_logout_ends_the_session(patient_client):
    assert patient_client.post('/api/auth/logout').status_code == 200
    assert patient_client.get('/api/patient/dashboard').status_code == 302


# ---------------------------------------------------------------------------
# Session lifetime - issue #3
# ---------------------------------------------------------------------------

def test_deactivating_a_user_ends_their_live_session(app, patient_client, seed):
    assert patient_client.get('/api/auth/me').status_code == 200

    with app.app_context():
        user = db.session.get(User, seed.pat1_user_id)
        user.is_active = False
        db.session.commit()

    # No new login, same cookie: the user loader must now refuse to load them.
    response = patient_client.get('/api/auth/me')
    assert response.status_code == 302, 'a blacklisted user kept their session'


def test_the_user_loader_refuses_a_deactivated_account(app, seed):
    """Pins the #3 change itself, not just its effect.

    The two tests either side of this one pass even with the ``is_active``
    check removed from ``load_user``, because Flask-Login's
    ``UserMixin.is_authenticated`` returns ``self.is_active`` and the model's
    column shadows the mixin's property - so ``@login_required`` already
    rejects a blacklisted user. This asserts the loader's own contract, which
    is the thing that would silently regress.
    """
    with app.app_context():
        user = db.session.get(User, seed.pat1_user_id)
        user.is_active = False
        db.session.commit()

        assert app.login_manager._user_callback(str(seed.pat1_user_id)) is None
        assert app.login_manager._user_callback(str(seed.admin_id)) is not None


def test_is_authenticated_tracks_the_is_active_column(app, seed):
    """Characterisation test for the behaviour the layer above depends on.

    ``User.is_active`` is a column that shadows ``UserMixin.is_active``.
    Renaming it - to ``active``, say - would silently restore the mixin's
    hardcoded ``True`` and blacklisting would stop working on every request.
    """
    with app.app_context():
        user = db.session.get(User, seed.pat1_user_id)
        assert user.is_authenticated is True
        user.is_active = False
        assert user.is_authenticated is False


def test_an_admin_blacklisting_a_doctor_ends_that_doctors_session(app, admin_client, seed):
    doctor_client = app.test_client()
    assert login(doctor_client, 'doc1').status_code == 200
    assert doctor_client.get('/api/doctor/dashboard').status_code == 200

    assert admin_client.post(f'/api/admin/doctors/{seed.doc1_id}/toggle-status').status_code == 200

    assert doctor_client.get('/api/doctor/dashboard').status_code == 302


# ---------------------------------------------------------------------------
# Missing profile rows - issue #14
# ---------------------------------------------------------------------------

def test_login_survives_a_patient_with_no_profile_row(app, client, seed):
    with app.app_context():
        make_user('orphan', 'patient')
        db.session.commit()

    response = login(client, 'orphan')
    assert response.status_code == 200, 'a missing Patient row used to 500 the login'
    assert response.get_json()['user']['profile'] == {}


def test_me_survives_a_doctor_with_no_profile_row(app, client, seed):
    with app.app_context():
        make_user('orphan_doc', 'doctor')
        db.session.commit()

    login(client, 'orphan_doc')
    response = client.get('/api/auth/me')
    assert response.status_code == 200
    assert response.get_json()['user']['profile'] == {}


# ---------------------------------------------------------------------------
# Role guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('path', [
    '/api/admin/dashboard',
    '/api/doctor/dashboard',
    '/api/patient/dashboard',
    '/api/auth/me',
])
def test_protected_endpoints_reject_anonymous_callers(client, path):
    assert client.get(path).status_code == 302


def test_a_patient_cannot_reach_admin_endpoints(patient_client):
    response = patient_client.get('/api/admin/dashboard')
    assert response.status_code == 403
    assert response.get_json()['error'] == 'Admin access required'


def test_a_patient_cannot_reach_doctor_endpoints(patient_client):
    response = patient_client.get('/api/doctor/dashboard')
    assert response.status_code == 403


def test_a_doctor_cannot_reach_patient_endpoints(doctor_client):
    response = doctor_client.get('/api/patient/dashboard')
    assert response.status_code == 403


def test_an_admin_cannot_reach_patient_endpoints(admin_client):
    assert admin_client.get('/api/patient/dashboard').status_code == 403


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

def test_change_password_requires_the_old_one(patient_client):
    response = patient_client.post('/api/auth/change-password',
                                   json={'old_password': 'wrong', 'new_password': 'brandnew'})
    assert response.status_code == 401


def test_change_password_enforces_a_minimum_length(patient_client):
    response = patient_client.post('/api/auth/change-password',
                                   json={'old_password': PASSWORD, 'new_password': 'abc'})
    assert response.status_code == 400


def test_change_password_takes_effect(app, patient_client):
    response = patient_client.post('/api/auth/change-password',
                                   json={'old_password': PASSWORD, 'new_password': 'brandnew'})
    assert response.status_code == 200

    fresh = app.test_client()
    assert login(fresh, 'pat1', PASSWORD).status_code == 401
    assert login(fresh, 'pat1', 'brandnew').status_code == 200
