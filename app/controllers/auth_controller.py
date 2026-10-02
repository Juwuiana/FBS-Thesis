"""
Business logic for sign up / log in. Keeps validation and password
handling out of the view functions so auth_views.py just wires HTTP
request/response to these calls.
"""
import re
import secrets
from datetime import datetime

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db
from app.models import audit_model, lookup_model, settings as settings_model, user as user_model

PH_MOBILE_RE = re.compile(r"^9\d{9}$")
NAME_RE = re.compile(r"^[A-Za-z\s.\-]+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_SEX = ("male", "female")
VALID_ROLES = ("health_worker", "medical_officer")
MIN_PASSWORD_LENGTH = 12
_PASSWORD_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def generate_temp_password(length: int = 10) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _clean(form, key):
    return (form.get(key) or "").strip()


def normalize_phone(phone):
    normalized = (phone or "").strip().replace(" ", "").replace("-", "")
    for prefix in ("+63", "63", "0"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized


def normalize_import_birthday(birthday):
    """Convert common spreadsheet date output to the stored ISO format."""
    value = (birthday or "").strip()
    for date_format in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return value


def validate_profile_fields(form, require_terms=False, normalize_phone_input=False):
    """
    Validate the sign-up form. Returns (errors, cleaned_fields, password).
    `errors` is a list of user-facing strings; empty list means valid.
    """
    errors = []

    first_name = _clean(form, "first_name")
    middle_name = _clean(form, "middle_name")
    last_name = _clean(form, "last_name")
    email = _clean(form, "email").lower()
    phone = _clean(form, "phone")
    if normalize_phone_input:
        phone = normalize_phone(phone)
    birthday = _clean(form, "birthday")
    sex = _clean(form, "sex")
    role = _clean(form, "role")
    facility = _clean(form, "facility")
    # Region/city/barangay come from the PSGC cascade (psgc_cascade.js) --
    # barangay_code is authoritative; barangay_name alone is only trusted
    # for the "type it in" fallback used when a city has no PSGC barangay
    # list. Resolving by bare name otherwise is unsafe: barangay names
    # collide constantly nationwide (e.g. over 600 barangays are named
    # "Poblacion"), so a name with no code can never safely identify one.
    barangay_code = _clean(form, "barangay_code")
    barangay_name = _clean(form, "barangay_name")
    city_code = _clean(form, "city_code")
    city_name = _clean(form, "city_name")
    region_code = _clean(form, "region_code")
    region_name = _clean(form, "region_name")
    password = form.get("password") or ""
    confirm_password = form.get("confirm_password") or ""
    terms = form.get("terms")

    if not first_name or not NAME_RE.match(first_name):
        errors.append("First name is required and must contain letters only.")
    if not last_name or not NAME_RE.match(last_name):
        errors.append("Last name is required and must contain letters only.")
    if middle_name and not NAME_RE.match(middle_name):
        errors.append("Middle name must contain letters only.")

    if not email or not EMAIL_RE.match(email):
        errors.append("A valid email address is required.")

    if not phone or not PH_MOBILE_RE.match(phone):
        errors.append("Enter a valid 10-digit mobile number starting with 9.")

    if not birthday:
        errors.append("Birthday is required.")
    else:
        try:
            bday = datetime.strptime(birthday, "%Y-%m-%d").date()
            age_days = (datetime.utcnow().date() - bday).days
            if age_days < 0:
                errors.append("Birthday cannot be in the future.")
            elif age_days // 365 < 18:
                errors.append("You must be at least 18 years old to register.")
        except ValueError:
            errors.append("Birthday is invalid.")

    if sex not in VALID_SEX:
        errors.append("Please select a sex.")
    if role not in VALID_ROLES:
        errors.append("Please select a valid role.")
    if not facility:
        errors.append("Please select a health facility.")

    barangay_id = None
    if barangay_code and barangay_name:
        barangay_id = lookup_model.get_or_create_barangay(
            barangay_code, barangay_name, city_code, city_name, region_code, region_name
        )
    elif barangay_name:
        # Manual-entry fallback (no PSGC code available) -- also used by
        # the staff CSV bulk import, which only ever has a bare name.
        barangay_id = lookup_model.get_or_create_barangay_by_name(barangay_name)
    if barangay_id is None:
        errors.append("Please select an assigned barangay.")

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if require_terms and not terms:
        errors.append("You must agree to the Terms of Use and Privacy Policy.")

    # Only hit the DB for a duplicate-email check once the email itself is
    # well-formed, to avoid a wasted query on obviously bad input.
    if email and EMAIL_RE.match(email) and user_model.email_exists(email):
        errors.append("An account with this email already exists.")

    cleaned = {
        "first_name": first_name,
        "middle_name": middle_name or None,
        "last_name": last_name,
        "birthday": birthday,
        "sex": sex,
        "email": email,
        "phone": phone,
        "role": role,
        "facility": facility,
        "barangay_id": barangay_id,
        "barangay": barangay_name or None,  # legacy text column, display-only now
    }
    return errors, cleaned, password


def validate_signup(form):
    return validate_profile_fields(form, require_terms=True)


def register_user(form):
    """
    Validate + create a user. Returns (user_id, errors).
    On failure, user_id is None and errors is a non-empty list.
    """
    errors, cleaned, password = validate_signup(form)
    if errors:
        return None, errors

    status = "pending" if current_app.config.get("REQUIRE_ADMIN_APPROVAL", True) else "approved"
    password_hash = generate_password_hash(password)
    user_id = user_model.create_user(cleaned, password_hash, status=status)
    return user_id, []


def authenticate(email, password):
    """
    Check credentials. Returns (user_row, error_message).
    On success, error_message is None. On failure, user_row is None.
    """
    email = (email or "").strip().lower()
    password = password or ""

    if not email or not password:
        return None, "Please enter both email and password."

    user = user_model.get_user_by_email(email)

    # Always run check_password_hash even when the user doesn't exist, using
    # a fixed dummy hash, so login takes the same amount of time either way
    # and doesn't leak whether an email is registered via response timing.
    dummy_hash = "pbkdf2:sha256:600000$00000000000000000000000000000000"
    stored_hash = user["password_hash"] if user else dummy_hash
    password_ok = check_password_hash(stored_hash, password)

    if not user:
        return None, "Invalid email or password."

    if not password_ok:
        user_model.increment_failed_login_attempts(user["id"])
        user = user_model.get_user_by_id(user["id"])
        max_attempts = settings_model.get_max_login_attempts()
        if user["failed_login_attempts"] >= max_attempts:
            user_model.set_suspended(user["id"], True)
            audit_model.log_event(
                get_db(), user_id=user["id"], user_name=user["email"], role=user["role"],
                action=f"Account suspended after {max_attempts} failed login attempts: {email}",
                ip_address=None, severity="Critical",
            )
            return None, (
                "Too many failed attempts. Your account has been suspended - "
                "contact your LHU administrator."
            )
        return None, "Invalid email or password."

    if user["is_suspended"]:
        return None, "Your account has been suspended. Contact your LHU administrator."

    user_status = user["status"]
    if current_app.config.get("REQUIRE_ADMIN_APPROVAL", True) and user_status != "approved":
        if user_status == "pending":
            return None, "Your account is still awaiting admin approval."
        if user_status == "recovery":
            return None, "Your account is awaiting a password reset from an administrator."
        return None, "Your account access has been denied. Contact your LHU administrator."

    if not settings_model.is_role_login_enabled(user["role"]):
        return None, "Logins for this role have been temporarily disabled by an administrator."

    user_model.reset_failed_login_attempts(user["id"])
    user_model.update_last_login(user["id"])
    return user, None


def change_own_password(user_id, form):
    user = user_model.get_user_by_id(user_id)
    if user is None:
        return ["Your account could not be found."]

    current_password = form.get("current_password") or ""
    new_password = form.get("new_password") or ""
    confirm_password = form.get("confirm_password") or ""
    errors = []

    if not check_password_hash(user["password_hash"], current_password):
        errors.append("Current password is incorrect.")
    if len(new_password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if new_password != confirm_password:
        errors.append("Passwords do not match.")
    if new_password == current_password:
        errors.append("New password must be different from your current password.")

    if not errors:
        user_model.update_password(user_id, generate_password_hash(new_password))
    return errors