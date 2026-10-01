"""
all reads/writes to `patients`

"""
import csv
import hashlib
import io
import re
from datetime import date
from app.db import get_db
from app.models.db import get_connection
from datetime import date, datetime  
import sqlite3
import openpyxl
from io import BytesIO
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import PatternFill, Font


def _compute_age(birthdate_iso: str) -> int:
    b = date.fromisoformat(birthdate_iso)
    today = date.today()
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


def generate_next_patient_code(conn=None) -> str:
    """
    NNNN resets per year. Uses MAX(sequence) rather than COUNT(*) so that
    deleting/purging a patient (recycle bin) never causes a stale row count
    to collide with a still-existing higher patient_code.
    """
    own_conn = conn is None
    conn = conn or get_connection()
    year = date.today().year
    prefix = f"SRCHO-{year}-"

    row = conn.execute(
        """
        SELECT MAX(CAST(SUBSTR(patient_code, LENGTH(?) + 1) AS INTEGER)) AS max_seq
        FROM patients
        WHERE patient_code LIKE ?
        """,
        (prefix, f"{prefix}%")
    ).fetchone()

    next_seq = (row["max_seq"] or 0) + 1

    if own_conn:
        conn.close()
    return f"{prefix}{next_seq:04d}"


def _normalize_name_part(s: str | None) -> str:
    """Lowercase and strip everything but letters, so 'Dela Cruz', 'dela  cruz',
    and 'DELACRUZ' all compare equal."""
    return re.sub(r"[^a-z]", "", (s or "").strip().lower())


def find_existing_patient_id(last_name: str, first_name: str, middle_name: str | None, birthdate: str) -> int | None:
    """
    Look for a patient already in the system with the same normalized
    last name, first name, middle name, and birthdate.

    Used by CSV import so a repeat visit for the same person attaches to
    their existing patient_code instead of minting a brand new one.
    Only compares against non-deleted patients.
    """
    conn = get_connection()
    try:
        candidates = conn.execute(
            """
            SELECT id, last_name, first_name, middle_name
            FROM patients
            WHERE birthdate = ? AND deleted_at IS NULL
            """,
            (birthdate,)
        ).fetchall()
    finally:
        conn.close()

    target = (
        _normalize_name_part(last_name),
        _normalize_name_part(first_name),
        _normalize_name_part(middle_name),
    )
    for c in candidates:
        candidate_key = (
            _normalize_name_part(c["last_name"]),
            _normalize_name_part(c["first_name"]),
            _normalize_name_part(c["middle_name"]),
        )
        if candidate_key == target:
            return c["id"]
    return None



def create_patient(data: dict, staff_id: int | None = None) -> int:
    max_attempts = 5
    last_error = None
    for attempt in range(max_attempts):
        conn = get_connection()
        try:
            patient_code = generate_next_patient_code(conn)
            cur = conn.execute("""
                INSERT INTO patients (
                    patient_code, last_name, first_name, middle_name,
                    father_last_name, father_first_name, mother_last_name, mother_first_name,
                    spouse_last_name, spouse_first_name, contact_number,
                    birthdate, sex, civil_status, religion, occupation, education,
                    barangay_id, address, phic_membership, phic_type, maiden_name, created_by_staff_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                patient_code, data["last_name"], data["first_name"], data.get("middle_name"),
                data.get("father_last_name"), data.get("father_first_name"),
                data.get("mother_last_name"), data.get("mother_first_name"),
                data.get("spouse_last_name"), data.get("spouse_first_name"), data.get("contact_number"),
                data["birthdate"], data["sex"], data.get("civil_status"), data.get("religion"),
                data.get("occupation"), data.get("education"), data.get("barangay_id"),
                data.get("address"), data.get("phic_membership"), data.get("phic_type"),
                data.get("maiden_name"), staff_id
            ))
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError as e:
            conn.rollback()
            last_error = str(e)
            if "patient_code" not in last_error:
                raise RuntimeError(f"Patient insert failed: {last_error}") from e
            continue
        finally:
            conn.close()
    raise RuntimeError(
        f"Could not generate a unique patient_code after {max_attempts} attempts "
        f"(last error: {last_error})"
    )

def get_patient_code_by_id(patient_id: int) -> str | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT patient_code FROM patients WHERE id = ?",
        (patient_id,)
    ).fetchone()
    conn.close()
    return row["patient_code"] if row else None

def format_location(patient: dict | None) -> str:
    """'Street, Barangay, City, Region' from a get_patient_by_* row, skipping blanks.
    Used for the before/after shown to a nurse when a patient changes their address."""
    if not patient:
        return ""
    parts = [patient.get("address"), patient.get("barangay"),
             patient.get("city_name"), patient.get("region_name")]
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def get_patient_by_code(patient_code: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("""
        SELECT p.*, b.name AS barangay,
               b.barangay_code, b.city_code, b.city_name,
               b.region_code, b.region_name
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

def get_patient_by_id(patient_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("""
        SELECT p.*, b.name AS barangay,
               b.barangay_code, b.city_code, b.city_name,
               b.region_code, b.region_name
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        WHERE p.id = ?
    """, (patient_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    patient = dict(row)
    patient["age"] = _compute_age(patient["birthdate"])
    patient["birthdate_display"] = date.fromisoformat(patient["birthdate"]).strftime("%B %d, %Y")
    return patient

def set_patient_credentials(patient_id: int, password_hash: str, staff_id: int | None = None) -> None:
    conn = get_connection()
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
    conn.close()


def update_patient_password(patient_id: int, password_hash: str) -> None:
    conn = get_connection()
    conn.execute(
        """
        UPDATE patients
        SET password_hash = ?, must_change_password = 0,
            portal_activated_at = COALESCE(portal_activated_at, datetime('now'))
        WHERE id = ?
        """,
        (password_hash, patient_id),
    )
    conn.commit()
    conn.close()

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
    sql += _patient_order_by(sort, direction)
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


def update_patient(patient_id: int, data: dict, allow_name_edit: bool = False, allow_last_name_edit: bool = False) -> None:
    if not data:
        return
    allowed = {
        "middle_name", "father_last_name",
        "father_first_name", "mother_last_name", "mother_first_name",
        "spouse_last_name", "spouse_first_name", "contact_number",
        "birthdate", "sex", "civil_status", "religion", "occupation",
        "education", "barangay_id", "address", "phic_membership", "phic_type",
        "maiden_name",
    }
    if allow_name_edit:
        allowed = allowed | {"last_name", "first_name"}
    elif allow_last_name_edit:
        allowed = allowed | {"last_name"}
    ignored_name_edit = not (allow_name_edit or allow_last_name_edit) and ("last_name" in data or "first_name" in data)
    data = {k: v for k, v in data.items() if k in allowed}
    if ignored_name_edit and not data:
        return
    if not data:
        return
    columns = ", ".join(f"{k} = ?" for k in data.keys())
    values = list(data.values()) + [patient_id]
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE patients SET {columns}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _patient_listing_filters(barangay=None, risk=None, date=None, q=None, status=None):
    """
    Shared WHERE-clause builder for list_patients_with_latest_screening and
    count_patients_with_latest_screening, so pagination's count and its
    page of rows can never drift out of sync with each other's filters.
    """
    conditions, params = ["p.deleted_at IS NULL"], []

    if barangay:
        conditions.append("b.name = ?")
        params.append(barangay)
    if risk:
        conditions.append("COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) = ?")
        params.append(risk)
    if date:
        conditions.append("DATE(v.assessment_date) = ?")
        params.append(date)
    if q:
        conditions.append("(p.last_name LIKE ? OR p.first_name LIKE ? OR p.patient_code LIKE ?)")
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    if status == "draft":
        conditions.append("COALESCE(v.status, '') = 'draft'")
    elif status == "awaiting_lab":
        conditions.append("v.id IS NOT NULL AND COALESCE(v.status, '') != 'draft' AND ls.id IS NULL")
    elif status == "needs_review":

        conditions.append("""
            EXISTS (
                SELECT 1 FROM visits v_rev
                WHERE v_rev.patient_id = p.id
                  AND v_rev.edited_by_patient_at IS NOT NULL
                  AND v_rev.edit_acknowledged_at IS NULL
            )
        """)
    return conditions, params


_PATIENT_LISTING_JOINS = """
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        LEFT JOIN visits v ON v.id = (
            SELECT v2.id FROM visits v2
            WHERE v2.patient_id = p.id
            ORDER BY v2.id DESC
            LIMIT 1
        )
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
"""


def count_patients_with_latest_screening(barangay=None, risk=None, date=None, q=None, status=None) -> int:
    conn = get_connection()
    conditions, params = _patient_listing_filters(barangay=barangay, risk=risk, date=date, q=q, status=status)
    sql = f"SELECT COUNT(*) AS n {_PATIENT_LISTING_JOINS} WHERE " + " AND ".join(conditions)
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row["n"] if row else 0


# Sortable columns for the Data Management table. The URL only ever supplies a
# KEY from this dict (a whitelist), never SQL, so there is no injection surface.
# Each value is (ORDER BY expressions, invert_direction). NULLs (e.g. a pending
# risk or a missing FBS) always sort last, whichever way the column is sorted.
_RISK_RANK = ("CASE COALESCE(ls.final_risk_level, ls.preliminary_risk_level, "
              "ls.model_predicted_risk_level) "
              "WHEN 'Low' THEN 1 WHEN 'Moderate' THEN 2 WHEN 'High' THEN 3 END")
_PATIENT_SORTS = {
    "patient_code": (["p.patient_code"], False),
    "name":         (["p.last_name COLLATE NOCASE", "p.first_name COLLATE NOCASE"], False),
    "age":          (["p.birthdate"], True),   # older = earlier birthdate, so flip
    "sex":          (["p.sex"], False),
    "fbs":          (["ls.fbs_mg_dl"], False),
    "risk":         ([_RISK_RANK], False),     # Low < Moderate < High, Pending last
    "date":         (["v.assessment_date"], False),
}
PATIENT_SORT_KEYS = frozenset(_PATIENT_SORTS)


def _patient_order_by(sort, direction) -> str:
    """ORDER BY clause for the listing. Unknown sort/direction fall back to the
    original newest-first order. A unique tie-breaker (p.id) keeps LIMIT/OFFSET
    pages stable, so a row can't repeat or vanish between pages."""
    if sort not in _PATIENT_SORTS:
        return " ORDER BY p.created_at DESC, p.id DESC"
    exprs, invert = _PATIENT_SORTS[sort]
    desc = (str(direction).lower() == "desc") != invert
    d = "DESC" if desc else "ASC"
    parts = [f"({exprs[0]}) IS NULL", *[f"{e} {d}" for e in exprs]]
    return " ORDER BY " + ", ".join(parts) + ", p.id ASC"


def list_patients_with_latest_screening(barangay=None, risk=None, date=None, entries_limit=None, q=None, offset=None, status=None, sort=None, direction="asc"):
    conn = get_connection()
    conditions, params = _patient_listing_filters(barangay=barangay, risk=risk, date=date, q=q, status=status)

    sql = f"""
        SELECT p.id AS patient_id, p.patient_code, p.first_name, p.last_name, p.birthdate, p.sex,
               b.name AS barangay,
               v.assessment_date AS date,
               v.status AS visit_status,
               ls.fbs_mg_dl AS fbs,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) AS risk
        {_PATIENT_LISTING_JOINS}
    """

    sql += " WHERE " + " AND ".join(conditions)
    sql += _patient_order_by(sort, direction)

    if entries_limit:
        sql += " LIMIT ?"
        params.append(entries_limit)
        if offset:
            sql += " OFFSET ?"
            params.append(offset)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["age"] = _compute_age(d["birthdate"])
        result.append(d)
    return result

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
    Delete soft-deleted patients older than the configured retention window.

    """
    from app.models import settings as settings_model

    retention_days = settings_model.get_data_retention_days()
    if retention_days is None:
        return 0

    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM patients WHERE deleted_at IS NOT NULL AND deleted_at <= datetime('now', ?)",
        (f"-{retention_days} days",),
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


def list_screenings_missing_risk_prediction(barangay=None, date=None) -> list[dict]:
    """
    Visits that have an FBS reading but no risk classification at all yet
    (no clinician-confirmed final_risk_level, no preliminary_risk_level, and
    no model_predicted_risk_level). Used by the export flow to backfill a
    model prediction so the CSV never has to show 'Pending'.
    """
    conn = get_connection()
    conditions, params = [
        "p.deleted_at IS NULL",
        "ls.fbs_mg_dl IS NOT NULL",
        "ls.final_risk_level IS NULL",
        "ls.preliminary_risk_level IS NULL",
        "ls.model_predicted_risk_level IS NULL",
    ], []
    if barangay:
        conditions.append("b.name = ?")
        params.append(barangay)
    if date:
        conditions.append("DATE(v.assessment_date) = ?")
        params.append(date)

    sql = f"""
        SELECT v.id AS visit_id, ls.id AS lab_screening_id, ls.fbs_mg_dl
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        LEFT JOIN barangays b ON b.id = p.barangay_id
        WHERE {" AND ".join(conditions)}
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_patients_csv(barangay=None, risk=None, date=None, all_visits=False) -> str:
    """
    Full clinical export for SRCHO -- includes demographics, vitals,
    PMH/family history/diet/immunization/dm_symptom flags, CVD questionnaire,
    and lab screening result per visit. Patient names excluded; patient_code
    kept in plaintext as a non-identifying reference.
    """
    conn = get_connection()

    conditions, params = ["p.deleted_at IS NULL"], []
    if barangay:
        conditions.append("b.name = ?")
        params.append(barangay)
    if risk:
        conditions.append("COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) = ?")
        params.append(risk)
    if date:
        conditions.append("DATE(v.assessment_date) = ?")
        params.append(date)

    visit_join = (
        "LEFT JOIN visits v ON v.patient_id = p.id"
        if all_visits else
        """LEFT JOIN visits v ON v.id = (
               SELECT v2.id FROM visits v2
               WHERE v2.patient_id = p.id
               ORDER BY v2.id DESC
               LIMIT 1
           )"""
    )

    sql = f"""
        SELECT p.patient_code, p.birthdate, p.sex, p.civil_status, p.education, p.occupation,
               b.region_name AS region, b.city_name AS city, b.name AS barangay,
               v.id AS visit_id, v.assessment_date,
               v.smoking_status, v.alcohol_intake, v.illicit_drug_use, v.physical_activity,
               v.diabetes_diagnosis, v.bp_systolic, v.bp_diastolic, v.heart_rate,
               v.respiratory_rate, v.height_cm, v.weight_kg, v.waist_cm, v.bmi, v.obesity_class,
               ls.fbs_mg_dl,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) AS risk,
               CASE
                   WHEN ls.final_risk_level IS NOT NULL THEN 'Confirmed'
                   WHEN ls.preliminary_risk_level IS NOT NULL THEN 'Preliminary'
                   WHEN ls.model_predicted_risk_level IS NOT NULL THEN 'Model-predicted'
                   ELSE 'Pending'
               END AS risk_source
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        {visit_join}
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
    """
    sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY p.patient_code, v.id"

    rows = conn.execute(sql, params).fetchall()

    # per visit toh
    
    visit_ids = [dict(r)["visit_id"] for r in rows if dict(r)["visit_id"] is not None]
    conditions_by_visit = {}
    cvd_by_visit = {}
    if visit_ids:
        placeholders = ",".join("?" * len(visit_ids))
        cond_rows = conn.execute(f"""
            SELECT vc.visit_id, cc.category, cc.code
            FROM visit_conditions vc
            JOIN condition_catalog cc ON cc.id = vc.condition_id
            WHERE vc.visit_id IN ({placeholders})
        """, visit_ids).fetchall()
        for cr in cond_rows:
            conditions_by_visit.setdefault(cr["visit_id"], {
                "pmh": [], "family_history": [], "diet": [], "immunization": [], "dm_symptom": []
            })
            conditions_by_visit[cr["visit_id"]][cr["category"]].append(cr["code"])

        cvd_rows = conn.execute(f"""
            SELECT * FROM cvd_responses WHERE visit_id IN ({placeholders})
        """, visit_ids).fetchall()
        for cvr in cvd_rows:
            cvd_by_visit[cvr["visit_id"]] = dict(cvr)

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "patient_code", "age", "sex", "civil_status", "education", "occupation", "region", "city", "barangay",
        "assessment_date", "smoking_status", "alcohol_intake", "illicit_drug_use", "physical_activity",
        "diabetes_diagnosis", "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
        "height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class",
        "fbs_mg_dl", "risk_level", "risk_source",
        "pmh", "family_history", "diet", "immunization", "dm_symptom",
        "q1_chest_discomfort", "q2_pain_center_left_arm", "q3_occurs_uphill_hurrying",
        "q4_slows_down_if_occurs", "q5_relieved_by_rest_tablet", "q6_relieved_under_10min",
        "q7_severe_pain_30min_plus", "q8_tia_stroke_symptoms",
    ])

    for r in rows:
        d = dict(r)
        age = _compute_age(d["birthdate"]) if d["birthdate"] else ""
        vid = d["visit_id"]
        cond = conditions_by_visit.get(vid, {"pmh": [], "family_history": [], "diet": [], "immunization": [], "dm_symptom": []})
        cvd = cvd_by_visit.get(vid, {})

        writer.writerow([
            d["patient_code"], age, d["sex"] or "", d["civil_status"] or "", d["education"] or "", d["occupation"] or "",
            d["region"] or "", d["city"] or "", d["barangay"] or "",
            d["assessment_date"] or "",
            d["smoking_status"] or "", d["alcohol_intake"] or "", d["illicit_drug_use"] or "", d["physical_activity"] or "",
            d["diabetes_diagnosis"] or "",
            d["bp_systolic"] if d["bp_systolic"] is not None else "",
            d["bp_diastolic"] if d["bp_diastolic"] is not None else "",
            d["heart_rate"] if d["heart_rate"] is not None else "",
            d["respiratory_rate"] if d["respiratory_rate"] is not None else "",
            d["height_cm"] if d["height_cm"] is not None else "",
            d["weight_kg"] if d["weight_kg"] is not None else "",
            d["waist_cm"] if d["waist_cm"] is not None else "",
            d["bmi"] if d["bmi"] is not None else "",
            d["obesity_class"] or "",
            d["fbs_mg_dl"] if d["fbs_mg_dl"] is not None else "",
            d["risk"] or "", d["risk_source"],
            ";".join(cond["pmh"]), ";".join(cond["family_history"]), ";".join(cond["diet"]),
            ";".join(cond["immunization"]), ";".join(cond["dm_symptom"]),
            int(bool(cvd.get("q1_chest_discomfort"))), int(bool(cvd.get("q2_pain_center_left_arm"))),
            int(bool(cvd.get("q3_occurs_uphill_hurrying"))), int(bool(cvd.get("q4_slows_down_if_occurs"))),
            int(bool(cvd.get("q5_relieved_by_rest_tablet"))), int(bool(cvd.get("q6_relieved_under_10min"))),
            int(bool(cvd.get("q7_severe_pain_30min_plus"))), int(bool(cvd.get("q8_tia_stroke_symptoms"))),
        ])

    return output.getvalue()

def export_single_patient_csv(patient_code: str, all_visits: bool = True) -> str:
    """
    Same shape as export_patients_csv, scoped to one patient.
    Defaults to all_visits=True since viewing one patient's file usually
    means wanting their whole history, not just the latest visit.
    """
    conn = get_connection()

    patient_row = conn.execute("SELECT id FROM patients WHERE patient_code = ?", (patient_code,)).fetchone()
    if patient_row is None:
        conn.close()
        return ""

    patient_db_id = patient_row["id"]

    visit_join = (
        "LEFT JOIN visits v ON v.patient_id = p.id"
        if all_visits else
        """LEFT JOIN visits v ON v.id = (
               SELECT v2.id FROM visits v2
               WHERE v2.patient_id = p.id
               ORDER BY v2.id DESC
               LIMIT 1
           )"""
    )

    sql = f"""
        SELECT p.patient_code, p.birthdate, p.sex, p.civil_status, p.education, p.occupation,
               b.region_name AS region, b.city_name AS city, b.name AS barangay,
               v.id AS visit_id, v.assessment_date,
               v.smoking_status, v.alcohol_intake, v.illicit_drug_use, v.physical_activity,
               v.diabetes_diagnosis, v.bp_systolic, v.bp_diastolic, v.heart_rate,
               v.respiratory_rate, v.height_cm, v.weight_kg, v.waist_cm, v.bmi, v.obesity_class,
               ls.fbs_mg_dl,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) AS risk,
               CASE
                   WHEN ls.final_risk_level IS NOT NULL THEN 'Confirmed'
                   WHEN ls.preliminary_risk_level IS NOT NULL THEN 'Preliminary'
                   WHEN ls.model_predicted_risk_level IS NOT NULL THEN 'Model-predicted'
                   ELSE 'Pending'
               END AS risk_source
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        {visit_join}
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
        WHERE p.id = ?
        ORDER BY v.id
    """

    rows = conn.execute(sql, (patient_db_id,)).fetchall()

    visit_ids = [dict(r)["visit_id"] for r in rows if dict(r)["visit_id"] is not None]
    conditions_by_visit = {}
    cvd_by_visit = {}
    if visit_ids:
        placeholders = ",".join("?" * len(visit_ids))
        cond_rows = conn.execute(f"""
            SELECT vc.visit_id, cc.category, cc.code
            FROM visit_conditions vc
            JOIN condition_catalog cc ON cc.id = vc.condition_id
            WHERE vc.visit_id IN ({placeholders})
        """, visit_ids).fetchall()
        for cr in cond_rows:
            conditions_by_visit.setdefault(cr["visit_id"], {
                "pmh": [], "family_history": [], "diet": [], "immunization": [], "dm_symptom": []
            })
            conditions_by_visit[cr["visit_id"]][cr["category"]].append(cr["code"])

        cvd_rows = conn.execute(f"""
            SELECT * FROM cvd_responses WHERE visit_id IN ({placeholders})
        """, visit_ids).fetchall()
        for cvr in cvd_rows:
            cvd_by_visit[cvr["visit_id"]] = dict(cvr)

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "patient_code", "age", "sex", "civil_status", "education", "occupation", "region", "city", "barangay",
        "assessment_date", "smoking_status", "alcohol_intake", "illicit_drug_use", "physical_activity",
        "diabetes_diagnosis", "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
        "height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class",
        "fbs_mg_dl", "risk_level", "risk_source",
        "pmh", "family_history", "diet", "immunization", "dm_symptom",
        "q1_chest_discomfort", "q2_pain_center_left_arm", "q3_occurs_uphill_hurrying",
        "q4_slows_down_if_occurs", "q5_relieved_by_rest_tablet", "q6_relieved_under_10min",
        "q7_severe_pain_30min_plus", "q8_tia_stroke_symptoms",
    ])

    for r in rows:
        d = dict(r)
        age = _compute_age(d["birthdate"]) if d["birthdate"] else ""
        vid = d["visit_id"]
        cond = conditions_by_visit.get(vid, {"pmh": [], "family_history": [], "diet": [], "immunization": [], "dm_symptom": []})
        cvd = cvd_by_visit.get(vid, {})

        writer.writerow([
            d["patient_code"], age, d["sex"] or "", d["civil_status"] or "", d["education"] or "", d["occupation"] or "",
            d["region"] or "", d["city"] or "", d["barangay"] or "",
            d["assessment_date"] or "",
            d["smoking_status"] or "", d["alcohol_intake"] or "", d["illicit_drug_use"] or "", d["physical_activity"] or "",
            d["diabetes_diagnosis"] or "",
            d["bp_systolic"] if d["bp_systolic"] is not None else "",
            d["bp_diastolic"] if d["bp_diastolic"] is not None else "",
            d["heart_rate"] if d["heart_rate"] is not None else "",
            d["respiratory_rate"] if d["respiratory_rate"] is not None else "",
            d["height_cm"] if d["height_cm"] is not None else "",
            d["weight_kg"] if d["weight_kg"] is not None else "",
            d["waist_cm"] if d["waist_cm"] is not None else "",
            d["bmi"] if d["bmi"] is not None else "",
            d["obesity_class"] or "",
            d["fbs_mg_dl"] if d["fbs_mg_dl"] is not None else "",
            d["risk"] or "", d["risk_source"],
            ";".join(cond["pmh"]), ";".join(cond["family_history"]), ";".join(cond["diet"]),
            ";".join(cond["immunization"]), ";".join(cond["dm_symptom"]),
            int(bool(cvd.get("q1_chest_discomfort"))), int(bool(cvd.get("q2_pain_center_left_arm"))),
            int(bool(cvd.get("q3_occurs_uphill_hurrying"))), int(bool(cvd.get("q4_slows_down_if_occurs"))),
            int(bool(cvd.get("q5_relieved_by_rest_tablet"))), int(bool(cvd.get("q6_relieved_under_10min"))),
            int(bool(cvd.get("q7_severe_pain_30min_plus"))), int(bool(cvd.get("q8_tia_stroke_symptoms"))),
        ])

    return output.getvalue()

"""
Drop-in replacement for patient_model.generate_import_template_csv.

Design:
- 10 single-value fields get a real Excel dropdown (data validation) --
  the encoder physically cannot type a value outside the allowed set.
- 5 multi-value fields (semicolon-separated, per patient_model's own
  `multi()` splitter) can't use a plain dropdown, so instead they get:
    * a comment on the header cell listing the valid codes right where
      the encoder is typing
    * a "Codes" reference sheet with the same lists, copy-paste-able
    * conditional formatting that turns the cell red if ANY
      semicolon-separated token in it isn't one of the valid codes for
      that column -- visible before the file ever reaches import.
"""
import openpyxl
from io import BytesIO
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import PatternFill, Font

MAX_ROWS = 1000  # validation / formatting covers every row an encoder might fill in

# ---------------------------------------------------------------------------
# Confirmed against nurse_intake.html + the smoking_status CHECK constraint.
# Do not add a value here without confirming it against the schema/form --
# that's exactly how 'Heart Disease' / 'Standard' / 'Fatigue' ended up in
# the synthetic data with no matching condition_catalog row.
# ---------------------------------------------------------------------------
SINGLE_VALUE_FIELDS = {
    "sex": ["Male", "Female"],
    "civil_status": ["Single", "Married", "Annulled", "Widow/Widower", "Separated"],
    "education": ["No Schooling", "Elementary", "High School", "Vocational",
                  "College degree, post graduate"],
    "phic_membership": ["Member", "Dependent", "Non-Member"],
    "phic_type": ["Sponsored - NHTS", "Sponsored - LGU", "Sponsored - NGA",
                  "IPP - Organized Group", "IPP - OFW", "IPP - Private",
                  "Employed - Government", "Employed - Private", "Lifetime"],
    "smoking_status": ["Never smoked", "Stopped > 1 year", "Current Smoker",
                        "Stopped < 1 year", "Passive Smoker"],
    "alcohol_intake": ["Never Consumed", "Yes",
                        "Yes (Binge: 5+ drinks in one occasion past month)"],
    "illicit_drug_use": ["No", "Yes"],
    "physical_activity": ["Does NOT meet 2.5 hours/week",
                           "Meets at least 2.5 hours/week moderate activity"],
    "diabetes_diagnosis": ["No / Do not know", "Yes (with medications)",
                            "Yes (without medications)"],
    "referral_action": ["Refer for OGTT", "Refer to physician",
                         "Lifestyle counseling only"],
    # "referred_to" names a FACILITY only, never a physician -- referral_action
    # above ("Refer to physician") already records that a doctor is involved;
    # this field says where the patient is being sent, not who will see them.
    # Adjust this list to match SRCHO's actual referral destinations.
    "referred_to": ["Santa Rosa City Health Office (SRCHO)", "LHU I", "LHU II",
                     "Partner Hospital / Referral Center", "Other Facility"],
    # Pre-Screening Checklist (Yes/No per item, same as the screening page's checkboxes)
    "fasted_ge_8h": ["Yes", "No"],
    "identity_verified": ["Yes", "No"],
    "glucometer_calibrated": ["Yes", "No"],
    "capillary_sample_taken": ["Yes", "No"],
    "consent_signed": ["Yes", "No"],
    "result_recorded_within_5min": ["Yes", "No"],
}

def is_doctor_like_referral(text) -> bool:
    """referred_to must name a FACILITY, not a person. Flags the common
    ways a doctor's name slips in instead (a "Dr" title, or "M.D."/"MD"
    as a suffix)."""
    t = (text or "").strip()
    if not t:
        return False
    low = t.casefold()
    if re.match(r"^dr\.?\s", low) or low == "dr":
        return True
    if re.search(r"\bm\.?d\.?$", low):
        return True
    return False


# Screening-page fields that live on lab_screenings (need an fbs_mg_dl on the
# same row to be saved) -- checklist + referral & follow-up.
CHECKLIST_FIELDS = [
    "fasted_ge_8h", "identity_verified", "glucometer_calibrated",
    "capillary_sample_taken", "consent_signed", "result_recorded_within_5min",
]

MULTI_VALUE_FIELDS = {
    "pmh": ["Allergy", "Asthma", "Cancer", "Cerebrovascular Disease",
            "Coronary Artery Disease", "Diabetes Mellitus", "Emphysema",
            "Epilepsy/Seizure Disease", "Hepatitis", "Hyperlipidemia",
            "Hypertension", "Peptic Ulcer Disease", "Pneumonia",
            "Thyroid Disease", "Tuberculosis", "Urinary Tract Infection"],
    "family_history": ["Hypertension", "Stroke/Cerebrovascular Disease",
                        "Coronary Artery Disease", "Diabetes Mellitus",
                        "Asthma", "Cancer", "Kidney Disease"],
    "diet": ["High Fat/Salt", "3+ servings vegetables daily",
             "2-3 servings fruits daily"],
    "dm_symptom": ["Polyphagia", "Polydipsia", "Polyuria"],
    "immunization": ["BCG", "OPV/IPV Series", "DPT Series", "Measles",
                      "Hepatitis A/B Series", "HPV", "MMR", "Tetanus Toxoid",
                      "Pneumococcal Vaccine", "Flu Vaccine"],
}

COLUMNS = [
    "last_name", "first_name", "middle_name", "maiden_name",
    "birthdate", "sex", "civil_status", "religion", "occupation", "education",
    "region", "city", "barangay", "address", "contact_number",
    "phic_membership", "phic_type",
    "assessment_date",
    "smoking_status", "alcohol_intake", "illicit_drug_use", "physical_activity",
    "diabetes_diagnosis", "past_surgical_history",
    "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
    "height_cm", "weight_kg", "waist_cm",
    "pmh", "family_history", "diet", "immunization", "dm_symptom",
    "fbs_mg_dl",
    # Clinical Notes & Observations
    "clinical_notes",
    # Referral & Follow-up
    "referral_action", "follow_up_date", "referred_to",
    # Pre-Screening Checklist
    "fasted_ge_8h", "identity_verified", "glucometer_calibrated",
    "capillary_sample_taken", "consent_signed", "result_recorded_within_5min",
]

RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")


def _col_letter(ws, col_name):
    return ws.cell(row=1, column=COLUMNS.index(col_name) + 1).column_letter


def _add_dropdown(ws, col_name, choices):
    col_letter = _col_letter(ws, col_name)
    dv = DataValidation(
        type="list",
        formula1='"{}"'.format(",".join(choices)),
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Invalid entry",
        error="Pick one of: " + ", ".join(choices),
    )
    ws.add_data_validation(dv)
    dv.add(f"{col_letter}2:{col_letter}{MAX_ROWS}")


def _add_multi_value_comment(ws, col_name, choices):
    header_cell = ws.cell(row=1, column=COLUMNS.index(col_name) + 1)
    text = (
        "Separate multiple values with a semicolon (;).\n"
        "Valid codes for this column:\n- " + "\n- ".join(choices)
    )
    header_cell.comment = Comment(text, "System")


def _multi_value_flag_formula(top_left_ref, choices):
    """
    True (flag red) when the cell is non-blank AND, after stripping every
    valid code and every ';'/space from its text, something is still left
    over -- i.e. at least one token isn't a recognized code.

    Case-sensitive on purpose: SUBSTITUTE matches exact case, same as the
    Python-side `multi()` -> save_visit_conditions() lookup it's guarding
    against, so a formatting hit here means import would genuinely reject
    or drop that token too.
    """
    expr = top_left_ref
    for code in choices:
        escaped = code.replace('"', '""')
        expr = f'SUBSTITUTE({expr},"{escaped}","")'
    expr = f'SUBSTITUTE({expr},";","")'
    expr = f'SUBSTITUTE({expr}," ","")'
    return f'AND({top_left_ref}<>"",LEN({expr})>0)'


def _add_multi_value_formatting(ws, col_name, choices):
    col_letter = _col_letter(ws, col_name)
    top_left = f"{col_letter}2"
    formula = _multi_value_flag_formula(top_left, choices)
    rule = FormulaRule(formula=[formula], fill=RED_FILL)
    ws.conditional_formatting.add(f"{col_letter}2:{col_letter}{MAX_ROWS}", rule)


def _build_codes_sheet(wb):
    ws = wb.create_sheet("Codes")
    ws["A1"] = "Reference: valid codes for multi-value columns (semicolon-separated in the import sheet)"
    ws["A1"].font = Font(bold=True)
    row = 3
    for field, choices in MULTI_VALUE_FIELDS.items():
        ws.cell(row=row, column=1, value=field).font = Font(bold=True)
        for choice in choices:
            row += 1
            ws.cell(row=row, column=1, value=choice)
        row += 2
    ws.column_dimensions["A"].width = 45


def generate_import_template_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "patient_import"
    ws.append(COLUMNS)
    ws.freeze_panes = "A2"
    ws["A1"].font = Font(bold=True)
    for i in range(1, len(COLUMNS) + 1):
        ws.cell(row=1, column=i).font = Font(bold=True)
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = \
            max(14, len(COLUMNS[i - 1]) + 2)

    for field, choices in SINGLE_VALUE_FIELDS.items():
        _add_dropdown(ws, field, choices)

    for field, choices in MULTI_VALUE_FIELDS.items():
        _add_multi_value_comment(ws, field, choices)
        _add_multi_value_formatting(ws, field, choices)

    _build_codes_sheet(wb)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    # smoke test: build it, then re-open it and sanity-check a few things
    data = generate_import_template_xlsx()
    with open("/home/claude/patient_import_template.xlsx", "wb") as f:
        f.write(data)

    check = openpyxl.load_workbook("/home/claude/patient_import_template.xlsx")
    ws = check["patient_import"]
    assert ws["F1"].value == "sex"
    assert len(ws.data_validations.dataValidation) == len(SINGLE_VALUE_FIELDS)
    assert ws.cell(row=1, column=COLUMNS.index("pmh") + 1).comment is not None
    assert "Codes" in check.sheetnames
    print("OK:", len(ws.data_validations.dataValidation), "dropdowns,",
          len(check["Codes"]["A"]), "rows on Codes sheet")


def _parse_import_date(raw: str) -> str | None:
    """Best-effort parse of a CSV date cell into YYYY-MM-DD. Accepts the
    documented ISO format plus the handful of formats a nurse's spreadsheet
    commonly produces (Excel auto-formats dates as M/D/YYYY by default).
    Returns None if nothing recognized it -- the caller decides the fallback."""
    from datetime import datetime as _dt
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return _dt.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def import_patients_from_csv(file_stream, staff_id: int | None = None) -> dict:
    import csv as csv_module
    from datetime import date as date_module
    from app.models import visit_model, lab_model, lookup_model

    text = file_stream.read().decode("utf-8-sig")
    reader = csv_module.DictReader(io.StringIO(text))

    required_columns = {"last_name", "first_name", "birthdate", "sex"}
    if not required_columns.issubset(set(reader.fieldnames or [])):
        missing = required_columns - set(reader.fieldnames or [])
        return {"created": 0, "new_patients": 0, "matched_existing": 0, "skipped": 0,
                "errors": [f"Missing required column(s): {', '.join(missing)}"],
                "screened_for_prediction": []}

    created, skipped, errors = 0, 0, []
    new_patients = 0
    matched_existing = 0
    # Visits that got an FBS reading during this import, so the caller can
    # run the real ML model on them afterward instead of leaving them on
    # the naive glucose-cutoff preliminary classification only (see
    # nurse_controller.nurse_data_management_import).
    screened_for_prediction = []

    def multi(val):
        return [v.strip() for v in (val or "").split(";") if v.strip()]

    for i, row in enumerate(reader, start=2):
        try:
            last_name = (row.get("last_name") or "").strip()
            first_name = (row.get("first_name") or "").strip()
            birthdate = (row.get("birthdate") or "").strip()
            sex_raw = (row.get("sex") or "").strip()

            if not (last_name and first_name and birthdate and sex_raw):
                errors.append(f"Row {i}: missing required field(s), skipped.")
                skipped += 1
                continue

            sex = "Male" if sex_raw.upper().startswith("M") else "Female" if sex_raw.upper().startswith("F") else None
            if sex is None:
                errors.append(f"Row {i}: unrecognized sex value {sex_raw!r}, skipped.")
                skipped += 1
                continue

            try:
                date_module.fromisoformat(birthdate)
            except ValueError:
                errors.append(f"Row {i}: birthdate {birthdate!r} is not YYYY-MM-DD, skipped.")
                skipped += 1
                continue

            barangay_id, barangay_warning = lookup_model.resolve_barangay_from_names(
                (row.get("barangay") or "").strip(),
                (row.get("city") or "").strip(),
                (row.get("region") or "").strip(),
            )
            if barangay_warning:
                errors.append(f"Row {i}: {barangay_warning}")

            patient_data = {
                "last_name": last_name, "first_name": first_name,
                "middle_name": (row.get("middle_name") or "").strip() or None,
                "maiden_name": (row.get("maiden_name") or "").strip() or None,
                "birthdate": birthdate, "sex": sex,
                "civil_status": (row.get("civil_status") or "").strip() or None,
                "religion": (row.get("religion") or "").strip() or None,
                "occupation": (row.get("occupation") or "").strip() or None,
                "education": (row.get("education") or "").strip() or None,
                "barangay_id": barangay_id,
                "address": (row.get("address") or "").strip() or None,
                "contact_number": (row.get("contact_number") or "").strip() or None,
                "phic_membership": (row.get("phic_membership") or "").strip() or None,
                "phic_type": (row.get("phic_type") or "").strip() or None,
            }

            existing_patient_id = find_existing_patient_id(
                last_name, first_name, patient_data["middle_name"], birthdate
            )

            if existing_patient_id is not None:
                patient_id = existing_patient_id
                matched_existing += 1
            else:
                patient_id = create_patient(patient_data, staff_id=staff_id)
                new_patients += 1

            assessment_date_raw = (row.get("assessment_date") or "").strip()
            if assessment_date_raw:
                assessment_date = _parse_import_date(assessment_date_raw)
                if assessment_date is None:
                    errors.append(
                        f"Row {i}: assessment_date {assessment_date_raw!r} is not a recognized date "
                        "format (use YYYY-MM-DD) -- used today's date instead."
                    )
                    assessment_date = date_module.today().isoformat()
            else:
                assessment_date = date_module.today().isoformat()
            visit_data = {
                "assessment_date": assessment_date,
                # No FBS on the row = patient is still awaiting lab results, so
                # the visit is an unfinished draft (shows the Draft badge in Data
                # Management) until the screening is saved -- which flips it to
                # "submitted". Rows that arrive with an FBS are complete.
                "status": "submitted" if (row.get("fbs_mg_dl") or "").strip() else "draft",
                "smoking_status": (row.get("smoking_status") or "").strip() or None,
                "alcohol_intake": (row.get("alcohol_intake") or "").strip() or None,
                "illicit_drug_use": (row.get("illicit_drug_use") or "").strip() or None,
                "physical_activity": (row.get("physical_activity") or "").strip() or None,
                "diabetes_diagnosis": (row.get("diabetes_diagnosis") or "").strip() or None,
                "past_surgical_history": (row.get("past_surgical_history") or "").strip() or None,
                "clinical_notes": (row.get("clinical_notes") or "").strip() or None,
            }

            for num_field, csv_col in [
                ("bp_systolic", "bp_systolic"), ("bp_diastolic", "bp_diastolic"),
                ("heart_rate", "heart_rate"), ("respiratory_rate", "respiratory_rate"),
                ("height_cm", "height_cm"), ("weight_kg", "weight_kg"), ("waist_cm", "waist_cm"),
            ]:
                raw = (row.get(csv_col) or "").strip()
                if raw:
                    try:
                        visit_data[num_field] = float(raw)
                    except ValueError:
                        errors.append(f"Row {i}: {csv_col} value {raw!r} is not numeric, ignored.")

            # calc ng bmi
            if visit_data.get("height_cm") and visit_data.get("weight_kg"):
                h_m = visit_data["height_cm"] / 100
                bmi = visit_data["weight_kg"] / (h_m * h_m)
                visit_data["bmi"] = round(bmi, 1)
                if bmi < 18.5: visit_data["obesity_class"] = "Underweight"
                elif bmi < 23: visit_data["obesity_class"] = "Normal"
                elif bmi < 25: visit_data["obesity_class"] = "Overweight"
                elif bmi < 30: visit_data["obesity_class"] = "Obese Class I"
                else: visit_data["obesity_class"] = "Obese Class II"

            visit_id = visit_model.create_visit(patient_id, "intake", visit_data, staff_id=staff_id)

            for category, csv_col in [
                ("pmh", "pmh"), ("family_history", "family_history"),
                ("diet", "diet"), ("immunization", "immunization"), ("dm_symptom", "dm_symptom"),
            ]:
                raw_codes = multi(row.get(csv_col))
                if not raw_codes:
                    continue
                catalog = MULTI_VALUE_FIELDS[category]
                by_lower = {c.casefold(): c for c in catalog}
                valid_codes, bad_codes = [], []
                for code in raw_codes:
                    canonical = by_lower.get(code.casefold())
                    (valid_codes if canonical else bad_codes).append(canonical or code)
                if bad_codes:
                    errors.append(
                        f"Row {i}: {csv_col} value(s) not recognized, skipped: "
                        f"{', '.join(bad_codes)}. Recognized values: {', '.join(catalog)}."
                    )
                if valid_codes:
                    try:
                        visit_model.save_visit_conditions(visit_id, category, valid_codes)
                    except ValueError as ve:
                        # Only reachable if two rows race on the same visit_id, which
                        # can't happen here -- kept as a safety net, not expected.
                        errors.append(f"Row {i}: {ve}")

            def yes_no(val):
                return (val or "").strip().lower() in ("yes", "y", "true", "1", "x", "checked")

            referral_action = (row.get("referral_action") or "").strip() or None
            follow_up_date = (row.get("follow_up_date") or "").strip() or None
            referred_to = (row.get("referred_to") or "").strip() or None
            if referred_to and is_doctor_like_referral(referred_to):
                errors.append(
                    f"Row {i}: referred_to {referred_to!r} looks like a physician's name -- "
                    "this field is for the facility referred to, not a doctor. Ignored."
                )
                referred_to = None
            if follow_up_date:
                try:
                    date_module.fromisoformat(follow_up_date)
                except ValueError:
                    errors.append(f"Row {i}: follow_up_date {follow_up_date!r} is not YYYY-MM-DD, ignored.")
                    follow_up_date = None
            if referral_action and referral_action not in SINGLE_VALUE_FIELDS["referral_action"]:
                errors.append(f"Row {i}: referral_action {referral_action!r} is not a recognized option, ignored.")
                referral_action = None

            fbs_raw = (row.get("fbs_mg_dl") or "").strip()
            has_lab_extras = bool(
                referral_action or follow_up_date or referred_to
                or any((row.get(c) or "").strip() for c in CHECKLIST_FIELDS)
            )
            if has_lab_extras and not fbs_raw:
                errors.append(
                    f"Row {i}: imported as a draft (no fbs_mg_dl yet). Its referral/follow-up/"
                    "checklist values were not saved -- enter them on the screening page "
                    "once the lab result is in."
                )
            if fbs_raw:
                try:
                    fbs_value = float(fbs_raw)
                    lab_data = {
                        "fbs_mg_dl": fbs_value,
                        "test_datetime": f"{assessment_date}T00:00",
                        "referral_action": referral_action,
                        "follow_up_date": follow_up_date,
                        "referred_to": referred_to,
                    }
                    for c in CHECKLIST_FIELDS:
                        lab_data[c] = yes_no(row.get(c))
                    lab_screening_id = lab_model.create_lab_screening(visit_id, lab_data, staff_id=staff_id)
                    screened_for_prediction.append({
                        "visit_id": visit_id,
                        "lab_screening_id": lab_screening_id,
                        "fbs_mg_dl": fbs_value,
                    })
                except ValueError:
                    errors.append(f"Row {i}: fbs_mg_dl {fbs_raw!r} is not numeric, screening skipped (imported as a draft).")
                    visit_model.update_visit(visit_id, {"status": "draft"})

            created += 1

        except Exception as e:
            errors.append(f"Row {i}: unexpected error — {e}")
            skipped += 1

    return {
        "created": created,
        "new_patients": new_patients,
        "matched_existing": matched_existing,
        "skipped": skipped,
        "errors": errors,
        "screened_for_prediction": screened_for_prediction,
    }

def record_login_event(patient_id: int, user_agent: str | None, ip_address: str | None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO patient_login_events (patient_id, user_agent, ip_address) VALUES (?, ?, ?)",
        (patient_id, user_agent, ip_address),
    )
    conn.commit()
    conn.close()

def get_recent_login_events(patient_id: int, limit: int = 5) -> list[dict]:
    from app.controllers.patient_auth_controller import describe_user_agent
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, user_agent, ip_address, created_at FROM patient_login_events "
        "WHERE patient_id = ? ORDER BY created_at DESC LIMIT ?",
        (patient_id, limit),
    ).fetchall()
    conn.close()
    return [
        {**dict(row), "device_label": describe_user_agent(row["user_agent"])}
        for row in rows
    ]

def update_patient_consent(patient_id: int, consent: bool) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE patients SET consent_research = ? WHERE id = ?",
        (1 if consent else 0, patient_id),
    )
    conn.commit()
    conn.close()