"""
all reads/writes to `patients`

"""
from datetime import date
from app.models.db import get_connection


def _compute_age(birthdate_iso: str) -> int:
    b = date.fromisoformat(birthdate_iso)
    today = date.today()
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


def generate_next_patient_code(conn=None) -> str:
    """
    NNNN resets per year 
    """
    own_conn = conn is None
    conn = conn or get_connection()
    year = date.today().year
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM patients WHERE patient_code LIKE ?",
        (f"CAB-{year}-%",)
    ).fetchone()
    next_seq = row["n"] + 1
    if own_conn:
        conn.close()
    return f"CAB-{year}-{next_seq:04d}"


def create_patient(data: dict, staff_id: int | None = None) -> int:
    conn = get_connection()
    patient_code = generate_next_patient_code(conn)
    cur = conn.execute("""
        INSERT INTO patients (
            patient_code, last_name, first_name, middle_name,
            father_last_name, father_first_name, mother_last_name, mother_first_name,
            spouse_last_name, spouse_first_name, contact_number,
            birthdate, sex, civil_status, religion, occupation, education,
            barangay_id, address, phic_membership, phic_type, created_by_staff_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        patient_code, data["last_name"], data["first_name"], data.get("middle_name"),
        data.get("father_last_name"), data.get("father_first_name"),
        data.get("mother_last_name"), data.get("mother_first_name"),
        data.get("spouse_last_name"), data.get("spouse_first_name"), data.get("contact_number"),
        data["birthdate"], data["sex"], data.get("civil_status"), data.get("religion"),
        data.get("occupation"), data.get("education"), data.get("barangay_id"),
        data.get("address"), data.get("phic_membership"), data.get("phic_type"), staff_id
    ))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id

def get_patient_code_by_id(patient_id: int) -> str | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT patient_code FROM patients WHERE id = ?",
        (patient_id,)
    ).fetchone()
    conn.close()
    return row["patient_code"] if row else None

def get_patient_by_code(patient_code: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("""
        SELECT p.*, b.name AS barangay
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        WHERE p.patient_code = ?
    """, (patient_code,)).fetchone()
    conn.close()
    if row is None:
        return None
    patient = dict(row)
    patient["age"] = _compute_age(patient["birthdate"])
    patient["birthdate_display"] = date.fromisoformat(patient["birthdate"]).strftime("%B %d, %Y")
    return patient


def list_patients(barangay: str = None, entries_limit: int = None) -> list[dict]:
    conn = get_connection()
    sql = """
        SELECT p.id, p.patient_code, p.last_name, p.first_name, p.sex,
               p.birthdate, b.name AS barangay
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
    """
    params = []
    if barangay:
        sql += " WHERE b.name = ?"
        params.append(barangay)
    sql += " ORDER BY p.created_at DESC"
    if entries_limit:
        sql += " LIMIT ?"
        params.append(entries_limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["age"] = _compute_age(d["birthdate"])
        result.append(d)
    return result


def update_patient(patient_id: int, data: dict) -> None:
    if not data:
        return
    # Whitelist: column NAMES can't be parameterized with `?` (SQLite only
    # parameterizes values), so if `data` ever came straight from request
    # JSON we'd be one bad key away from breaking the query. The controller
    # must only pass through known field names -- this list is the guard.
    allowed = {
        "last_name", "first_name", "middle_name", "father_last_name",
        "father_first_name", "mother_last_name", "mother_first_name",
        "spouse_last_name", "spouse_first_name", "contact_number",
        "birthdate", "sex", "civil_status", "religion", "occupation",
        "education", "barangay_id", "address", "phic_membership", "phic_type",
    }
    data = {k: v for k, v in data.items() if k in allowed}
    if not data:
        return
    columns = ", ".join(f"{k} = ?" for k in data.keys())
    values = list(data.values()) + [patient_id]
    conn = get_connection()
    conn.execute(
        f"UPDATE patients SET {columns}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()

def list_patients_with_latest_screening(barangay=None, risk=None, date=None, entries_limit=None):
    conn = get_connection()

    conditions, params = ["p.deleted_at IS NULL"], []

    if barangay:
        conditions.append("b.name = ?")
        params.append(barangay)
    if risk:
        conditions.append("COALESCE(ls.final_risk_level, ls.preliminary_risk_level) = ?")
        params.append(risk)
    if date:
        conditions.append("DATE(v.assessment_date) = ?")
        params.append(date)

    sql = """
        SELECT p.patient_code, p.first_name, p.last_name, p.birthdate, p.sex,
               b.name AS barangay,
               v.assessment_date AS date,
               ls.fbs_mg_dl AS fbs,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        LEFT JOIN visits v ON v.patient_id = p.id
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
    """

    sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY p.created_at DESC"

    if entries_limit:
        sql += " LIMIT ?"
        params.append(entries_limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["age"] = _compute_age(d["birthdate"])
        result.append(d)
    return result

from datetime import date, datetime  # add datetime to the existing import


def soft_delete_patient(patient_id: int) -> None:
    """
    mapupunta patient sa recycle bin 

    """
    conn = get_connection()
    conn.execute("UPDATE patients SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()


def restore_patient(patient_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE patients SET deleted_at = NULL WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()


def purge_patient_permanently(patient_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()


def purge_expired_deleted_patients() -> int:
    """
    delete patients na lagpas 15 days na sa recycle bin

    """
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM patients WHERE deleted_at IS NOT NULL AND deleted_at <= datetime('now', '-15 days')"
    )
    conn.commit()
    purged = cur.rowcount
    conn.close()
    return purged


def list_deleted_patients() -> list[dict]:
    """Backs nurse_recycle_bin.html. days_remaining is clamped at 0 in
    case this renders in the gap before a purge has run."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.patient_code, p.last_name, p.first_name, p.deleted_at,
               b.name AS barangay
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        WHERE p.deleted_at IS NOT NULL
        ORDER BY p.deleted_at DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        deleted_dt = datetime.fromisoformat(d["deleted_at"])
        d["days_remaining"] = max(15 - (datetime.utcnow() - deleted_dt).days, 0)
        result.append(d)
    return result