from flask_caching import Cache
from functools import wraps

cache = Cache()

def cached_route(timeout=300):
    """
    Decorator to cache route responses
    Usage: @cached_route(timeout=600)
    """
    cache.delete(DEPARTMENTS_KEY)
