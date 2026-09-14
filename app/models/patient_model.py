"""
all reads/writes to `patients`

"""
import csv
import hashlib
import io
import re
from datetime import date
from app.models.db import get_connection
from datetime import date, datetime  
import sqlite3


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

def generate_import_template_csv() -> str:
    """CSV template matching nurse_intake.html's actual fields."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "last_name", "first_name", "middle_name",
        "birthdate", "sex", "civil_status", "religion", "occupation", "education",
        "barangay", "address", "contact_number",
        "phic_membership", "phic_type",
        "assessment_date",
        "smoking_status", "alcohol_intake", "illicit_drug_use", "physical_activity",
        "diabetes_diagnosis", "past_surgical_history",
        "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
        "height_cm", "weight_kg", "waist_cm",
        "pmh", "family_history", "diet", "immunization", "dm_symptom",
        "fbs_mg_dl",
    ])
    return output.getvalue()


def import_patients_from_csv(file_stream, staff_id: int | None = None) -> dict:
    import csv as csv_module
    from datetime import date as date_module
    from app.models import visit_model, lab_model, lookup_model

    text = file_stream.read().decode("utf-8-sig")
    reader = csv_module.DictReader(io.StringIO(text))

    required_columns = {"last_name", "first_name", "birthdate", "sex"}
    if not required_columns.issubset(set(reader.fieldnames or [])):
        missing = required_columns - set(reader.fieldnames or [])
        return {"created": 0, "skipped": 0, "errors": [f"Missing required column(s): {', '.join(missing)}"]}

    created, skipped, errors = 0, 0, []
    new_patients = 0
    matched_existing = 0

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

            barangay_id = None
            barangay_name = (row.get("barangay") or "").strip()
            if barangay_name:
                barangay_id = lookup_model.get_barangay_id(barangay_name)
                if barangay_id is None:
                    errors.append(f"Row {i}: unrecognized barangay {barangay_name!r}, created without barangay.")

            patient_data = {
                "last_name": last_name, "first_name": first_name,
                "middle_name": (row.get("middle_name") or "").strip() or None,
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

            assessment_date = (row.get("assessment_date") or "").strip() or date_module.today().isoformat()
            visit_data = {
                "assessment_date": assessment_date, "status": "submitted",
                "smoking_status": (row.get("smoking_status") or "").strip() or None,
                "alcohol_intake": (row.get("alcohol_intake") or "").strip() or None,
                "illicit_drug_use": (row.get("illicit_drug_use") or "").strip() or None,
                "physical_activity": (row.get("physical_activity") or "").strip() or None,
                "diabetes_diagnosis": (row.get("diabetes_diagnosis") or "").strip() or None,
                "past_surgical_history": (row.get("past_surgical_history") or "").strip() or None,
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
                codes = multi(row.get(csv_col))
                if codes:
                    try:
                        visit_model.save_visit_conditions(visit_id, category, codes)
                    except ValueError as ve:
                        errors.append(f"Row {i}: {ve}")

            fbs_raw = (row.get("fbs_mg_dl") or "").strip()
            if fbs_raw:
                try:
                    fbs_value = float(fbs_raw)
                    lab_model.create_lab_screening(visit_id, {
                        "fbs_mg_dl": fbs_value,
                        "test_datetime": f"{assessment_date}T00:00",
                    }, staff_id=staff_id)
                except ValueError:
                    errors.append(f"Row {i}: fbs_mg_dl {fbs_raw!r} is not numeric, screening skipped.")

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
    }