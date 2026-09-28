"""
all reads/writes to `visits`, `visit_conditions`, and `cvd_responses`
"""
from app.models.db import get_connection
from app.services import sync_queue


def create_visit(patient_id: int, visit_type: str, data: dict, staff_id: int | None = None) -> int:
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO visits (
                patient_id, visit_type, assessment_date, recorded_by_staff_id,
                smoking_status, alcohol_intake, illicit_drug_use, physical_activity,
                past_surgical_history, diabetes_diagnosis,
                bp_systolic, bp_diastolic, heart_rate, respiratory_rate,
                height_cm, weight_kg, waist_cm, bmi, obesity_class,
                pe_skin, pe_heent, pe_chest, pe_heart, pe_abdomen, pe_extremities,
                menarche_age, lmp_date, gravida, para, clinical_notes, status
            ) VALUES (?,?,?,?, ?,?,?,?, ?,?, ?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?)
        """, (
            patient_id, visit_type, data["assessment_date"], staff_id,
            data.get("smoking_status"), data.get("alcohol_intake"),
            data.get("illicit_drug_use"), data.get("physical_activity"),
            data.get("past_surgical_history"), data.get("diabetes_diagnosis"),
            data.get("bp_systolic"), data.get("bp_diastolic"), data.get("heart_rate"),
            data.get("respiratory_rate"), data.get("height_cm"), data.get("weight_kg"),
            data.get("waist_cm"), data.get("bmi"), data.get("obesity_class"),
            data.get("pe_skin"), data.get("pe_heent"), data.get("pe_chest"),
            data.get("pe_heart"), data.get("pe_abdomen"), data.get("pe_extremities"),
            data.get("menarche_age"), data.get("lmp_date"), data.get("gravida"),
            data.get("para"), data.get("clinical_notes"), data.get("status", "draft"),
        ))
        visit_id = cur.lastrowid
        # Green Computing module integration point: if the network link is currently down,
        # this queues the visit for the Offline & Sync Status page; if the link is up it does
        # nothing. Same transaction as the insert above -- on_visit_saved never commits itself.
        # See docs/NURSE_BRANCH_INTEGRATION.md.
        sync_queue.on_visit_saved(conn, visit_id)
        conn.commit()
        return visit_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_VISIT_UPDATABLE_COLUMNS = {
    "assessment_date", "smoking_status", "alcohol_intake", "illicit_drug_use",
    "physical_activity", "past_surgical_history", "diabetes_diagnosis",
    "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
    "height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class",
    "pe_skin", "pe_heent", "pe_chest", "pe_heart", "pe_abdomen", "pe_extremities",
    "menarche_age", "lmp_date", "gravida", "para", "clinical_notes", "status",
}


def update_visit(visit_id: int, data: dict) -> None:
    """
    Partial update of a visit row -- used by the Data Management "edit
    record" flow (nurse_patient_file_view). Only columns in
    _VISIT_UPDATABLE_COLUMNS are ever touched, and only the keys actually
    present in `data` are updated, so callers can send just the fields
    that changed. Deliberately excludes anything lab_screenings-owned
    (fbs, test method, risk level, etc.) -- test results are never
    editable from here.
    """
    fields = {k: v for k, v in data.items() if k in _VISIT_UPDATABLE_COLUMNS}
    if not fields:
        return
    set_clause = ", ".join(f"{col} = ?" for col in fields)
    params = list(fields.values()) + [visit_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE visits SET {set_clause} WHERE id = ?", params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def replace_visit_conditions(visit_id: int, category: str, codes: list[str]) -> None:
    """
    Like save_visit_conditions, but for editing: clears this visit's
    existing selections in `category` first, so unchecking a box in the
    edit form actually removes it instead of only ever adding new ones
    (save_visit_conditions is INSERT OR IGNORE-only, meant for first-time
    intake where there's nothing to remove).
    """
    conn = get_connection()
    try:
        conn.execute("""
            DELETE FROM visit_conditions
            WHERE visit_id = ? AND condition_id IN (
                SELECT id FROM condition_catalog WHERE category = ?
            )
        """, (visit_id, category))
        for code in codes or []:
            row = conn.execute(
                "SELECT id FROM condition_catalog WHERE category = ? AND code = ?",
                (category, code)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown condition_catalog entry: ({category!r}, {code!r})")
            conn.execute(
                "INSERT OR IGNORE INTO visit_conditions (visit_id, condition_id) VALUES (?, ?)",
                (visit_id, row["id"])
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_visit_conditions(visit_id: int, category: str, codes: list[str]) -> None:
    if not codes:
        return
    conn = get_connection()
    try:
        for code in codes:
            row = conn.execute(
                "SELECT id FROM condition_catalog WHERE category = ? AND code = ?",
                (category, code)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown condition_catalog entry: ({category!r}, {code!r})")
            conn.execute(
                "INSERT OR IGNORE INTO visit_conditions (visit_id, condition_id) VALUES (?, ?)",
                (visit_id, row["id"])
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_cvd_responses(visit_id: int, answers: dict) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO cvd_responses (
                visit_id, q1_chest_discomfort, q2_pain_center_left_arm,
                q3_occurs_uphill_hurrying, q4_slows_down_if_occurs,
                q5_relieved_by_rest_tablet, q6_relieved_under_10min,
                q7_severe_pain_30min_plus, q8_tia_stroke_symptoms
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(visit_id) DO UPDATE SET
                q1_chest_discomfort = excluded.q1_chest_discomfort,
                q2_pain_center_left_arm = excluded.q2_pain_center_left_arm,
                q3_occurs_uphill_hurrying = excluded.q3_occurs_uphill_hurrying,
                q4_slows_down_if_occurs = excluded.q4_slows_down_if_occurs,
                q5_relieved_by_rest_tablet = excluded.q5_relieved_by_rest_tablet,
                q6_relieved_under_10min = excluded.q6_relieved_under_10min,
                q7_severe_pain_30min_plus = excluded.q7_severe_pain_30min_plus,
                q8_tia_stroke_symptoms = excluded.q8_tia_stroke_symptoms
        """, (
            visit_id,
            int(bool(answers.get("q1_chest_discomfort"))),
            int(bool(answers.get("q2_pain_center_left_arm"))),
            int(bool(answers.get("q3_occurs_uphill_hurrying"))),
            int(bool(answers.get("q4_slows_down_if_occurs"))),
            int(bool(answers.get("q5_relieved_by_rest_tablet"))),
            int(bool(answers.get("q6_relieved_under_10min"))),
            int(bool(answers.get("q7_severe_pain_30min_plus"))),
            int(bool(answers.get("q8_tia_stroke_symptoms"))),
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_visits_for_patient(patient_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT v.id AS visit_id, v.assessment_date AS date,
               ls.fbs_mg_dl AS fbs,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk
        FROM visits v
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
        WHERE v.patient_id = ?
        ORDER BY v.id DESC
    """, (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_clinical_notes(visit_id: int, clinical_notes: str) -> None:
    """The screening page's Clinical Notes textarea posts to the lab-screening
    submit route, but clinical_notes lives on the visit row — this is the
    write path for it."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE visits SET clinical_notes = ? WHERE id = ?",
            (clinical_notes, visit_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_visit_by_id(visit_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_conditions_for_visit(visit_id: int) -> dict:
    conn = get_connection()
    rows = conn.execute("""
        SELECT cc.category, cc.code
        FROM visit_conditions vc
        JOIN condition_catalog cc ON cc.id = vc.condition_id
        WHERE vc.visit_id = ?
    """, (visit_id,)).fetchall()
    conn.close()
    result = {"pmh": [], "family_history": [], "diet": [], "immunization": [], "dm_symptom": []}
    for r in rows:
        result[r["category"]].append(r["code"])
    return result


def get_cvd_responses_for_visit(visit_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM cvd_responses WHERE visit_id = ?", (visit_id,)).fetchone()
    conn.close()
    return dict(row) if row else None