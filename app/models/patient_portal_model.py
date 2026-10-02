"""
eto yung nakikita ng patients
"""
import bisect
import json
from datetime import date, datetime
from app.models import visit_model, lab_model
from app.models import visit_model, lab_model, patient_fbs_model

_RISK_LABEL_MAP = {"Low": "Low Risk", "Moderate": "Moderate Risk", "High": "High Risk"}

_FBS_BAND_UPPER_BOUNDS = [99, 125]
_FBS_BAND_LABELS = ["Normal", "Pre-Diabetic", "Diabetic"]


def classify_fbs_band(fbs_score: float) -> str:
    idx = bisect.bisect_right(_FBS_BAND_UPPER_BOUNDS, fbs_score)
    return _FBS_BAND_LABELS[idx]


def _parse_date(value):
    """Handles ISO (2026-03-20) and DD/MM/YYYY strings. Returns date or None."""
    if not value:
        return None
    if isinstance(value, (date, datetime)):
        return value if isinstance(value, date) and not isinstance(value, datetime) else value.date()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _screened_visits(patient_id: int) -> list[dict]:
    """
    Only visits that actually have an FBS result (drafts / awaiting-lab visits
    are not "screenings" the patient should see or be counted), newest first.
    Sorted by assessment date, not visit id -- CSV imports create visits in
    file order, so id order can differ from date order.
    """
    visits = [v for v in visit_model.list_visits_for_patient(patient_id) if v["fbs"] is not None]
    visits.sort(key=lambda v: (_parse_date(v["date"]) or date.min, v["visit_id"]), reverse=True)
    return visits


def get_current_patient_id():
    """
    DEV_NO_AUTH bypass is for local testing only -- never set
    FBS_DEV_NO_AUTH in anything but your local machine's .env.
    """
    import os
    from flask import session
    if os.environ.get("FBS_DEV_NO_AUTH") == "1":
        return 1  # first patient in your local test DB
    return session.get("patient_id")


def get_patient_dashboard_data(patient_id: int) -> dict:
    """
    patient_id is the internal integer id (patients.id), NOT the
    patient_code string.

    Returns everything patient_dashboard.html needs. If the patient has
    no visits yet, has_data is False and the template should show an
    empty/first-visit state instead of crashing on missing fields.
    """
    visits = _screened_visits(patient_id)

    if not visits:
        return {"has_data": False, "visits": []}

    latest = visits[0]
    latest_visit_detail = visit_model.get_visit_by_id(latest["visit_id"]) or {}
    latest_screening = lab_model.get_lab_screening_for_visit(latest["visit_id"]) or {}

    risk_level = _RISK_LABEL_MAP.get(latest["risk"], "Pending")

    follow_up_date = latest_screening.get("follow_up_date")
    fu = _parse_date(follow_up_date)

    return {
        "has_data": True,
        "risk_level": risk_level,
        "fbs_score": latest["fbs"],
        "fbs_band": classify_fbs_band(latest["fbs"]),
        "total_screenings": len(visits),
        "latest_visit_date": latest["date"],
        "bmi": latest_visit_detail.get("bmi"),
        "waist_cm": latest_visit_detail.get("waist_cm"),
        "obesity_class": latest_visit_detail.get("obesity_class"),
        "follow_up_date": follow_up_date,
        "follow_up_overdue": bool(fu and fu < date.today()),
        "referred_to": latest_screening.get("referred_to"),
        "visits": visits,
    }


def get_full_screening_history(patient_id: int, sex: str | None = None) -> list[dict]:
    """
    One entry per visit, shaped for patient_health_results.html
    (screening-card + detail-view per visit).
    """
    visits = _screened_visits(patient_id)
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
        entry = {
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
            "heart_rate": visit_detail.get("heart_rate"),
            "respiratory_rate": visit_detail.get("respiratory_rate"),
            "height_cm": visit_detail.get("height_cm"),
            "weight_kg": visit_detail.get("weight_kg"),
            "patient_edit_pending": bool(
                visit_detail.get("edited_by_patient_at") and not visit_detail.get("edit_acknowledged_at")
            ),
            "patient_edited_fields": json.loads(visit_detail["edited_fields"]) if visit_detail.get("edited_fields") else [],
            "smoking_status": visit_detail.get("smoking_status"),
            "alcohol_intake": visit_detail.get("alcohol_intake"),
            "illicit_drug_use": visit_detail.get("illicit_drug_use"),
            "physical_activity": visit_detail.get("physical_activity"),
            "diabetes_diagnosis": visit_detail.get("diabetes_diagnosis"),
            "past_surgical_history": visit_detail.get("past_surgical_history"),
            "menarche_age": visit_detail.get("menarche_age"),
            "lmp_date": visit_detail.get("lmp_date"),
            "gravida": visit_detail.get("gravida"),
            "para": visit_detail.get("para"),
            "conditions": conditions,
            "cvd_responses": cvd,
            "follow_up_date": screening.get("follow_up_date") if screening else None,
            "referred_to": screening.get("referred_to") if screening else None,
            "referral_action": screening.get("referral_action") if screening else None,
        }
        entry["reasons"] = explain_result(entry, sex)
        history.append(entry)
    _add_changes(history)
    return history


_TRACKED_KEYS = ("fbs_score", "bmi", "weight_kg", "waist_cm")


def _change(cur: dict, prev: dict, key: str):
    """Change of `key` from the previous (older) screening, or None if unknown/unchanged."""
    a, b = cur.get(key), prev.get(key)
    if a is None or b is None:
        return None
    diff = round(float(a) - float(b), 1)
    if diff == 0:
        return None
    return {"dir": "up" if diff > 0 else "down", "diff": abs(diff),
            "prev": b, "prev_date": prev["date"]}


def _fmt_bp(v: dict) -> str:
    s, d = v.get("bp_systolic"), v.get("bp_diastolic")
    return f"{s:g}/{d:g}" if s is not None and d is not None else "-"


def _add_changes(history: list[dict]) -> None:
    """
    history is newest-first, so the previous screening is the next item.
    Adds entry["trend"] = {"fbs_score": {...}, "bmi": {...}, "weight_kg": {...},
    "waist_cm": {...}, "bp": {...}}; a key is missing when there is no change.
    """
    for i, cur in enumerate(history):
        prev = history[i + 1] if i + 1 < len(history) else None
        changes = {}
        if prev:
            for key in _TRACKED_KEYS:
                c = _change(cur, prev, key)
                if c:
                    changes[key] = c
            bp = _change(cur, prev, "bp_systolic") or _change(cur, prev, "bp_diastolic")
            if bp:
                bp["prev"] = _fmt_bp(prev)
                changes["bp"] = bp
        cur["trend"] = changes


def build_trend(history: list[dict]) -> list[dict]:
    """Oldest -> newest FBS points for the trend chart."""
    return [{"date": h["date"], "fbs": h["fbs_score"]}
            for h in reversed(history) if h["fbs_score"] is not None]

def explain_result(v: dict, sex: str | None) -> list[str]:
    """Plain-language reasons from one history entry (shape of get_full_screening_history)."""
    reasons = []
    fbs = v.get("fbs_score")
    if fbs is not None and fbs >= 126:
        reasons.append(f"Your fasting blood sugar was {fbs} mg/dL, which is in the diabetic range (126 or higher).")
    elif fbs is not None and fbs >= 100:
        reasons.append(f"Your fasting blood sugar was {fbs} mg/dL. Normal is below 100, so yours is slightly high.")

    obesity = (v.get("obesity_class") or "").lower()
    if "overweight" in obesity or "obese" in obesity:
        reasons.append("Your weight is above the healthy range, which raises diabetes risk.")

    waist = v.get("waist_cm")
    limit = 80 if (sex or "").lower() == "female" else 90
    if waist and waist >= limit:
        reasons.append("Your waist size is larger than recommended.")

    if v["conditions"].get("family_history"):
        reasons.append("A close family member has diabetes or a related condition.")
    if v["conditions"].get("dm_symptom"):
        reasons.append("You reported symptoms that can go with high blood sugar.")
    if (v.get("bp_systolic") or 0) >= 130:
        reasons.append("Your blood pressure was a bit high.")

    return reasons or ["No major risk factors were found in this screening."]


def get_dashboard_extras(patient_id: int, sex: str | None) -> dict:
    history = get_full_screening_history(patient_id, sex)
    screened = [h for h in history if h["fbs_score"] is not None]
    return {
        "history": history,
        "reasons": explain_result(screened[0], sex) if screened else [],
        "trend": [{"date": h["date"], "fbs": h["fbs_score"]} for h in reversed(screened)],
    }

def get_self_reported_fbs(patient_id: int) -> list[dict]:
    return [
        {**e, "band": classify_fbs_band(e["fbs_mg_dl"]),
         "reviewed": e["review_status"] != "unreviewed"}
        for e in patient_fbs_model.list_entries_for_patient(patient_id, limit=10)
    ]