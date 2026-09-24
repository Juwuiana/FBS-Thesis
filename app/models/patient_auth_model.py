"""
Patient portal authentication: credential issuance and login
"""
import secrets
from werkzeug.security import check_password_hash, generate_password_hash
from app.models.db import get_connection

# No 0/O/1/l/I -- avoids handwriting/reading mistakes on a printed slip.
_PASSWORD_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def generate_temp_password(length: int = 10) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def issue_patient_credentials(patient_id: int, staff_id: int | None = None) -> str:
    """
    (Re)generate portal credentials for a patient. Returns the plaintext
    password ONCE -- it is never stored or logged, only handed back to the
    caller to display to the issuing staff member for handoff to the patient.
    Safe to call again later as a "reset password" action.
    """
    temp_password = generate_temp_password()
    password_hash = generate_password_hash(temp_password)
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE patients
            SET password_hash = ?, must_change_password = 1,
                portal_activated_at = NULL,
                credentials_issued_by_staff_id = ?,
                credentials_issued_at = datetime('now')
            WHERE id = ?
            """,
            (password_hash, staff_id, patient_id),
        )
        conn.commit()
    finally:
        conn.close()
    return temp_password


def authenticate_patient(patient_code: str, password: str):
    """Returns (patient_row, error_message), same shape as auth_controller.authenticate()."""
    patient_code = (patient_code or "").strip().upper()
    password = password or ""

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM patients WHERE patient_code = ? AND deleted_at IS NULL",
            (patient_code,),
        ).fetchone()
    finally:
        conn.close()

    dummy_hash = "pbkdf2:sha256:600000$00000000000000000000000000000000"
    stored_hash = row["password_hash"] if row and row["password_hash"] else dummy_hash
    password_ok = check_password_hash(stored_hash, password)

    if not row or not row["password_hash"] or not password_ok:
        return None, "Invalid patient ID or password."
    return row, None


def set_patient_password(patient_id: int, new_password: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE patients
            SET password_hash = ?, must_change_password = 0,
                portal_activated_at = COALESCE(portal_activated_at, datetime('now'))
            WHERE id = ?
            """,
            (generate_password_hash(new_password), patient_id),
        )
        conn.commit()
    finally:
        conn.close()