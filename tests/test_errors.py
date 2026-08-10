"""The shared 500 helper.

Regression cover for:
  #4  ``str(e)`` used to go straight to the client, carrying SQL fragments,
      bound parameters and filesystem paths - and nothing was logged
  #17 HTTPException must pass through instead of becoming a 500
"""

import logging

import pytest
from werkzeug.exceptions import NotFound

from routes.errors import server_error

LEAK_MARKERS = ['traceback', 'sqlite', 'redis', 'select ', 'c:\\', '/home/', 'password']


def test_server_error_returns_a_fixed_message(app):
    with app.test_request_context():
        response, status = server_error(RuntimeError('connection to sqlite:///secret.db failed'))
        assert status == 500
        assert response.get_json() == {'error': 'Internal server error'}


def test_server_error_accepts_a_custom_message(app):
    with app.test_request_context():
        response, status = server_error(RuntimeError('boom'), 'Could not start the export job')
        assert status == 500
        assert response.get_json()['error'] == 'Could not start the export job'


def test_server_error_logs_the_traceback(app, caplog):
    with app.test_request_context(), caplog.at_level(logging.ERROR):
        server_error(RuntimeError('diagnostic detail'))
    assert 'diagnostic detail' in caplog.text, 'the exception must survive in the log'


def test_server_error_reraises_http_exceptions(app):
    with app.test_request_context():
        with pytest.raises(NotFound):
            server_error(NotFound())


def test_an_unexpected_failure_does_not_leak_internals_over_http(
        app, patient_client, seed, monkeypatch):
    """Broker is down: the route must fail closed, saying nothing useful to a caller."""
    import celery_app

    def explode(*args, **kwargs):
        raise ConnectionError(
            "Error 10061 connecting to localhost:6379. "
            r"No connection could be made; see C:\Users\secret\.env")

    monkeypatch.setattr(celery_app.celery, 'send_task', explode)

    response = patient_client.post('/api/patient/export-treatment-history')
    assert response.status_code == 500
    assert response.get_json() == {'error': 'Could not start the export job'}

    body = response.get_data(as_text=True).lower()
    leaked = [marker for marker in LEAK_MARKERS if marker in body]
    assert not leaked, f'response leaked {leaked}'


def test_the_traceback_still_reaches_the_log(app, patient_client, seed, monkeypatch, caplog):
    import celery_app

    monkeypatch.setattr(celery_app.celery, 'send_task',
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError('broker down')))

    with caplog.at_level(logging.ERROR):
        patient_client.post('/api/patient/export-treatment-history')

    assert 'broker down' in caplog.text


def test_no_route_returns_raw_exception_text(app):
    """A cheap guard against the pattern coming back: grep the blueprints."""
    import pathlib

    routes_dir = pathlib.Path(app.root_path) / 'routes'
    offenders = [
        path.name for path in routes_dir.glob('*.py')
        if "jsonify({'error': str(e)})" in path.read_text(encoding='utf-8')
    ]
    assert not offenders, f'raw exception text returned to clients in {offenders}'
