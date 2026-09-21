"""
User data-access functions.

Every query is a plain, parameterized SQL string (never string-formatted
with user input) run through sqlite3. Parameterization is what keeps raw
SQL safe from injection -- always pass values via the `?` placeholders,
never f-strings/.format()/% into the query text.
"""
import sqlite3

from app.db import get_db
from app.constants import BARANGAYS


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
        "rhui": "LHU I",
        "rhuii": "LHU II",
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


def display_status_from_db(status):
    if status == "approved":
        return "Approved"
    if status == "pending":
        return "Pending"
    if status == "rejected":
        return "Rejected"
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
            email, phone, role, facility, barangay,
            password_hash, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            data["barangay"],
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
                    email, phone, role, facility, barangay,
                    password_hash, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    row["barangay"],
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


def get_staff_records():
    """Return user records in the shape expected by the Data Management table."""
    db = get_db()
    rows = db.execute(
        """
        SELECT id, first_name, middle_name, last_name, email, phone, role,
               facility, barangay, status, created_at
        FROM users
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()

    employees = []
    for row in rows:
        name = " ".join(part for part in [row["first_name"], row["middle_name"], row["last_name"]] if part)
        employees.append(
            {
                "id": f"EMP-{row['id']:05d}",
                "name": name,
                "email": row["email"],
                "role": display_role_from_db(row["role"]),
                "station": display_facility_from_db(row["facility"]),
                "contact": row["phone"],
                "status": display_status_from_db(row["status"]),
                "date_added": row["created_at"],
            }
        )
    return employees


def get_employee_by_id(employee_id):
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
        "barangay": display_barangay_from_db(user["barangay"]),
        "contact": user["phone"],
        "status": display_status_from_db(user["status"]),
        "date_added": user["created_at"],
        "last_login_at": user["last_login_at"],
    }


def update_user_role(employee_id, role_name):
    user = get_user_by_employee_id(employee_id)
    if user is None:
        return False
    db_role = db_role_from_display(role_name)
    if not db_role:
        return False
    db = get_db()
    db.execute(
        "UPDATE users SET role = ? WHERE id = ?",
        (db_role, user["id"]),
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
            "facility": "rhui",
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
            "facility": "rhui",
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
            "facility": "rhuii",
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
    """Helper for admin approval/rejection (call from a shell or CLI for now)."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = ? WHERE id = ?",
        (status, user_id),
    )
    db.commit()


def delete_user_by_employee_id(employee_id):
    user = get_user_by_employee_id(employee_id)
    if user is None:
        return False
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    db.commit()
    return True
