"""
Business logic for sign up / log in. Keeps validation and password
handling out of the view functions so auth_views.py just wires HTTP
request/response to these calls.
"""
import re
from datetime import datetime

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import user as user_model

PH_MOBILE_RE = re.compile(r"^9\d{9}$")
NAME_RE = re.compile(r"^[A-Za-z\s.\-]+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_SEX = ("male", "female")
VALID_ROLES = ("health_worker", "medical_officer")
MIN_PASSWORD_LENGTH = 12


def _clean(form, key):
    return (form.get(key) or "").strip()


def validate_signup(form):
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
    birthday = _clean(form, "birthday")
    sex = _clean(form, "sex")
    role = _clean(form, "role")
    facility = _clean(form, "facility")
    barangay = _clean(form, "barangay")
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
    if not barangay:
        errors.append("Please select an assigned barangay.")

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if not terms:
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
        "barangay": barangay,
    }
    return errors, cleaned, password


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

    if not user or not password_ok:
        return None, "Invalid email or password."

    user_status = user["status"]
    if current_app.config.get("REQUIRE_ADMIN_APPROVAL", True) and user_status != "approved":
        if user_status == "pending":
            return None, "Your account is still awaiting admin approval."
        return None, "Your account access has been denied. Contact your LHU administrator."

    user_model.update_last_login(user["id"])
    return user, None
