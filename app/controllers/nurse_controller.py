from flask import Blueprint, render_template, request, jsonify, abort, redirect, url_for, Response
from app.models import patient_model, visit_model, lab_model, lookup_model, health_analytics_model, ml_model
from app.models.db import get_connection
from datetime import date as date_cls
from app.rate_limit import rate_limit


nurse_bp = Blueprint('nurse', __name__)

# Front-line staff only. Both roles can use the nurse workspace today; split this into two
# blueprints later if medical_officer should eventually get a separate, more limited view here.
from app.views.auth_views import require_role_for_blueprint  # noqa: E402 (after Blueprint())
require_role_for_blueprint(nurse_bp, "health_worker", "medical_officer")


@nurse_bp.route('/nurse_dashboard')
def nurse_dashboard():
    summary = health_analytics_model.get_dashboard_summary()
    risk_status = health_analytics_model.get_risk_status_distribution()
    timeline = health_analytics_model.get_screening_volume_timeline()
    top_barangays = health_analytics_model.get_top_barangays()
    recent = health_analytics_model.get_recent_registries()

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
        risk_data=risk_data,
        risk_counts=risk_counts,  
        risk_total=total,          
        timeline=timeline,
        top_barangays=top_barangays,
        recent=recent,
        active_page='dashboard',
    )
@nurse_bp.route('/nurse_intake')
def nurse_intake():
    return render_template('nurse/nurse_intake.html', barangays=lookup_model.list_barangays(), active_page='intake')


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

    barangay_name = patient_data.pop("barangay_name", None)
    if barangay_name:
        barangay_id = lookup_model.get_barangay_id(barangay_name)
        if barangay_id is None:
            return jsonify({"error": f"Unrecognized barangay: {barangay_name!r}"}), 400
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

    staff_id = None

    if demographic_updates:
        barangay_name = demographic_updates.pop("barangay_name", None)
        if barangay_name:
            barangay_id = lookup_model.get_barangay_id(barangay_name)
            if barangay_id is None:
                return jsonify({"error": f"Unrecognized barangay: {barangay_name!r}"}), 400
            demographic_updates["barangay_id"] = barangay_id
        patient_model.update_patient(patient["id"], demographic_updates)

    visit_id = visit_model.create_visit(patient["id"], "follow_up", visit_data, staff_id=staff_id)

    for category, codes in conditions.items():
        if codes:
            visit_model.save_visit_conditions(visit_id, category, codes)

    if cvd_answers:
        visit_model.save_cvd_responses(visit_id, cvd_answers)

    return jsonify({
        "message": "Follow-up visit recorded.",
        "patient_code": patient_id,
        "visit_id": visit_id,
    }), 201

@nurse_bp.route('/nurse_screening/<patient_id>/<int:visit_id>/submit', methods=['POST'])
def nurse_screening_submit(patient_id, visit_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    visits = visit_model.list_visits_for_patient(patient["id"])
    if not any(v["visit_id"] == visit_id for v in visits):
        abort(404)

    data = {
        "fbs_mg_dl": float(request.form["fbs_mg_dl"]),
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
        "referred_to": request.form.get("referred_to"),
    }

    lab_model.create_lab_screening(visit_id, data)

    # ML PREDICTION 
    visit = visit_model.get_visit_by_id(visit_id)
    conditions = visit_model.get_conditions_for_visit(visit_id)
    try:
        risk_level, confidence = ml_model.predict_risk(visit, patient, conditions)
        lab_model.set_model_prediction(visit_id, risk_level, confidence)
    except FileNotFoundError:
        pass  # no model file 

    return redirect(url_for('nurse.nurse_screening', patient_id=patient_id, visit_id=visit_id))


@nurse_bp.route('/nurse_screening/<patient_id>')
@nurse_bp.route('/nurse_screening/<patient_id>/<int:visit_id>')
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

@nurse_bp.route('/nurse_patient_file_view/<patient_id>')
@nurse_bp.route('/nurse_patient_file_view/<patient_id>/<int:visit_id>')
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
    )

@nurse_bp.route('/nurse_new_record/<patient_id>')
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


@nurse_bp.route('/nurse_health_results')
def nurse_health_results():
    # TODO: no model backs this page yet 
    return render_template('nurse/nurse_health_results.html', active_page='health_results')


@nurse_bp.route('/nurse_data_management')
def nurse_data_management():
    barangay = request.args.get('barangay') or None
    risk = request.args.get('risk') or None
    date = request.args.get('date') or None
    entries = request.args.get('entries')
    entries_limit = int(entries) if entries and entries.isdigit() else None

    patients = patient_model.list_patients_with_latest_screening(
        barangay=barangay, risk=risk, date=date, entries_limit=entries_limit
    )

    return render_template(
        'nurse/nurse_data_management.html',
        barangays=lookup_model.list_barangays(),
        patients=patients,
        selected_barangay=barangay,
        active_page='data_management',
    )


@nurse_bp.route('/nurse_privacy_security')
def nurse_privacy_security():
    # TODO: needs a staff_model + logged-in 

    return render_template('nurse/nurse_privacy_security.html', active_page='privacy')


@nurse_bp.route('/nurse_patient/<patient_id>/delete', methods=['POST'])
def nurse_patient_delete(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)
    patient_model.soft_delete_patient(patient["id"])
    return redirect(url_for('nurse.nurse_data_management'))


@nurse_bp.route('/nurse_recycle_bin')
def nurse_recycle_bin():
    patient_model.purge_expired_deleted_patients()
    deleted_patients = patient_model.list_deleted_patients()
    return render_template('nurse/nurse_recycle_bin.html', deleted_patients=deleted_patients, active_page='data_management')


@nurse_bp.route('/nurse_patient/<patient_id>/restore', methods=['POST'])
def nurse_patient_restore(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)
    patient_model.restore_patient(patient["id"])
    return redirect(url_for('nurse.nurse_recycle_bin'))


@nurse_bp.route('/nurse_patient/<patient_id>/purge', methods=['POST'])
def nurse_patient_purge(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)
    patient_model.purge_patient_permanently(patient["id"])
    return redirect(url_for('nurse.nurse_recycle_bin'))

@nurse_bp.route('/nurse_data_management/export', methods=['POST'])
@rate_limit(max_calls=5, period_seconds=60)
def nurse_data_management_export():
    barangay = request.form.get('barangay') or request.args.get('barangay') or None
    risk = request.form.get('risk') or request.args.get('risk') or None
    date = request.form.get('date') or request.args.get('date') or None
    all_visits = request.form.get('all_visits') == 'true'

    csv_content = patient_model.export_patients_csv(barangay=barangay, risk=risk, date=date, all_visits=all_visits)

    filename = f"srcho_fbs_export_{date_cls.today().isoformat()}.csv"

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@nurse_bp.route('/nurse_patient/<patient_id>/export')
def nurse_patient_export_all(patient_id):
    patient = patient_model.get_patient_by_code(patient_id)
    if patient is None:
        abort(404)

    csv_content = patient_model.export_single_patient_csv(patient_id, all_visits=True)
    filename = f"{patient_id}_full_history_{date_cls.today().isoformat()}.csv"

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@nurse_bp.route('/nurse_patient/<patient_id>/export/<int:visit_id>')
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
    })

@nurse_bp.route('/nurse_data_management/import_template')
def nurse_data_management_import_template():
    csv_content = patient_model.generate_import_template_csv()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=patient_import_template.csv"}
    )


@nurse_bp.route('/nurse_data_management/import', methods=['POST'])
@rate_limit(max_calls=5, period_seconds=60)
def nurse_data_management_import():
    file = request.files.get('csv_import')
    if file is None or file.filename == '':
        return jsonify({"error": "No file selected."}), 400
    if not file.filename.lower().endswith('.csv'):
        return jsonify({"error": "Only .csv files are accepted."}), 400

    staff_id = None  # wire ng auth sesh
    result = patient_model.import_patients_from_csv(file.stream, staff_id=staff_id)

    return jsonify({
        "message": (
            f"Import complete: {result['new_patients']} new patient(s) created, "
            f"{result['matched_existing']} visit(s) matched to existing patients, "
            f"{result['skipped']} row(s) skipped."
        ),
        **result
    }), 200


