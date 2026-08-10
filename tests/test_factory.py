"""The application factory: routes, error handlers, login redirect.

Regression cover for issue #13 - the HTML routes used to be registered on the
module-level ``app`` rather than inside ``create_app()``, so a factory-built app
had no ``index`` endpoint and Flask-Login's redirect raised BuildError.
"""

import pytest

HTML_ROUTES = [
    '/',
    '/register',
    '/admin/dashboard',
    '/doctor/dashboard',
    '/patient/dashboard',
    '/patient/history',
]


def test_factory_registers_the_html_routes(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    missing = [route for route in HTML_ROUTES if route not in rules]
    assert not missing, f'factory-built app is missing {missing}'


def test_factory_registers_the_api_blueprints(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    for prefix in ('/api/auth/login', '/api/admin/dashboard',
                   '/api/doctor/dashboard', '/api/patient/dashboard'):
        assert prefix in rules


def test_landing_page_renders_for_anonymous_visitors(client):
    response = client.get('/')
    assert response.status_code == 200


@pytest.mark.parametrize('route', [
    '/admin/dashboard',
    '/doctor/dashboard',
    '/patient/dashboard',
    '/patient/history',
])
def test_protected_pages_redirect_to_login(client, route):
    """This is the case that used to raise BuildError instead of redirecting."""
    response = client.get(route)
    assert response.status_code == 302
    assert response.headers['Location'].startswith('/')


def test_dashboard_page_renders_for_its_own_role(patient_client):
    assert patient_client.get('/patient/dashboard').status_code == 200


def test_dashboard_page_rejects_the_wrong_role(patient_client):
    response = patient_client.get('/admin/dashboard')
    assert response.status_code == 302
    assert response.headers['Location'] == '/'


def test_landing_page_redirects_a_signed_in_user_to_their_dashboard(patient_client):
    response = patient_client.get('/')
    assert response.status_code == 302
    assert response.headers['Location'] == '/patient/dashboard'


def test_health_check(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'healthy'


def test_api_info(client):
    response = client.get('/api')
    assert response.status_code == 200
    assert 'endpoints' in response.get_json()


def test_unknown_api_path_returns_json_404(client):
    response = client.get('/api/does-not-exist')
    assert response.status_code == 404
    assert response.get_json() == {'error': 'Not found'}


def test_testing_config_does_not_touch_the_real_database(app):
    """Guards the incident in the fixes log: a probe once wrote into hospital.db."""
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'
    assert app.config['CACHE_TYPE'] == 'SimpleCache'
