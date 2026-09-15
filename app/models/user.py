"""
User data-access functions.

Every query is a plain, parameterized SQL string (never string-formatted
with user input) run through sqlite3. Parameterization is what keeps raw
SQL safe from injection -- always pass values via the `?` placeholders,
never f-strings/.format()/% into the query text.
"""
from app.db import get_db


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


def update_last_login(user_id):
    db = get_db()
    db.execute(
        "UPDATE users SET last_login_at = datetime('now') WHERE id = ?",
        (user_id,),
    )
    db.commit()


def set_status(user_id, status):
    """Helper for admin approval/rejection (call from a shell or CLI for now)."""
    db = get_db()
    db.execute(
        "UPDATE users SET status = ? WHERE id = ?",
        (status, user_id),
    )
    db.commit()
