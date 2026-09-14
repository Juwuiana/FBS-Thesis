"""
eto yung nakikita ng patients

"""
from app.models import visit_model, lab_model

_RISK_LABEL_MAP = {
    "Low": "Low Risk",
    "Moderate": "Moderate Risk",
    "High": "High Risk",
}


def get_patient_dashboard_data(patient_id: int) -> dict:
    """
    patient_id is the internal integer id (patients.id), NOT the
    patient_code string -- same convention visit_model already uses.

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

    risk_raw = latest["risk"]  # None if no lab_screening yet on this visit
    risk_level = _RISK_LABEL_MAP.get(risk_raw, "Pending")

    return {
        "has_data": True,
        "risk_level": risk_level,
        "fbs_score": latest["fbs"],
        "total_screenings": len(visits),
        "latest_visit_date": latest["date"],
        "bmi": latest_visit_detail.get("bmi") if latest_visit_detail else None,
        "waist_cm": latest_visit_detail.get("waist_cm") if latest_visit_detail else None,
        "obesity_class": latest_visit_detail.get("obesity_class") if latest_visit_detail else None,
        "follow_up_date": latest_screening.get("follow_up_date") if latest_screening else None,
        "referred_to": latest_screening.get("referred_to") if latest_screening else None,
        "visits": visits,
    }


def get_current_patient_id():
    """
    TODO(auth): replace this with the real logged-in patient's internal
    id once patient authentication is built, e.g.:

        from flask import session
        return session.get("patient_id")

    Raises on purpose for now. A route that silently fell back to a
    hardcoded/default patient_id would show one patient's private FBS
    results to anyone who visits the page -- that failure mode is worse
    than the page simply not working yet.
    """
    raise NotImplementedError(
        "Patient authentication isn't wired in yet. Whoever builds "
        "patient login should replace get_current_patient_id() with a "
        "real session lookup -- see the docstring for the exact shape "
        "expected by patient_controller.py."
    )