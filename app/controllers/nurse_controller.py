from flask import Blueprint, render_template, request, jsonify, abort, redirect, url_for, Response, current_app, session, flash, send_from_directory
from app.models import patient_model, visit_model, lab_model, lookup_model, health_analytics_model, audit_model
from app.db import get_db
from app.controllers import auth_controller, metrics_controller
from datetime import date as date_cls
from app.rate_limit import rate_limit
from app.controllers import patient_auth_controller
import os


nurse_bp = Blueprint('nurse', __name__)
from app.views.auth_views import require_role_for_blueprint

# Serves FBS-Thesis/data/psgc_data.json without needing it inside static/.
@nurse_bp.route('/nurse-data/<path:filename>')
def nurse_static_data(filename):
    project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    data_dir = os.path.join(project_root, "data")
    return send_from_directory(data_dir, filename)  
require_role_for_blueprint(nurse_bp, "health_worker", "medical_officer")


@nurse_bp.app_context_processor
def inject_pending_patient_edits():
    """Lets every nurse_base.html-extending page show the notification bell
    count without each route remembering to pass it in."""
    try:
        return {"pending_patient_edits_count": visit_model.count_pending_patient_edits()}
    except Exception:
        return {"pending_patient_edits_count": 0}


@nurse_bp.route('/nurse/patient-edits')
def nurse_patient_edits():
    """Notification bell dropdown contents: visits a patient has edited
    from the portal that no nurse has acknowledged yet."""
    edits = visit_model.list_pending_patient_edits()
    return jsonify({
        "count": len(edits),
        "edits": [{
            "visit_id": e["visit_id"],
            "patient_code": e["patient_code"],
            "patient_name": f'{e["first_name"]} {e["last_name"]}',
            "edited_at": e["edited_by_patient_at"],
            "fields": e["edited_fields"],
            "previous": e["patient_edit_previous_values"],
            "patient_file_url": url_for('nurse.nurse_patient_file_view', patient_id=e["patient_code"], visit_id=e["visit_id"]),
        } for e in edits],
    })


@nurse_bp.route('/nurse/patient-edits/<int:visit_id>/acknowledge', methods=['POST'])
def nurse_acknowledge_patient_edit(visit_id):
    visit_model.acknowledge_patient_edit(visit_id, staff_id=session.get("user_id"))
    return jsonify({"ok": True})



def _audit_event(action, severity="Info"):
    audit_model.log_event(
        get_db(), user_id=session.get("user_id"), user_name=session.get("user_name", "unknown"),
        role=session.get("user_role", "Unknown"), action=action,
        ip_address=request.remote_addr, severity=severity,
    )


def _resolve_barangay(patient_data):
    """
    Pop the region/city/barangay fields nurse_intake.js sends and resolve
    them to a barangay_id, mutating patient_data in place.

    barangay_code is authoritative (PSGC) and is preferred whenever it's
    present -- barangay_name alone is ambiguous once more than one
    region/city is in play (see 0024_add_psgc_to_barangays.sql). Only
    when no code was sent (the manual-entry fallback for a city with no
    PSGC barangay list) do we fall back to a best-effort name match,
    which now creates the barangay instead of rejecting the intake.
    """
    barangay_code = patient_data.pop("barangay_code", None)
    barangay_name = patient_data.pop("barangay_name", None)
    city_code = patient_data.pop("city_code", None)
    city_name = patient_data.pop("city_name", None)
    region_code = patient_data.pop("region_code", None)
    region_name = patient_data.pop("region_name", None)

    if barangay_code and barangay_name:
        return lookup_model.get_or_create_barangay(
            barangay_code, barangay_name, city_code, city_name, region_code, region_name
        )
    if barangay_name:
        return lookup_model.get_or_create_barangay_by_name(barangay_name)
    return None


@nurse_bp.route('/nurse/dashboard')
def nurse_dashboard():
    summary = health_analytics_model.get_dashboard_summary()
    risk_status = health_analytics_model.get_risk_status_distribution()
    timeline = health_analytics_model.get_screening_volume_timeline(level="year")
    top_barangays = health_analytics_model.get_top_barangays()
    recent = health_analytics_model.get_recent_registries()
    summary_changes = health_analytics_model.get_dashboard_changes()
    actual_vs_predicted = health_analytics_model.get_actual_vs_predicted()

    risk_counts = {
        "Low": risk_status.get("Low", 0),
        "Moderate": risk_status.get("Moderate", 0),
        "High": risk_status.get("High", 0),
    }
    total = sum(risk_counts.values())

    if total:
        risk_data = [
            round(risk_counts["Low"] / total * 100, 1),
            round(risk_counts["Moderate"] / total * 100, 1),
            round(risk_counts["High"] / total * 100, 1),
        ]
    else:
        risk_data = [0, 0, 0]

    return render_template(
        'nurse/nurse_dashboard.html',
        summary=summary,
        summary_changes=summary_changes,
        change_label='vs last week',
        actual_vs_predicted=actual_vs_predicted,
        risk_data=risk_data,
        risk_counts=risk_counts,  
        risk_total=total,          
        timeline=timeline,
        top_barangays=top_barangays,
        recent=recent,
        barangays=lookup_model.list_barangays(),
        active_page='dashboard',
    )
@nurse_bp.route('/nurse/intake')
def nurse_intake():
    return render_template('nurse/nurse_intake.html', barangays=lookup_model.list_barangays(), active_page='intake')


_REQUIRED_VISIT_FIELDS_ON_SUBMIT = {
    "smoking_status": "Smoking",
    "alcohol_intake": "Alcohol Intake",
    "illicit_drug_use": "Illicit Drug Use",
    "bp_systolic": "Systolic BP",
    "bp_diastolic": "Diastolic BP",
    "heart_rate": "Heart Rate",
    "respiratory_rate": "Respiratory Rate",
    "height_cm": "Height",
    "weight_kg": "Weight",
    "waist_cm": "Waist Circumference",
}


def _missing_required_visit_fields(visit_data: dict) -> list[str]:
    """
    Same required set nurse_intake.js / nurse_new_record.js enforce on
    submit -- re-checked here so a request that skips the JS (or a bug in
    it) can't sneak an incomplete "submitted" visit past validation. Only
    applies when status is "submitted"; a draft is allowed to be incomplete.
    """
    if visit_data.get("status") != "submitted":
        return []
    return [
        label for field, label in _REQUIRED_VISIT_FIELDS_ON_SUBMIT.items()
        if visit_data.get(field) in (None, "")
    ]


@nurse_bp.route('/api/patients', methods=['POST'])
@rate_limit(max_calls=10, period_seconds=60)
def create_patient():
    """
    Expects the JSON shape sent by static/js/nurse_intake.js:
    {
      "patient": { last_name, first_name, ..., barangay_name, ... },
      "visit": { assessment_date, ..., status },
      "conditions": { "pmh": [...], "family_history": [...], "diet": [...],
                       "immunization": [...], "dm_symptom": [...] },
      "cvd_responses": { "q1_chest_discomfort": true, ... }
    }
    """
    payload = request.get_json(silent=True) or {}
    patient_data = dict(payload.get("patient", {}))
    visit_data = payload.get("visit", {})
    conditions = payload.get("conditions", {})
    cvd_answers = payload.get("cvd_responses", {})

    required_patient = ("last_name", "first_name", "birthdate", "sex")
    missing = [f for f in required_patient if not patient_data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required patient fields: {', '.join(missing)}"}), 400
    if not visit_data.get("assessment_date"):
        return jsonify({"error": "Missing required visit field: assessment_date"}), 400
    missing_visit = _missing_required_visit_fields(visit_data)
    if missing_visit:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_visit)}"}), 400

    barangay_id = _resolve_barangay(patient_data)
    if barangay_id is not None:
        patient_data["barangay_id"] = barangay_id

    staff_id = None  # wire up once auth/session (staff table) is in place

    patient_id = patient_model.create_patient(patient_data, staff_id=staff_id)
    visit_id = visit_model.create_visit(patient_id, "intake", visit_data, staff_id=staff_id)

    for category, codes in conditions.items():
        if codes:
            visit_model.save_visit_conditions(visit_id, category, codes)

    if cvd_answers:
        visit_model.save_cvd_responses(visit_id, cvd_answers)

    patient_code = patient_model.get_patient_code_by_id(patient_id)
    _audit_event(f"Patient created with intake visit: {patient_code}", "Success")

    return jsonify({
        "message": "Patient created and intake visit recorded.",
        "patient": {"id": patient_id, "patient_code": patient_code},
        "visit_id": visit_id,
    }), 201


@nurse_bp.route('/api/patients/<patient_id>/records', methods=['POST'])
def create_followup_record(patient_id):
    """
    patient_id here is the patient_code, matching /nurse_new_record/<patient_id>.
    Creates a follow-up visit under the SAME patient instead of a new patient row.
    """
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    demographic_updates = payload.get("patient", {})
    visit_data = payload.get("visit", {})
    conditions = payload.get("conditions", {})
    cvd_answers = payload.get("cvd_responses", {})

    if not visit_data.get("assessment_date"):
        return jsonify({"error": "Missing required visit field: assessment_date"}), 400
    missing_visit = _missing_required_visit_fields(visit_data)
    if missing_visit:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_visit)}"}), 400

    staff_id = None

    if demographic_updates:
        barangay_id = _resolve_barangay(demographic_updates)
        if barangay_id is not None:
            demographic_updates["barangay_id"] = barangay_id
        patient_model.update_patient(patient["id"], demographic_updates)

    visit_id = visit_model.create_visit(patient["id"], "follow_up", visit_data, staff_id=staff_id)

    for category, codes in conditions.items():
        if codes:
            visit_model.save_visit_conditions(visit_id, category, codes)

    if cvd_answers:
        visit_model.save_cvd_responses(visit_id, cvd_answers)

    _audit_event(f"Follow-up visit created: {patient_id} (visit: {visit_id})", "Success")
    if demographic_updates:
        _audit_event(f"Patient record edited: {patient_id} (patient_id: {patient['id']})", "Info")

    return jsonify({
        "message": "Follow-up visit recorded.",
        "patient_code": patient_id,
        "visit_id": visit_id,
    }), 201

@nurse_bp.route('/nurse/screening/<patient_id>/<int:visit_id>/submit', methods=['POST'])
def nurse_screening_submit(patient_id, visit_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    visits = visit_model.list_visits_for_patient(patient["id"])
    if not any(v["visit_id"] == visit_id for v in visits):
        abort(404)

    referred_to = (request.form.get("referred_to") or "").strip()
    if patient_model.is_doctor_like_referral(referred_to):
        flash("Referred To must be a facility (e.g. SRCHO, LHU I), not a doctor's name.", "error")
        return redirect(url_for('nurse.nurse_screening', patient_id=patient_id, visit_id=visit_id))

    clinical_notes = (request.form.get("clinical_notes") or "").strip()
    if not clinical_notes:
        flash('Clinical Notes is required. Type "None" if there is nothing to note.', "error")
        return redirect(url_for('nurse.nurse_screening', patient_id=patient_id, visit_id=visit_id))
    visit_model.update_clinical_notes(visit_id, clinical_notes)

    fbs_raw = float(request.form["fbs_mg_dl"])
    fbs_unit = (request.form.get("fbs_unit") or "mg_dl").strip().lower()
    if fbs_unit in ("mmol_l", "mmol/l", "mmol"):
        # Standard clinical conversion factor for glucose.
        fbs_mg_dl = round(fbs_raw * 18.0182, 1)
    else:
        fbs_mg_dl = fbs_raw

    data = {
        "fbs_mg_dl": fbs_mg_dl,
        "fbs_entered_value": fbs_raw,
        "fbs_entered_unit": fbs_unit,
        "test_method": request.form.get("test_method"),
        "glucometer_id": request.form.get("glucometer_id"),
        "test_datetime": request.form.get("test_datetime"),
        "final_risk_level": request.form.get("final_risk_level"),
        "fasted_ge_8h": request.form.get("fasted_ge_8h"),
        "identity_verified": request.form.get("identity_verified"),
        "glucometer_calibrated": request.form.get("glucometer_calibrated"),
        "capillary_sample_taken": request.form.get("capillary_sample_taken"),
        "consent_signed": request.form.get("consent_signed"),
        "result_recorded_within_5min": request.form.get("result_recorded_within_5min"),
        "referral_action": request.form.get("referral_action"),
        "follow_up_date": request.form.get("follow_up_date"),
        "referred_to": referred_to or None,
    }

    lab_screening_id = lab_model.create_lab_screening(visit_id, data)
    _audit_event(f"Screening saved: {patient_id} (visit: {visit_id})", "Success")

    # ML + GREEN COMPUTING
    # Keep the nurse workflow on the same measured prediction path as the
    # dedicated Green API. This records one green_computing_log row per
    # inference and links it to the lab screening that triggered it.
    # The Predictor falls back to the clearly-labelled stub when no trained
    # model is installed, so the GREEN pipeline can still be exercised on
    # Android/Termux.
    prediction = metrics_controller.run_measured_prediction(
        get_db(),
        current_app.extensions["predictor"],
        current_app.extensions["battery"],
        {"fbs_mg_dl": data["fbs_mg_dl"]},
        lab_screening_id=lab_screening_id,
    )
    lab_model.set_model_prediction(
        visit_id,
        prediction["model_predicted_risk_level"],
        prediction["model_confidence"],
    )

    # A screening being completed is what actually finalizes a visit --
    # nurse_data_management's "Draft" badge is driven by visits.status,
    # so without this a visit stays "draft" forever even after its
    # screening (and risk prediction) is fully done.
    visit_model.update_visit(visit_id, {"status": "submitted"})

    flash("Screening saved.", "success")
    return redirect(url_for('nurse.nurse_data_management', just_saved=1))


@nurse_bp.route('/nurse/screening/<patient_id>')
@nurse_bp.route('/nurse/screening/<patient_id>/<int:visit_id>')
def nurse_screening(patient_id, visit_id=None):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    visits = visit_model.list_visits_for_patient(patient["id"])

    if visit_id is not None:
        if not any(v["visit_id"] == visit_id for v in visits):
            abort(404)
        selected_visit_id = visit_id
    else:
        selected_visit_id = visits[0]["visit_id"] if visits else None

    is_latest = bool(visits) and selected_visit_id == visits[0]["visit_id"]

    latest_visit = None
    existing_screening = None
    if selected_visit_id is not None:
        latest_visit = visit_model.get_visit_by_id(selected_visit_id)
        latest_visit["visit_id"] = latest_visit["id"]
        latest_visit["date"] = latest_visit["assessment_date"]
        existing_screening = lab_model.get_lab_screening_for_visit(selected_visit_id)

    return render_template(
        'nurse/nurse_screening.html',
        patient_id=patient_id,
        patient=patient,
        latest_visit=latest_visit,
        visits=visits,
        existing_screening=existing_screening,
        is_latest=is_latest,
        active_page='intake',
    )

@nurse_bp.route('/nurse/patient_file_view/<patient_id>')
@nurse_bp.route('/nurse/patient_file_view/<patient_id>/<int:visit_id>')
def nurse_patient_file_view(patient_id, visit_id=None):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    records = visit_model.list_visits_for_patient(patient["id"])

    if visit_id is not None:
        if not any(v["visit_id"] == visit_id for v in records):
            abort(404)
        selected_visit_id = visit_id
    else:
        selected_visit_id = records[0]["visit_id"] if records else None

    latest_visit = None
    conditions = {"pmh": [], "family_history": [], "diet": [], "immunization": [], "dm_symptom": []}
    cvd_responses = None
    existing_screening = None

    if selected_visit_id is not None:
        latest_visit = visit_model.get_visit_by_id(selected_visit_id)
        latest_visit["visit_id"] = latest_visit["id"]        
        latest_visit["date"] = latest_visit["assessment_date"]  
        conditions = visit_model.get_conditions_for_visit(selected_visit_id)
        cvd_responses = visit_model.get_cvd_responses_for_visit(selected_visit_id)
        existing_screening = lab_model.get_lab_screening_for_visit(selected_visit_id)

    return render_template(
        'nurse/nurse_patient_file_view.html',
        patient_id=patient_id,
        patient=patient,
        records=records,
        latest_visit=latest_visit,
        conditions=conditions,
        cvd_responses=cvd_responses,
        existing_screening=existing_screening,
        active_page='data_management',
        # Carries the Data Management page's filters/page/entries back through
        # so "Back to Data Management" restores exactly where the nurse was,
        # instead of resetting to page 1 with no filters applied.
        return_qs=request.args.get('return_qs', ''),
    )

@nurse_bp.route('/nurse/patient_file_view/<patient_id>/<int:visit_id>/edit', methods=['POST'])
def nurse_patient_file_edit(patient_id, visit_id):
    """
    Edit endpoint for the Data Management "Patient Record" page. Updates
    patient demographics and visit-level clinical fields (history,
    lifestyle, CVD questionnaire, vitals, PE findings) for one visit.
    Deliberately does NOT touch lab_screenings -- test results (FBS,
    test method, risk level, etc.) are never editable from here; that
    stays on the dedicated Lab Screening page.
    """
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    visits = visit_model.list_visits_for_patient(patient["id"])
    if not any(v["visit_id"] == visit_id for v in visits):
        abort(404)

    visit_row = visit_model.get_visit_by_id(visit_id)
    is_draft = bool(visit_row and visit_row.get("status") == "draft")

    payload = request.get_json(silent=True) or {}
    demographic_updates = dict(payload.get("patient", {}))
    visit_data = dict(payload.get("visit", {}))
    conditions = payload.get("conditions", {})
    cvd_answers = payload.get("cvd_responses", {})

    # assessment_date / birthdate are NOT NULL columns. A null here means
    # the field was left untouched (or its stored value didn't parse into
    # the <input type="date">, e.g. a non-ISO date from an old CSV import)
    # -- never a deliberate clear, since the UI has no way to blank a
    # required date on purpose. Drop rather than null out either column.
    if visit_data.get("assessment_date") is None:
        visit_data.pop("assessment_date", None)
    if demographic_updates.get("birthdate") is None:
        demographic_updates.pop("birthdate", None)

    try:
        if demographic_updates:
            # Same PSGC-code-first resolver used by intake and nurse_new_record,
            # so this edit form's region/city/barangay cascade resolves the same
            # way instead of falling back to an ambiguous name-only match.
            barangay_id = _resolve_barangay(demographic_updates)
            if barangay_id is not None:
                demographic_updates["barangay_id"] = barangay_id
            # Name is normally only correctable while the visit is still a
            # draft -- EXCEPT a married female patient, whose last name can
            # legitimately change after marriage. Use the post-edit values
            # (falling back to what's already on file) so this also works the
            # same turn she sets Sex/Civil Status. The server re-checks this
            # itself rather than trusting the client, so a crafted request
            # can't sneak a rename in outside these two cases.
            effective_sex = demographic_updates.get("sex", patient["sex"])
            effective_civil_status = demographic_updates.get("civil_status", patient["civil_status"])
            is_married_female = effective_sex == "Female" and effective_civil_status == "Married"
            patient_model.update_patient(
                patient["id"], demographic_updates,
                allow_name_edit=is_draft or is_married_female,
            )

        if visit_data:
            visit_model.update_visit(visit_id, visit_data)

        for category, codes in conditions.items():
            visit_model.replace_visit_conditions(visit_id, category, codes)

        if cvd_answers:
            visit_model.save_cvd_responses(visit_id, cvd_answers)
    except Exception as e:
        # Surface the real reason instead of a bare 500 -- the frontend
        # shows this in its "Could not save changes" alert, so a data
        # problem (bad barangay match, a constraint violation, etc.) is
        # actually diagnosable instead of only ever generic.
        current_app.logger.exception("nurse_patient_file_edit failed for %s/%s", patient_id, visit_id)
        return jsonify({"error": f"Could not save: {e}"}), 400

    _audit_event(f"Patient record edited via Data Management: {patient_id} (visit: {visit_id})", "Info")
    return jsonify({"message": "Record updated."}), 200


@nurse_bp.route('/nurse/new_record/<patient_id>')
def nurse_new_record(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    return render_template(
        'nurse/nurse_new_record.html',
        patient_id=patient_id,
        patient=patient,
        barangays=lookup_model.list_barangays(),
        active_page='data_management',
    )


@nurse_bp.route('/nurse/health_results')
def nurse_health_results():
    worklist = health_analytics_model.get_followup_worklist()
    risk = health_analytics_model.get_risk_status_distribution()
    return render_template(
        'nurse/nurse_health_results.html',
        active_page='health_results',
        risk=risk,
        risk_total=sum(risk.get(k, 0) for k in ("Low", "Moderate", "High")),
        followup=health_analytics_model.get_followup_summary(),
        referral=health_analytics_model.get_referral_funnel(),
        worklist=worklist,
        worklist_barangays=sorted({w["barangay"] for w in worklist if w["barangay"]}),
        red_flags=health_analytics_model.get_red_flags(),
        barangay_rows=health_analytics_model.get_barangay_summary(),
        quality=health_analytics_model.get_screening_quality(),
        daily_log=health_analytics_model.get_daily_log(),
        nurse_activity=health_analytics_model.get_nurse_activity(),
        report_date=date_cls.today().isoformat(),
    )

def _attach_pending_edits(patients):
    """Adds p['pending_edit'] = {'date', 'fields'} to patients whose own
    edits no nurse has acknowledged yet. Reuses the global bell's data."""
    pending = {}
    for e in visit_model.list_pending_patient_edits():
        entry = pending.setdefault(e["patient_code"], {"date": "", "fields": []})
        entry["date"] = max(entry["date"], str(e["edited_by_patient_at"])[:10])
        for f in (e["edited_fields"] or []):
            if f not in entry["fields"]:
                entry["fields"].append(f)
    patients = [dict(p) for p in patients]
    for p in patients:
        p["pending_edit"] = pending.get(p["patient_code"])
    return patients

@nurse_bp.route('/nurse/data_management')
def nurse_data_management():
    barangay = request.args.get('barangay') or None
    risk = request.args.get('risk') or None
    date = request.args.get('date') or None
    q = request.args.get('q') or None
    status = request.args.get('status') or None

    # Column sort (clickable table headers). Only whitelisted keys are honoured;
    # anything else falls back to the default newest-first order.
    sort = request.args.get('sort')
    if sort not in patient_model.PATIENT_SORT_KEYS:
        sort = None
    direction = 'desc' if request.args.get('dir') == 'desc' else 'asc'

    entries = request.args.get('entries', '10')
    page_size = int(entries) if entries.isdigit() else None  # None == "all"

    total = patient_model.count_patients_with_latest_screening(
        barangay=barangay, risk=risk, date=date, q=q, status=status
    )
    total_pages = max(1, -(-total // page_size)) if page_size else 1

    page = request.args.get('page', '1')
    page = int(page) if page.isdigit() else 1
    page = min(max(page, 1), total_pages)

    offset = (page - 1) * page_size if page_size else None

    patients = patient_model.list_patients_with_latest_screening(
        barangay=barangay, risk=risk, date=date, entries_limit=page_size, q=q, offset=offset, status=status,
        sort=sort, direction=direction,
    )
    patients = visit_model.attach_pending_patient_edits([dict(p) for p in patients])

    # Windowed page numbers so the pager stays a fixed width even with
    # hundreds of pages: first, last, current +/-1, with None marking a
    # "…" gap between non-adjacent numbers.
    page_numbers = []
    if total_pages <= 7:
        page_numbers = list(range(1, total_pages + 1))
    else:
        window = {1, total_pages, page, page - 1, page + 1}
        window = {p for p in window if 1 <= p <= total_pages}
        last = 0
        for p in sorted(window):
            if last and p - last > 1:
                page_numbers.append(None)
            page_numbers.append(p)
            last = p

    return render_template(
        'nurse/nurse_data_management.html',
        barangays=lookup_model.list_barangays(),
        patients=patients,
        selected_barangay=barangay,
        active_page='data_management',
        current_page=page,
        total_pages=total_pages,
        total_records=total,
        page_numbers=page_numbers,
        entries=entries,
        sort=sort,
        direction=direction,
    )

@nurse_bp.route('/nurse/data_management/acknowledge_edits/<patient_id>', methods=['POST'])
def nurse_data_management_acknowledge_edits(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)
    cleared = visit_model.acknowledge_patient_edits_for_patient(
        patient["id"], staff_id=session.get("user_id")
    )
    for e in visit_model.list_pending_patient_edits():
        if e["patient_code"] == patient_id:
            visit_model.acknowledge_patient_edit(e["visit_id"], staff_id=session.get("user_id"))
            cleared += 1
    _audit_event(f"Patient edits marked reviewed: {patient_id} ({cleared} visit(s))", "Info")
    qs = request.form.get('return_qs', '')
    target = url_for('nurse.nurse_data_management')
    return redirect(f"{target}?{qs}" if qs else target)

@nurse_bp.route('/nurse/dashboard/screening-volume')
def nurse_dashboard_screening_volume():
    """
    Drill-down data for the Screening Volume Timeline.
      ?level=month&year=2026            -> 12 months of that year
      ?level=week&year=2026&month=9     -> weeks of that month
    Returns ordered arrays (not a dict) so JSON key sorting can't scramble
    the x-axis.
    """
    level = request.args.get('level', 'year')
    try:
        data = health_analytics_model.get_screening_volume_timeline(
            level=level,
            year=request.args.get('year'),
            month=request.args.get('month'),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "level": level,
        "labels": list(data.keys()),
        "values": list(data.values()),
    })


@nurse_bp.route('/api/analytics/screening_trend')
def api_screening_trend():
    """
    Year > month > day drill-down for the Health Results line chart, three
    lines (Normal / Prediabetic / Diabetic).
      ?level=year
      ?level=month&year=2024
      ?level=day&year=2024&month=3
    """
    try:
        data = health_analytics_model.get_screening_trend(
            level=request.args.get('level', 'year'),
            year=request.args.get('year'),
            month=request.args.get('month'),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(data)


@nurse_bp.route('/nurse/dashboard/barangay-patients')
def nurse_dashboard_barangay_patients():
    barangay = request.args.get('barangay') or None
    if not barangay:
        return jsonify({"patients": []})
    patients = patient_model.list_patients_with_latest_screening(
        barangay=barangay, entries_limit=25
    )
    return jsonify({"patients": patients})


@nurse_bp.route('/nurse/privacy_security')
def nurse_privacy_security():
    audit_logs = audit_model.get_recent_logs_for_user(get_db(), session.get("user_id"))
    return render_template(
        'nurse/nurse_privacy_security.html',
        audit_logs=audit_logs,
        active_page='privacy',
    )


@nurse_bp.route('/nurse/privacy_security/change-password', methods=['POST'])
def nurse_change_password():
    errors = auth_controller.change_own_password(session["user_id"], request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for('nurse.nurse_privacy_security'))

    _audit_event("Password changed", "Warning")
    flash("Password changed successfully.", "success")
    return redirect(url_for('nurse.nurse_privacy_security'))


@nurse_bp.route('/nurse/patient/<patient_id>/delete', methods=['POST'])
def nurse_patient_delete(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)
    patient_model.soft_delete_patient(patient["id"])
    _audit_event(f"Patient soft-deleted: {patient_id}", "Critical")
    # Return to the same filtered/paged view the delete was clicked from,
    # instead of resetting Data Management back to page 1 with no filters.
    return_qs = request.form.get('return_qs', '')
    target = url_for('nurse.nurse_data_management')
    if return_qs:
        target = f"{target}?{return_qs}"
    return redirect(target)


@nurse_bp.route('/nurse/recycle_bin')
def nurse_recycle_bin():
    patient_model.purge_expired_deleted_patients()
    deleted_patients = patient_model.list_deleted_patients()
    return render_template('nurse/nurse_recycle_bin.html', deleted_patients=deleted_patients, active_page='data_management')


@nurse_bp.route('/nurse/patient/<patient_id>/restore', methods=['POST'])
def nurse_patient_restore(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)
    patient_model.restore_patient(patient["id"])
    _audit_event(f"Patient restored: {patient_id}", "Success")
    return redirect(url_for('nurse.nurse_recycle_bin'))


@nurse_bp.route('/nurse/patient/<patient_id>/purge', methods=['POST'])
def nurse_patient_purge(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)
    patient_model.purge_patient_permanently(patient["id"])
    _audit_event(f"Patient permanently purged: {patient_id}", "Critical")
    return redirect(url_for('nurse.nurse_recycle_bin'))

@nurse_bp.route('/nurse/data_management/recalculate_pending', methods=['POST'])
@rate_limit(max_calls=5, period_seconds=60)
def nurse_data_management_recalculate_pending():
    """
    One-click fix for screenings that ended up with no risk level at all --
    e.g. rows imported before the model_predicted_risk_level fallback was
    added to the listing queries, or any other edge case where the
    per-row prediction at import/screening time didn't run. Runs the same
    measured-prediction path nurse_screening_submit and CSV import use, so
    the nurse never has to open a patient's record just to force this.
    """
    pending = patient_model.list_screenings_missing_risk_prediction()
    for item in pending:
        prediction = metrics_controller.run_measured_prediction(
            get_db(),
            current_app.extensions["predictor"],
            current_app.extensions["battery"],
            {"fbs_mg_dl": item["fbs_mg_dl"]},
            lab_screening_id=item["lab_screening_id"],
        )
        lab_model.set_model_prediction(
            item["visit_id"],
            prediction["model_predicted_risk_level"],
            prediction["model_confidence"],
        )

    if pending:
        flash(f"Recalculated risk for {len(pending)} pending screening(s).", "success")
        _audit_event(f"Manually recalculated risk for {len(pending)} pending screening(s)", "Info")
    else:
        flash("No pending screenings needed recalculation.", "success")

    return redirect(url_for('nurse.nurse_data_management'))


@nurse_bp.route('/nurse/data_management/export', methods=['POST'])
@rate_limit(max_calls=5, period_seconds=60)
def nurse_data_management_export():
    from app.models import settings as settings_model

    if (session.get("user_role") == "health_worker" and
            not settings_model.is_role_export_enabled("health_worker")):
        flash("Export has been disabled for nurse accounts by an administrator.", "error")
        return redirect(url_for("nurse.nurse_data_management"))

    barangay = request.form.get('barangay') or request.args.get('barangay') or None
    risk = request.form.get('risk') or request.args.get('risk') or None
    date = request.form.get('date') or request.args.get('date') or None
    all_visits = request.form.get('all_visits') == 'true'

    # Auto-run risk prediction on any screening that has an FBS reading but
    # no risk level yet, so the exported CSV never shows "Pending" — it shows
    # the model's predicted level instead (flagged as such in risk_source).
    pending = patient_model.list_screenings_missing_risk_prediction(barangay=barangay, date=date)
    for item in pending:
        prediction = metrics_controller.run_measured_prediction(
            get_db(),
            current_app.extensions["predictor"],
            current_app.extensions["battery"],
            {"fbs_mg_dl": item["fbs_mg_dl"]},
            lab_screening_id=item["lab_screening_id"],
        )
        lab_model.set_model_prediction(
            item["visit_id"],
            prediction["model_predicted_risk_level"],
            prediction["model_confidence"],
        )
    if pending:
        _audit_event(f"Auto-predicted risk for {len(pending)} screening(s) prior to export", "Info")

    csv_content = patient_model.export_patients_csv(barangay=barangay, risk=risk, date=date, all_visits=all_visits)
    _audit_event("Exported CSV: patient data", "Warning")

    filename = f"srcho_fbs_export_{date_cls.today().isoformat()}.csv"

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@nurse_bp.route('/nurse/patient/<patient_id>/export')
def nurse_patient_export_all(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    csv_content = patient_model.export_single_patient_csv(patient_id, all_visits=True)
    _audit_event(f"Exported CSV: patient {patient_id}", "Warning")
    filename = f"{patient_id}_full_history_{date_cls.today().isoformat()}.csv"

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@nurse_bp.route('/nurse/patient/<patient_id>/export/<int:visit_id>')
def nurse_patient_export_visit(patient_id, visit_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    visits = visit_model.list_visits_for_patient(patient["id"])
    if not any(v["visit_id"] == visit_id for v in visits):
        abort(404)
    full_csv = patient_model.export_single_patient_csv(patient_id, all_visits=True)
    lines = full_csv.splitlines()
    header = lines[0]
    target_visit = next(v for v in visits if v["visit_id"] == visit_id)
    matching_lines = [ln for ln in lines[1:] if f",{target_visit['date']}," in ln]

    csv_content = header + "\n" + "\n".join(matching_lines)
    _audit_event(f"Exported CSV: patient {patient_id}, visit {visit_id}", "Warning")
    filename = f"{patient_id}_visit_{target_visit['date']}_{date_cls.today().isoformat()}.csv"

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@nurse_bp.route('/api/analytics/health_results')
def api_health_results():
    return jsonify({
        "fbs": health_analytics_model.get_fbs_distribution(),
        "status": health_analytics_model.get_risk_status_distribution(),
        "age": health_analytics_model.get_age_distribution(),
        "sex": health_analytics_model.get_sex_distribution(),
        "bmi": health_analytics_model.get_bmi_distribution(),
        "bp": health_analytics_model.get_bp_distribution(),
        "hypertension": health_analytics_model.get_hypertension_history_distribution(),
        "waist": health_analytics_model.get_waist_distribution(),
        "smoking": health_analytics_model.get_smoking_distribution(),
        "family": health_analytics_model.get_family_history_distribution(),
        "barangay_matrix": health_analytics_model.get_barangay_risk_matrix(),
        "risk_by_sex": health_analytics_model.get_risk_by_sex(),
        "risk_by_age": health_analytics_model.get_risk_by_age(),
        "monthly_trend": health_analytics_model.get_monthly_risk_trend(),
    })

@nurse_bp.route('/nurse/data_management/import_template')
def nurse_data_management_import_template():
    xlsx_bytes = patient_model.generate_import_template_xlsx()
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=patient_import_template.xlsx"}
    )


@nurse_bp.route('/nurse/data_management/import', methods=['POST'])
@rate_limit(max_calls=5, period_seconds=60)
def nurse_data_management_import():
    file = request.files.get('csv_import')
    if file is None or file.filename == '':
        return jsonify({"error": "No file selected."}), 400
    if not file.filename.lower().endswith('.csv'):
        return jsonify({"error": "Only .csv files are accepted."}), 400

    staff_id = None  # wire ng auth sesh
    result = patient_model.import_patients_from_csv(file.stream, staff_id=staff_id)

    # Run the actual trained model on every row that came in with an FBS
    # reading, same measured-prediction path the manual screening submit
    # route uses -- so an imported record shows the model's risk level
    # immediately instead of sitting on the naive glucose-cutoff
    # preliminary classification (or "Pending" on pages that key off
    # model_predicted_risk_level specifically).
    predicted = 0
    for item in result.get("screened_for_prediction", []):
        prediction = metrics_controller.run_measured_prediction(
            get_db(),
            current_app.extensions["predictor"],
            current_app.extensions["battery"],
            {"fbs_mg_dl": item["fbs_mg_dl"]},
            lab_screening_id=item["lab_screening_id"],
        )
        lab_model.set_model_prediction(
            item["visit_id"],
            prediction["model_predicted_risk_level"],
            prediction["model_confidence"],
        )
        predicted += 1
    result.pop("screened_for_prediction", None)

    _audit_event(
        f"Imported CSV: {result['new_patients']} new, {result['matched_existing']} matched, "
        f"{result['skipped']} skipped, {predicted} auto-predicted",
        "Warning",
    )

    return jsonify({
        "message": (
            f"Import complete: {result['new_patients']} new patient(s) created, "
            f"{result['matched_existing']} visit(s) matched to existing patients, "
            f"{result['skipped']} row(s) skipped"
            + (f", {predicted} screening(s) auto-predicted by the model." if predicted else ".")
        ),
        **result
    }), 200


@nurse_bp.route('/nurse/patient/<patient_id>/issue_portal_credentials', methods=['POST'])
@rate_limit(max_calls=10, period_seconds=60)
def nurse_issue_portal_credentials(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    temp_password = patient_auth_controller.issue_patient_credentials(
        patient["id"], staff_id=session.get("user_id")
    )
    _audit_event(f"Portal credentials issued: {patient_id}", "Warning")

    return render_template(
        'nurse/nurse_patient_credentials_slip.html',
        patient=patient, temp_password=temp_password,
    )