"""The single Flask-Caching instance, plus the cache keys the app uses.

Import ``cache`` from this module - never construct another ``Cache()``. ``app.py``
owns the ``init_app`` call; everything else just imports and uses it. Keeping the
instance here (rather than in ``app.py``) means the blueprints can import it at module
level without a circular import back into the application factory.
"""

from flask_caching import Cache

cache = Cache()

# Cached list of departments with their doctor counts, written by
# routes/patient.py::get_departments. Any change to a doctor's department,
# active flag, or existence invalidates it.
DEPARTMENTS_KEY = 'all_departments'


def invalidate_departments():
    """Drop the cached department list.

    Call after anything that changes which doctors belong to which department, or
    whether they are active - the cached payload carries per-department doctor counts.
    """
    cache.delete(DEPARTMENTS_KEY)
