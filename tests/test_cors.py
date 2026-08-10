"""Cross-origin policy.

Regression cover for security finding 08. `CORS(app)` with no arguments
reflected any Origin the caller sent, so every site on the internet could read
this API's unauthenticated responses. It was safe only by accident - credentials
were not allowed, so browsers withheld the session cookie. Adding
`supports_credentials=True` later, which is the obvious thing to reach for when
splitting the frontend onto its own domain, would have turned it into account
takeover from any website.

The frontend is served by this same app and calls relative paths, so the default
is now no CORS at all.
"""

import pytest

from app import create_app

EVIL = 'https://evil.example'
FRIEND = 'https://app.hospital.example'


def cross_origin_get(client, origin=EVIL):
    return client.get('/api/health', headers={'Origin': origin})


def test_no_cors_headers_by_default(client):
    """The important one: an unknown site gets no permission to read anything."""
    response = cross_origin_get(client)
    assert response.status_code == 200
    assert response.headers.get('Access-Control-Allow-Origin') is None


def test_preflight_is_not_granted_by_default(client):
    response = client.options('/api/patient/appointments/book', headers={
        'Origin': EVIL,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
    })
    assert response.headers.get('Access-Control-Allow-Origin') is None


def test_same_origin_requests_are_unaffected(client, seed):
    """No Origin header at all - the actual frontend. Must still work."""
    response = client.post('/api/auth/login',
                           json={'username': 'pat1', 'password': 'pw'})
    assert response.status_code == 200


@pytest.fixture
def cors_app(monkeypatch):
    """An app built with CORS_ORIGINS naming one allowed origin."""
    monkeypatch.setenv('CORS_ORIGINS', f'{FRIEND}, https://admin.hospital.example')
    return create_app('testing')


def test_named_origins_are_allowed_when_configured(cors_app):
    response = cross_origin_get(cors_app.test_client(), origin=FRIEND)
    assert response.headers.get('Access-Control-Allow-Origin') == FRIEND


def test_origins_outside_the_list_are_still_refused(cors_app):
    response = cross_origin_get(cors_app.test_client(), origin=EVIL)
    assert response.headers.get('Access-Control-Allow-Origin') is None


def test_credentials_are_never_allowed(cors_app):
    """Sending the session cookie cross-origin needs CSRF tokens first."""
    response = cross_origin_get(cors_app.test_client(), origin=FRIEND)
    assert response.headers.get('Access-Control-Allow-Credentials') is None


def test_cors_is_scoped_to_the_api(cors_app):
    """The HTML pages are not an API; nobody needs to fetch them cross-origin."""
    response = cors_app.test_client().get('/', headers={'Origin': FRIEND})
    assert response.headers.get('Access-Control-Allow-Origin') is None
