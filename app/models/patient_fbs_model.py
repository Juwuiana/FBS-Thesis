"""
all reads/writes to `patient_fbs_entries` (patient self-reported FBS).

These rows are UNVERIFIED reference data. They never touch `lab_screenings`,
never feed the risk calculation, the FBS trend, the follow-up bell logic
(`fbs_score is not None`) or the CSV export. A nurse can only mark them
reviewed / flagged -- there is deliberately no "promote to clinical FBS" here.
"""
from app.models.db import get_connection

VALID_UNITS = ("mg_dl", "mmol_l")
VALID_FASTED = ("yes", "no", "unsure")
VALID_STATUSES = ("unreviewed", "reviewed", "flagged")

MMOL_TO_MGDL = 18.0182


def to_mg_dl(value: float, unit: str) -> float:
    return round(value * MMOL_TO_MGDL, 1) if unit == "mmol_l" else round(value, 1)


def _shape(row) -> dict:
    """Row -> dict, plus split date/time fields for the nurse card."""
    d = dict(row)
    stamp = d.get("entered_at") or ""
    d["date"] = stamp[:10]
    d["time"] = stamp[11:16] if len(stamp) >= 16 else ""
    return d


def create_entry(patient_id: int, visit_id: int | None, entered_value: float,
                 entered_unit: str, fasted: str) -> int:
    """fbs_mg_dl is always derived here, never trusted from the caller."""
    if entered_unit not in VALID_UNITS:
        raise ValueError("Invalid FBS unit.")
    if fasted not in VALID_FASTED:
        raise ValueError("Invalid fasting answer.")
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO patient_fbs_entries
                (patient_id, visit_id, fbs_mg_dl, entered_value, entered_unit, fasted)
            VALUES (?,?,?,?,?,?)
        """, (patient_id, visit_id, to_mg_dl(entered_value, entered_unit),
              entered_value, entered_unit, fasted))
        conn.commit()
        return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_entries_for_patient(patient_id: int, limit: int | None = None) -> list[dict]:
    """Newest first. Used by the patient portal and the nurse patient file."""
    sql = """
        SELECT * FROM patient_fbs_entries
        WHERE patient_id = ?
        ORDER BY entered_at DESC, id DESC
    """
    params = [patient_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_shape(r) for r in rows]


def list_entries_for_screening(patient_id: int, visit_id: int | None, limit: int = 10) -> list[dict]:
    """
    For the nurse screening card. Entries submitted WITH this visit (the
    patient's Add New Record) come first and carry linked=True; the rest are
    the patient's other recent entries.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT *, (visit_id IS NOT NULL AND visit_id = ?) AS linked
        FROM patient_fbs_entries
        WHERE patient_id = ?
        ORDER BY linked DESC, entered_at DESC, id DESC
        LIMIT ?
    """, (visit_id, patient_id, limit)).fetchall()
    conn.close()
    return [_shape(r) for r in rows]


def set_review_status(entry_id: int, patient_id: int, status: str,
                      staff_id: int | None = None) -> bool:
    """
    patient_id is checked so a nurse URL for patient A can't alter patient B's
    entry. Returns False when no matching row exists.
    """
    if status not in VALID_STATUSES:
        raise ValueError("Invalid review status.")
    reviewed = status != "unreviewed"
    conn = get_connection()
    try:
        cur = conn.execute("""
            UPDATE patient_fbs_entries
            SET review_status = ?,
                reviewed_by_staff_id = ?,
                reviewed_at = CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END
            WHERE id = ? AND patient_id = ?
        """, (status, staff_id if reviewed else None, int(reviewed), entry_id, patient_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_unreviewed(patient_id: int | None = None) -> int:
    """For a future nurse-bell badge (all patients when patient_id is None)."""
    conn = get_connection()
    if patient_id is None:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM patient_fbs_entries WHERE review_status = 'unreviewed'"
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM patient_fbs_entries WHERE review_status = 'unreviewed' AND patient_id = ?",
            (patient_id,),
        ).fetchone()
    conn.close()
    return row["n"]
