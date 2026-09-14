"""
app/rate_limit.py 

this is IP-based only dahil walang login

"""
import time
from functools import wraps
from flask import request, jsonify, abort

_hits: dict[str, list[float]] = {}


def rate_limit(max_calls: int, period_seconds: int):
    """
    Usage:
        @nurse_bp.route('/api/patients', methods=['POST'])
        @rate_limit(max_calls=10, period_seconds=60)
        def create_patient():
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            key = f"{request.remote_addr}:{view_func.__name__}"
            now = time.time()
            window_start = now - period_seconds

            hits = [t for t in _hits.get(key, []) if t > window_start]
            if len(hits) >= max_calls:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Too many requests. Please slow down."}), 429
                abort(429)

            hits.append(now)
            _hits[key] = hits
            return view_func(*args, **kwargs)
        return wrapped
    return decorator