"""
all reads/writes to `visits`, `visit_conditions`, and `cvd_responses`
"""
from app.models.db import get_connection


def create_visit(patient_id: int, visit_type: str, data: dict, staff_id: int | None = None) -> int:
    conn = get_connection()
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
    conn.commit()
    visit_id = cur.lastrowid
    conn.close()
    return visit_id


def save_visit_conditions(visit_id: int, category: str, codes: list[str]) -> None:
    if not codes:
        return
    conn = get_connection()
    for code in codes:
        row = conn.execute(
            "SELECT id FROM condition_catalog WHERE category = ? AND code = ?",
            (category, code)
        ).fetchone()
        if row is None:
            # Unknown option -- likely a typo between the form and the
            # catalog seed data. Fail loud rather than silently dropping
            # a checked box (this is exactly the kind of silent-drop bug
            # that already bit the smoking/alcohol mapping, per thesis notes).
            raise ValueError(f"Unknown condition_catalog entry: ({category!r}, {code!r})")
        conn.execute(
            "INSERT OR IGNORE INTO visit_conditions (visit_id, condition_id) VALUES (?, ?)",
            (visit_id, row["id"])
        )
    conn.commit()
    conn.close()


def save_cvd_responses(visit_id: int, answers: dict) -> None:
    conn = get_connection()
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
    conn.close()


def list_visits_for_patient(patient_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT v.id AS visit_id, v.assessment_date AS date,
               ls.fbs_mg_dl AS fbs, ls.final_risk_level AS risk
        FROM visits v
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
        WHERE v.patient_id = ?
        ORDER BY v.assessment_date DESC
    """, (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

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