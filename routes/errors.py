"""Shared error helpers for the API blueprints."""

from flask import current_app, jsonify


def server_error(exc, message='Internal server error'):
    """Log an unhandled exception and return a client-safe 500.

    The traceback goes to the application log; the client only ever sees
    ``message``. Never pass exception text back to the caller - it leaks SQL
    fragments, filesystem paths and library internals.
    """
    current_app.logger.exception(exc)
    return jsonify({'error': message}), 500
