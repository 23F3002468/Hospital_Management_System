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


# ---------------------------------------------------------------------------
# The development server must not be deployable
# ---------------------------------------------------------------------------

def test_app_run_does_not_hardcode_debug(app):
    """`app.run(debug=True, host='0.0.0.0')` served the Werkzeug debugger - an
    interactive Python console - to the whole network. Debug must come from the
    loaded config so ProductionConfig can switch it off.
    """
    import ast
    import pathlib

    tree = ast.parse(
        (pathlib.Path(app.root_path) / 'app.py').read_text(encoding='utf-8'))

    runs = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == 'run'
    ]
    assert runs, 'expected app.run() to still exist for local development'

    for call in runs:
        for keyword in call.keywords:
            if keyword.arg in ('debug', 'host'):
                assert not isinstance(keyword.value, ast.Constant), (
                    f'app.run({keyword.arg}=...) is a hardcoded literal at line '
                    f'{call.lineno}; it must be read from config or the environment'
                )


def test_production_config_has_debug_off():
    from config import ProductionConfig

    assert ProductionConfig.DEBUG is False
    assert ProductionConfig.TESTING is False


# ---------------------------------------------------------------------------
# Cookie hardening - the login lives in these cookies
# ---------------------------------------------------------------------------

def cookie_named(response, name):
    for header in response.headers.getlist('Set-Cookie'):
        if header.startswith(f'{name}='):
            return header
    return None


def test_session_cookie_is_httponly_and_samesite(client, seed):
    """SameSite is this app's only CSRF defence - there are no tokens."""
    response = client.post('/api/auth/login',
                           json={'username': 'pat1', 'password': 'pw'})
    cookie = cookie_named(response, 'session')
    assert cookie is not None, 'login did not set a session cookie'
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie


def test_remember_cookie_is_hardened_too(client, seed):
    """It outlives the browser session, so it matters more, not less."""
    response = client.post('/api/auth/login',
                           json={'username': 'pat1', 'password': 'pw', 'remember': True})
    cookie = cookie_named(response, 'remember_token')
    assert cookie is not None, 'remember=True did not set a remember cookie'
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie


def test_cookies_are_not_secure_in_development(app):
    """Development runs on plain http://localhost; a Secure cookie would be
    dropped by the browser and nobody could log in locally."""
    from config import DevelopmentConfig

    assert DevelopmentConfig.SESSION_COOKIE_SECURE is False


def test_production_marks_both_cookies_secure():
    from config import ProductionConfig

    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.REMEMBER_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
    assert ProductionConfig.REMEMBER_COOKIE_HTTPONLY is True
    assert ProductionConfig.SESSION_COOKIE_SAMESITE == 'Lax'
    assert ProductionConfig.REMEMBER_COOKIE_SAMESITE == 'Lax'


def test_session_lifetime_is_not_flasks_month_long_default():
    from datetime import timedelta

    from config import Config

    assert Config.PERMANENT_SESSION_LIFETIME <= timedelta(hours=24)


def test_proxy_headers_are_not_trusted_by_default(app):
    """X-Forwarded-* is spoofable by a direct client, so ProxyFix is opt-in."""
    from werkzeug.middleware.proxy_fix import ProxyFix

    assert not isinstance(app.wsgi_app, ProxyFix)
