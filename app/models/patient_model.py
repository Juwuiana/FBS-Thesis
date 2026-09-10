"""
all reads/writes to `patients`

"""
import csv
import hashlib
import io
from datetime import date
from app.models.db import get_connection
from datetime import date, datetime  


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
    prefix = f"CAB-{year}-"

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

import sqlite3

def create_patient(data: dict, staff_id: int | None = None) -> int:
    max_attempts = 5
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
            return cur.lastrowid
        except sqlite3.IntegrityError:
            conn.rollback()
            continue  
        finally:
            conn.close()
    raise RuntimeError(f"Could not generate a unique patient_code after {max_attempts} attempts")

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
        LEFT JOIN visits v ON v.id = (
            SELECT v2.id FROM visits v2
            WHERE v2.patient_id = p.id
            ORDER BY v2.id DESC
            LIMIT 1
        )
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
        conditions.append("COALESCE(ls.final_risk_level, ls.preliminary_risk_level) = ?")
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
               b.name AS barangay,
               v.id AS visit_id, v.assessment_date,
               v.smoking_status, v.alcohol_intake, v.illicit_drug_use, v.physical_activity,
               v.diabetes_diagnosis, v.bp_systolic, v.bp_diastolic, v.heart_rate,
               v.respiratory_rate, v.height_cm, v.weight_kg, v.waist_cm, v.bmi, v.obesity_class,
               ls.fbs_mg_dl, COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk
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
        "patient_code", "age", "sex", "civil_status", "education", "occupation", "barangay",
        "assessment_date", "smoking_status", "alcohol_intake", "illicit_drug_use", "physical_activity",
        "diabetes_diagnosis", "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
        "height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class",
        "fbs_mg_dl", "risk_level",
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
            d["barangay"] or "",
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
            d["risk"] or "",
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
               b.name AS barangay,
               v.id AS visit_id, v.assessment_date,
               v.smoking_status, v.alcohol_intake, v.illicit_drug_use, v.physical_activity,
               v.diabetes_diagnosis, v.bp_systolic, v.bp_diastolic, v.heart_rate,
               v.respiratory_rate, v.height_cm, v.weight_kg, v.waist_cm, v.bmi, v.obesity_class,
               ls.fbs_mg_dl, COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk
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
        "patient_code", "age", "sex", "civil_status", "education", "occupation", "barangay",
        "assessment_date", "smoking_status", "alcohol_intake", "illicit_drug_use", "physical_activity",
        "diabetes_diagnosis", "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
        "height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class",
        "fbs_mg_dl", "risk_level",
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
            d["barangay"] or "",
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
            d["risk"] or "",
            ";".join(cond["pmh"]), ";".join(cond["family_history"]), ";".join(cond["diet"]),
            ";".join(cond["immunization"]), ";".join(cond["dm_symptom"]),
            int(bool(cvd.get("q1_chest_discomfort"))), int(bool(cvd.get("q2_pain_center_left_arm"))),
            int(bool(cvd.get("q3_occurs_uphill_hurrying"))), int(bool(cvd.get("q4_slows_down_if_occurs"))),
            int(bool(cvd.get("q5_relieved_by_rest_tablet"))), int(bool(cvd.get("q6_relieved_under_10min"))),
            int(bool(cvd.get("q7_severe_pain_30min_plus"))), int(bool(cvd.get("q8_tia_stroke_symptoms"))),
        ])

    return output.getvalue()