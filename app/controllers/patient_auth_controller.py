"""
Business logic for patient portal login and password changes. Same split
as auth_controller.py: validation and hashing live here, patient_views.py
just wires HTTP to these calls, patient_model.py just runs SQL.
"""
"""
Business logic for patient portal login and password changes. Same split
as auth_controller.py: validation and hashing live here, patient_views.py
just wires HTTP to these calls, patient_model.py just runs SQL.
"""
import re
import secrets
from werkzeug.security import check_password_hash, generate_password_hash
from app.security_helpers import verify_password_or_dummy


from app.models import patient_model

_PASSWORD_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
MIN_NEW_PASSWORD_LENGTH = 8

_CODE_FORMAT_RE = re.compile(r"^([A-Z]+)(\d{4})(\d+)$")


def normalize_patient_code(raw_code: str) -> str:
    stripped = re.sub(r"[^A-Za-z0-9]", "", raw_code or "").upper()
    match = _CODE_FORMAT_RE.match(stripped)
    if not match:
        return stripped
    prefix, year, sequence = match.groups()
    return f"{prefix}-{year}-{sequence}"

def generate_temp_password(length: int = 10) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def issue_patient_credentials(patient_id: int, staff_id: int | None = None) -> str:
    """
    (Re)generate portal credentials for a patient. Returns the plaintext
    password ONCE -- it is never stored or logged, only handed back to the
    caller to display to the issuing staff member for handoff to the patient.
    """
    temp_password = generate_temp_password()
    patient_model.set_patient_credentials(
        patient_id, generate_password_hash(temp_password), staff_id=staff_id
    )
    return temp_password

def authenticate_patient(patient_code: str, password: str):
    patient_code = normalize_patient_code(patient_code)
    password = password or ""

    patient = patient_model.get_patient_by_code(patient_code)
    password_ok = verify_password_or_dummy(
        patient["password_hash"] if patient else None, password
    )

    if not patient or not patient["password_hash"] or not password_ok:
        return None, "Invalid patient ID or password."
    return patient, None

def change_patient_password(patient, form) -> list[str]:
    """Validate + apply a password change. Returns a list of errors (empty = success)."""
    new_password = form.get("new_password", "")
    confirm_password = form.get("confirm_password", "")
    errors = []

    if not patient["must_change_password"]:
        _, error = authenticate_patient(patient["patient_code"], form.get("current_password", ""))
        if error:
            errors.append("Current password is incorrect.")

    if len(new_password) < MIN_NEW_PASSWORD_LENGTH:
        errors.append(f"New password must be at least {MIN_NEW_PASSWORD_LENGTH} characters.")
    if new_password != confirm_password:
        errors.append("Passwords do not match.")

    if errors:
        return errors

    patient_model.update_patient_password(patient["id"], generate_password_hash(new_password))
    return []

def describe_user_agent(ua: str | None) -> str:
    if not ua:
        return "Unknown device"
    ua_l = ua.lower()

    if "iphone" in ua_l:
        os_name = "iPhone"
    elif "ipad" in ua_l:
        os_name = "iPad"
    elif "android" in ua_l:
        os_name = "Android"
    elif "windows" in ua_l:
        os_name = "Windows"
    elif "mac os" in ua_l or "macintosh" in ua_l:
        os_name = "Mac"
    else:
        os_name = "Unknown OS"

    if "edg/" in ua_l:
        browser = "Edge"
    elif "chrome/" in ua_l and "edg/" not in ua_l:
        browser = "Chrome"
    elif "firefox/" in ua_l:
        browser = "Firefox"
    elif "safari/" in ua_l and "chrome/" not in ua_l:
        browser = "Safari"
    else:
        browser = "Unknown browser"

    return f"{browser} on {os_name}"