"""
Site-wide settings, stored as simple key/value rows in app_settings.
Used for things like the admin-configurable session timeout.
"""
from app.db import get_db

SESSION_TIMEOUT_KEY = "session_timeout_minutes"
DEFAULT_SESSION_TIMEOUT_MINUTES = 30

# Only these values are selectable from the Privacy & Security page.
# 1 minute is included so it's easy to test the timeout quickly;
# remove it once you're done testing if you don't want it in production.
ALLOWED_SESSION_TIMEOUTS = (1, 15, 30, 60)


def get_setting(key, default=None):
    db = get_db()
    row = db.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )
    db.commit()


def get_session_timeout_minutes():
    raw = get_setting(SESSION_TIMEOUT_KEY, DEFAULT_SESSION_TIMEOUT_MINUTES)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SESSION_TIMEOUT_MINUTES


def set_session_timeout_minutes(minutes):
    if minutes not in ALLOWED_SESSION_TIMEOUTS:
        raise ValueError(f"{minutes} is not an allowed session timeout value.")
    set_setting(SESSION_TIMEOUT_KEY, minutes)