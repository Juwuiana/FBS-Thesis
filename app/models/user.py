"""
User data-access functions.

Every query is a plain, parameterized SQL string (never string-formatted
with user input) run through sqlite3. Parameterization is what keeps raw
SQL safe from injection -- always pass values via the `?` placeholders,
never f-strings/.format()/% into the query text.
"""
import secrets
import sqlite3
from datetime import datetime, timezone

from app.db import get_db
from app.constants import BARANGAYS, ROLE_MAP
from app.models import lookup_model


def display_role_from_db(role):
    if role == "medical_officer":
        return "Health Officer"
    if role == "health_worker":
        return "LHU Nurse"
    return "Health Officer" if role else "Staff"


def db_role_from_display(role_name):
    role_lookup = {
        "Admin": "medical_officer",
        "Health Officer": "medical_officer",
        "LHU Nurse": "health_worker",
        "Encoder": "health_worker",
    }
    return role_lookup.get(role_name.strip(), None)


def display_facility_from_db(facility):
    labels = {
        "lhui": "LHU I",
        "lhuii": "LHU II",
    }
    return labels.get((facility or "").lower(), (facility or "Unknown Facility").title())


def display_sex_from_db(sex):
    return {"male": "Male", "female": "Female"}.get(
        (sex or "").lower(), (sex or "Unknown").title()
    )


def display_barangay_from_db(barangay):
    labels = dict(BARANGAYS)
    return labels.get(
        (barangay or "").lower(), (barangay or "Unknown Barangay").title()
    )


def display_staff_barangay(user_row):
    """
    Prefer the linked barangays row (users.barangay_id, added in 0026,
    resolved via the PSGC region/city/barangay cascade). Falls back to the
    legacy free-text slug only for rows that predate that column.
    """
    barangay_id = user_row["barangay_id"] if "barangay_id" in user_row.keys() else None
    if barangay_id:
        name = lookup_model.get_barangay_name_by_id(barangay_id)
        if name:
            return name
    return display_barangay_from_db(user_row["barangay"])


def display_status_from_db(status):
    if status == "approved":
        return "Approved"
    if status == "pending":
        return "Pending"
    if status == "rejected":
        return "Rejected"
    if status == "recovery":
        return "Password Recovery"
    return "Pending"


def get_user_by_email(email):
    db = get_db()
    return db.execute(
        "SELECT * FROM users WHERE email = ?",
        (email.strip().lower(),),
    ).fetchone()


def get_user_by_id(user_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def email_exists(email):
    return get_user_by_email(email) is not None


def create_user(data, password_hash, status="pending"):
    """
    data: dict with keys first_name, middle_name, last_name, birthday, sex,
          email, phone, role, facility, barangay
    Returns the new user's id.
    """
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO users (
            first_name, middle_name, last_name, birthday, sex,
            email, phone, role, facility, barangay, barangay_id,
            password_hash, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["first_name"],
            data.get("middle_name") or None,
            data["last_name"],
            data["birthday"],
            data["sex"],
            data["email"].strip().lower(),
            data["phone"],
            data["role"],
            data["facility"],
            data.get("barangay"),
            data.get("barangay_id"),
            password_hash,
            status,
        ),
    )
    db.commit()
    return cur.lastrowid


def create_users_bulk(rows):
    """Insert validated users in one transaction."""
    db = get_db()
    try:
        for row in rows:
            db.execute(
                """
                INSERT INTO users (
                    first_name, middle_name, last_name, birthday, sex,
                    email, phone, role, facility, barangay, barangay_id,
                    password_hash, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["first_name"],
                    row.get("middle_name") or None,
                    row["last_name"],
                    row["birthday"],
                    row["sex"],
                    row["email"].strip().lower(),
                    row["phone"],
                    row["role"],
                    row["facility"],
                    row.get("barangay"),
                    row.get("barangay_id"),
                    row["password_hash"],
                    "approved",
                ),
            )
        db.commit()
    except sqlite3.Error:
        db.rollback()
        raise


def update_last_login(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET last_login_at = datetime('now') WHERE id = ?",
        (user_id,),
    )
    db.commit()


def increment_failed_login_attempts(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE id = ?",
        (user_id,),
    )
    db.commit()


def reset_failed_login_attempts(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET failed_login_attempts = 0 WHERE id = ?",
        (user_id,),
    )
    db.commit()


def update_password(user_id, password_hash):
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, active_session_token = NULL, active_session_last_seen = NULL WHERE id = ?",
        (password_hash, user_id),
    )
    db.commit()


def start_session(user_id):
    """Issue a new single-session token (replacing any previous one)."""
    token = secrets.token_urlsafe(32)
    db = get_db()
    db.execute(
        "UPDATE users SET active_session_token = ?, active_session_last_seen = ? WHERE id = ?",
        (token, datetime.now(timezone.utc).isoformat(), user_id),
    )
    db.commit()
    return token


def clear_session(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET active_session_token = NULL, active_session_last_seen = NULL WHERE id = ?",
        (user_id,),
    )
    db.commit()


def clear_sessions_for_role(role):
    db = get_db()
    db.execute(
        "UPDATE users SET active_session_token = NULL, active_session_last_seen = NULL WHERE role = ?",
        (role,),
    )
    db.commit()


def touch_session(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET active_session_last_seen = ? WHERE id = ? AND active_session_token IS NOT NULL",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    db.commit()


def get_active_session_state(user_id):
    """Return {"token", "last_seen"} (last_seen is an aware datetime or None), or None if no session."""
    row = get_db().execute(
        "SELECT active_session_token, active_session_last_seen FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None or not row["active_session_token"]:
        return None
    last_seen = None
    if row["active_session_last_seen"]:
        try:
            last_seen = datetime.fromisoformat(row["active_session_last_seen"])
        except ValueError:
            last_seen = None
    return {"token": row["active_session_token"], "last_seen": last_seen}


def update_avatar(user_id, filename):
    db = get_db()
    db.execute(
        "UPDATE users SET avatar_filename = ? WHERE id = ?",
        (filename, user_id),
    )
    db.commit()


def get_staff_records():
    """Return user records in the shape expected by the Data Management table."""
    from app.models import settings as settings_model

    db = get_db()
    max_login_attempts = settings_model.get_max_login_attempts()
    rows = db.execute(
        """
        SELECT id, first_name, middle_name, last_name, email, phone, role,
               facility, barangay, status, created_at, failed_login_attempts,
               is_suspended
        FROM users
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()

    employees = []
    for row in rows:
        name = " ".join(part for part in [row["first_name"], row["middle_name"], row["last_name"]] if part)
        is_suspended = bool(row["is_suspended"])
        is_locked = (
            row["status"] == "recovery"
            and row["failed_login_attempts"] >= max_login_attempts
        )
        employees.append(
            {
                "id": f"EMP-{row['id']:05d}",
                "name": name,
                "email": row["email"],
                "role": display_role_from_db(row["role"]),
                "station": display_facility_from_db(row["facility"]),
                "contact": row["phone"],
                "status": "Suspended" if is_suspended else display_status_from_db(row["status"]),
                "is_locked": is_locked,
                "is_password_recovery": row["status"] == "recovery" and not is_suspended,
                "is_suspended": is_suspended,
                "date_added": row["created_at"],
            }
        )
    return employees


def get_employee_by_id(employee_id):
    from app.models import settings as settings_model

    if isinstance(employee_id, str):
        employee_id = employee_id.strip()
        if employee_id.upper().startswith("EMP-"):
            employee_id = employee_id.split("-", 1)[1]
    try:
        user_id = int(employee_id)
    except (TypeError, ValueError):
        return None
    user = get_user_by_id(user_id)
    if not user:
        return None
    is_suspended = bool(user["is_suspended"])
    is_locked = (
        user["status"] == "recovery"
        and user["failed_login_attempts"] >= settings_model.get_max_login_attempts()
    )
    return {
        "id": f"EMP-{user['id']:05d}",
        "name": " ".join(part for part in [user["first_name"], user["middle_name"], user["last_name"]] if part),
        "first_name": user["first_name"],
        "middle_name": user["middle_name"],
        "last_name": user["last_name"],
        "birthday": user["birthday"],
        "sex": display_sex_from_db(user["sex"]),
        "email": user["email"],
        "role": display_role_from_db(user["role"]),
        "station": display_facility_from_db(user["facility"]),
        "facility": user["facility"],
        "barangay": display_staff_barangay(user),
        "barangay_id": user["barangay_id"],
        "contact": user["phone"],
        "phone": user["phone"],
        "avatar_filename": user["avatar_filename"],
        "status": "Suspended" if is_suspended else display_status_from_db(user["status"]),
        "is_locked": is_locked,
        "is_suspended": is_suspended,
        "date_added": user["created_at"],
        "last_login_at": user["last_login_at"],
    }


def update_staff_details(employee_id, facility, phone, barangay_id, role):
    user = get_user_by_employee_id(employee_id)
    db_role = ROLE_MAP.get(role)
    if user is None or not db_role:
        return False
    db = get_db()
    db.execute(
        "UPDATE users SET role = ?, facility = ?, phone = ?, barangay_id = ?, "
        "active_session_token = CASE WHEN role != ? THEN NULL ELSE active_session_token END, "
        "active_session_last_seen = CASE WHEN role != ? THEN NULL ELSE active_session_last_seen END "
        "WHERE id = ?",
        (db_role, facility, phone, barangay_id, db_role, db_role, user["id"]),
    )
    db.commit()
    return True


def get_user_by_employee_id(employee_id):
    if isinstance(employee_id, str):
        employee_id = employee_id.strip()
        if employee_id.upper().startswith("EMP-"):
            employee_id = employee_id.split("-", 1)[1]
    try:
        return get_user_by_id(int(employee_id))
    except (TypeError, ValueError):
        return None


def seed_demo_users():
    """Create a few dummy approved users when the database is empty."""
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0:
        return

    from werkzeug.security import generate_password_hash

    demo_users = [
        {
            "first_name": "Linda",
            "middle_name": "M.",
            "last_name": "Walker",
            "birthday": "1987-04-12",
            "sex": "female",
            "email": "l.walker@lhu.gov.ph",
            "phone": "9171234567",
            "role": "medical_officer",
            "facility": "lhui",
            "barangay": "aplaya",
            "status": "approved",
            "password": "Password123!",
        },
        {
            "first_name": "Kurt",
            "middle_name": "P.",
            "last_name": "Pernia",
            "birthday": "1992-02-15",
            "sex": "male",
            "email": "k.pernia@lhu.gov.ph",
            "phone": "9182345678",
            "role": "health_worker",
            "facility": "lhui",
            "barangay": "market_area",
            "status": "approved",
            "password": "Password123!",
        },
        {
            "first_name": "Clarise",
            "middle_name": "A.",
            "last_name": "Espiritu",
            "birthday": "1989-07-08",
            "sex": "female",
            "email": "c.espiritu@lhu.gov.ph",
            "phone": "9193456789",
            "role": "medical_officer",
            "facility": "lhuii",
            "barangay": "tagapo",
            "status": "approved",
            "password": "Password123!",
        },
    ]

    for user_data in demo_users:
        create_user(
            {
                "first_name": user_data["first_name"],
                "middle_name": user_data["middle_name"],
                "last_name": user_data["last_name"],
                "birthday": user_data["birthday"],
                "sex": user_data["sex"],
                "email": user_data["email"],
                "phone": user_data["phone"],
                "role": user_data["role"],
                "facility": user_data["facility"],
                "barangay": user_data["barangay"],
            },
            generate_password_hash(user_data["password"]),
            status=user_data["status"],
        )


def set_status(user_id, status):
    """Update an account status."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = ?, "
        "active_session_token = CASE WHEN ? = 'approved' THEN active_session_token ELSE NULL END, "
        "active_session_last_seen = CASE WHEN ? = 'approved' THEN active_session_last_seen ELSE NULL END "
        "WHERE id = ?",
        (status, status, status, user_id),
    )
    db.commit()


def reset_password(user_id, password_hash, status="approved"):
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, status = ?, failed_login_attempts = 0, is_suspended = 0, "
        "active_session_token = NULL, active_session_last_seen = NULL WHERE id = ?",
        (password_hash, status, user_id),
    )
    db.commit()


def unlock_user(user_id):
    db = get_db()
    cursor = db.execute(
        "UPDATE users SET status = ?, failed_login_attempts = 0, is_suspended = 0 WHERE id = ?",
        ("approved", user_id),
    )
    db.commit()
    return cursor.rowcount > 0


def set_suspended(user_id, suspended: bool):
    db = get_db()
    flag = 1 if suspended else 0
    cursor = db.execute(
        "UPDATE users SET is_suspended = ?, "
        "failed_login_attempts = CASE WHEN ? = 0 THEN 0 ELSE failed_login_attempts END, "
        "active_session_token = CASE WHEN ? = 0 THEN active_session_token ELSE NULL END, "
        "active_session_last_seen = CASE WHEN ? = 0 THEN active_session_last_seen ELSE NULL END "
        "WHERE id = ?",
        (flag, flag, flag, flag, user_id),
    )
    db.commit()
    return cursor.rowcount > 0


def delete_user_by_employee_id(employee_id):
    user = get_user_by_employee_id(employee_id)
    if user is None:
        return False
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    db.commit()
    return True