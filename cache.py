from flask_caching import Cache
from functools import wraps

cache = Cache()

def cached_route(timeout=300):
    """
    Decorator to cache route responses
    Usage: @cached_route(timeout=600)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            cache_key = f"route_{f.__name__}_{str(args)}_{str(kwargs)}"
            
            # Try to get from cache
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                return cached_response
            
            # Generate response
            response = f(*args, **kwargs)
            
            # Cache it
            cache.set(cache_key, response, timeout=timeout)
            
            return response
        return decorated_function
    return decorator