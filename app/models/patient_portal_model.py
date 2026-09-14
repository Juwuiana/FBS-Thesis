"""
eto yung nakikita ng patients
"""
import bisect
from app.models import visit_model, lab_model

_RISK_LABEL_MAP = {"Low": "Low Risk", "Moderate": "Moderate Risk", "High": "High Risk"}

_FBS_BAND_UPPER_BOUNDS = [99, 125]
_FBS_BAND_LABELS = ["Normal", "Pre-Diabetic", "Diabetic"]


def classify_fbs_band(fbs_score: float) -> str:
    idx = bisect.bisect_right(_FBS_BAND_UPPER_BOUNDS, fbs_score)
    return _FBS_BAND_LABELS[idx]


def get_current_patient_id():
    """
    TODO(auth): replace this with the real logged-in patient's internal
    id once the auth branch merges, e.g.:

        from flask import session
        return session.get("patient_id")

    DEV_NO_AUTH bypass below is for local testing only, before the auth
    branch merges. Never set FBS_DEV_NO_AUTH in anything but your local
    machine's .env.
    """
    import os
    if os.environ.get("FBS_DEV_NO_AUTH") == "1":
        return 1  # first patient in your local test DB

    raise NotImplementedError(
        "Patient authentication isn't wired in yet. See the auth branch "
        "for the real session lookup -- patient_controller.py just needs "
        "get_current_patient_id() to return the logged-in patient's id."
    )


def get_patient_dashboard_data(patient_id: int) -> dict:
    """
    patient_id is the internal integer id (patients.id), NOT the
    patient_code string.

    Returns everything patient_dashboard.html needs. If the patient has
    no visits yet, has_data is False and the template should show an
    empty/first-visit state instead of crashing on missing fields.
    """
    visits = visit_model.list_visits_for_patient(patient_id)

    if not visits:
        return {"has_data": False, "visits": []}

    screened_visits = [v for v in visits if v["fbs"] is not None]
    latest = screened_visits[0] if screened_visits else visits[0]

    latest_visit_detail = visit_model.get_visit_by_id(latest["visit_id"])
    latest_screening = lab_model.get_lab_screening_for_visit(latest["visit_id"])

    risk_raw = latest["risk"]
    risk_level = _RISK_LABEL_MAP.get(risk_raw, "Pending")

    return {
        "has_data": True,
        "risk_level": risk_level,
        "fbs_score": latest["fbs"],
        "fbs_band": classify_fbs_band(latest["fbs"]) if latest["fbs"] is not None else None,
        "total_screenings": len(visits),
        "latest_visit_date": latest["date"],
        "bmi": latest_visit_detail.get("bmi") if latest_visit_detail else None,
        "waist_cm": latest_visit_detail.get("waist_cm") if latest_visit_detail else None,
        "obesity_class": latest_visit_detail.get("obesity_class") if latest_visit_detail else None,
        "follow_up_date": latest_screening.get("follow_up_date") if latest_screening else None,
        "referred_to": latest_screening.get("referred_to") if latest_screening else None,
        "visits": visits,
    }


def get_full_screening_history(patient_id: int) -> list[dict]:
    """
    One entry per visit, shaped for patient_health_results.html
    (screening-card + detail-view per visit).
    """
    visits = visit_model.list_visits_for_patient(patient_id)
    history = []
    for v in visits:
        visit_detail = visit_model.get_visit_by_id(v["visit_id"]) or {}
        screening = lab_model.get_lab_screening_for_visit(v["visit_id"])
        conditions = visit_model.get_conditions_for_visit(v["visit_id"])
        cvd = visit_model.get_cvd_responses_for_visit(v["visit_id"]) or {
            "q1_chest_discomfort": 0, "q2_pain_center_left_arm": 0,
            "q3_occurs_uphill_hurrying": 0, "q4_slows_down_if_occurs": 0,
            "q5_relieved_by_rest_tablet": 0, "q6_relieved_under_10min": 0,
            "q7_severe_pain_30min_plus": 0, "q8_tia_stroke_symptoms": 0,
        }

        fbs = v["fbs"]
        history.append({
            "visit_id": v["visit_id"],
            "date": v["date"],
            "fbs_score": fbs,
            "fbs_band": classify_fbs_band(fbs) if fbs is not None else None,
            "range_marker_pct": max(2, min(100, round((fbs - 70) / (180 - 70) * 100, 1))) if fbs else None,
            "risk_level": _RISK_LABEL_MAP.get(v["risk"], "Pending"),
            "bmi": visit_detail.get("bmi"),
            "obesity_class": visit_detail.get("obesity_class"),
            "waist_cm": visit_detail.get("waist_cm"),
            "bp_systolic": visit_detail.get("bp_systolic"),
            "bp_diastolic": visit_detail.get("bp_diastolic"),
            "height_cm": visit_detail.get("height_cm"),
            "weight_kg": visit_detail.get("weight_kg"),
            "smoking_status": visit_detail.get("smoking_status"),
            "alcohol_intake": visit_detail.get("alcohol_intake"),
            "physical_activity": visit_detail.get("physical_activity"),
            "diabetes_diagnosis": visit_detail.get("diabetes_diagnosis"),
            "conditions": conditions,
            "cvd_responses": cvd,
            "follow_up_date": screening.get("follow_up_date") if screening else None,
            "referred_to": screening.get("referred_to") if screening else None,
            "referral_action": screening.get("referral_action") if screening else None,
        })
    return history