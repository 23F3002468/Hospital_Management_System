"""Shared input validation for the API blueprints.

Lives next to routes/errors.py for the same reason: rules that more than one
blueprint needs belong in one place, or they drift. The password floor did
exactly that - change_password enforced six characters while register and
add_doctor enforced nothing at all, so the rule applied at the one moment a
user is least likely to pick a weak password and was skipped at the two moments
they are most likely to.
"""

MIN_PASSWORD_LENGTH = 8


def password_error(password):
    """Return a client-safe message if the password is unacceptable, else None.

    Length only, deliberately. Composition rules - a digit, a symbol, mixed
    case - push people towards predictable substitutions ("Password1!") without
    adding real entropy, and current NIST guidance recommends against them. A
    length floor is the check that actually costs an attacker something.
    """
    if not password:
        return 'Password is required'

    if len(password) < MIN_PASSWORD_LENGTH:
        return f'Password must be at least {MIN_PASSWORD_LENGTH} characters long'

    return None
