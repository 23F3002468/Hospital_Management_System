"""Shared error helpers for the API blueprints."""

from flask import current_app, jsonify
from werkzeug.exceptions import HTTPException


def server_error(exc, message='Internal server error'):
    """Log an unhandled exception and return a client-safe 500.

    The traceback goes to the application log; the client only ever sees
    ``message``. Never pass exception text back to the caller - it leaks SQL
    fragments, filesystem paths and library internals.

    Deliberate aborts pass straight through. ``get_or_404`` and
    ``first_or_404`` raise ``NotFound``, which is an ``Exception`` like any
    other and so lands in the ``except Exception`` block that calls this
    helper. Swallowing it would turn every missing row into a 500 and log a
    traceback for what is a routine client error.
    """
    if isinstance(exc, HTTPException):
        raise exc

    current_app.logger.exception(exc)
    return jsonify({'error': message}), 500
