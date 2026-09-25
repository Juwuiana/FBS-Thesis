"""
Site-wide settings, stored as simple key/value rows in app_settings.
Used for things like the admin-configurable session timeout.
"""
from app.db import get_db

SESSION_TIMEOUT_KEY = "session_timeout_minutes"
DEFAULT_SESSION_TIMEOUT_MINUTES = 30
DATA_RETENTION_KEY = "data_retention_days"
DEFAULT_DATA_RETENTION_DAYS = 365
ALLOWED_DATA_RETENTION_DAYS = (180, 365, 730, None)
MAX_LOGIN_ATTEMPTS_KEY = "max_login_attempts"
DEFAULT_MAX_LOGIN_ATTEMPTS = 5
ALLOWED_MAX_LOGIN_ATTEMPTS = (3, 5, 10)
VALID_ROLES = ("health_worker", "medical_officer", "patient")

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


def get_data_retention_days():
    raw = get_setting(DATA_RETENTION_KEY, DEFAULT_DATA_RETENTION_DAYS)
    if raw in (None, "", "None"):
        return None
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DATA_RETENTION_DAYS
    return days if days in ALLOWED_DATA_RETENTION_DAYS else DEFAULT_DATA_RETENTION_DAYS


def set_data_retention_days(days):
    if days not in ALLOWED_DATA_RETENTION_DAYS:
        raise ValueError(f"{days} is not an allowed data retention value.")
    set_setting(DATA_RETENTION_KEY, days if days is not None else "")


def _role_setting_key(prefix, role):
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {role}")
    return f"{prefix}:{role}"


def is_role_login_enabled(role):
    raw = get_setting(_role_setting_key("role_login_enabled", role), "1")
    return raw != "0"


def set_role_login_enabled(role, enabled):
    if role == "medical_officer" and not enabled:
        raise ValueError(
            "The medical_officer role cannot be disabled - this would lock every admin out of the system."
        )
    set_setting(_role_setting_key("role_login_enabled", role), "1" if enabled else "0")


def is_role_export_enabled(role):
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role: {role}")
    if role == "medical_officer":
        return True
    raw = get_setting(_role_setting_key("role_export_enabled", role), "1")
    return raw != "0"


def set_role_export_enabled(role, enabled):
    if role not in ("health_worker", "patient"):
        raise ValueError("Export permission can only be toggled for health_worker or patient roles.")
    set_setting(_role_setting_key("role_export_enabled", role), "1" if enabled else "0")


def get_security_version(role):
    raw = get_setting(_role_setting_key("security_version", role), 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def bump_security_version(role):
    version = get_security_version(role) + 1
    set_setting(_role_setting_key("security_version", role), version)
    return version


def get_max_login_attempts():
    raw = get_setting(MAX_LOGIN_ATTEMPTS_KEY, DEFAULT_MAX_LOGIN_ATTEMPTS)
    try:
        attempts = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_LOGIN_ATTEMPTS
    return attempts if attempts in ALLOWED_MAX_LOGIN_ATTEMPTS else DEFAULT_MAX_LOGIN_ATTEMPTS


def set_max_login_attempts(attempts):
    if attempts not in ALLOWED_MAX_LOGIN_ATTEMPTS:
        raise ValueError(f"{attempts} is not an allowed maximum login attempt value.")
    set_setting(MAX_LOGIN_ATTEMPTS_KEY, attempts)