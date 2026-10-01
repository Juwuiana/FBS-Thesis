from flask import Blueprint, abort, current_app, flash, jsonify, render_template, request, session, redirect, url_for
from app.models import patient_portal_model, patient_model, visit_model, lookup_model, settings as settings_model
from app.controllers import patient_auth_controller
from flask import Response


patient_bp = Blueprint('patient', __name__)


@patient_bp.before_request
def _require_patient_login():
    if current_app.config.get("DEV_NO_AUTH"):
        return
    if request.endpoint in ("patient.patient_login",):
        return
    if (session.get("patient_id") and
            session.get("security_version") != settings_model.get_security_version("patient")):
        session.clear()
        flash("You've been signed out for security reasons. Please log in again.", "error")
        return redirect(url_for("patient.patient_login"))
    if not session.get("patient_id"):
        return redirect(url_for('patient.patient_login'))


@patient_bp.app_context_processor
def inject_current_patient():
    patient_id = patient_portal_model.get_current_patient_id()
    return {"patient": patient_model.get_patient_by_id(patient_id) if patient_id else None}


@patient_bp.route('/patient_login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'GET':
        return render_template('auth/patient_login.html')

    patient, error = patient_auth_controller.authenticate_patient(
        request.form.get('patient_code', ''), request.form.get('password', '')
    )
    if error:
        return render_template('auth/patient_login.html', error=error)

    if not settings_model.is_role_login_enabled("patient"):
        return render_template(
            'auth/patient_login.html',
            error="Patient portal access is temporarily disabled. Please contact your LHU.",
        )

    session.clear()
    session['patient_id'] = patient['id']
    session['security_version'] = settings_model.get_security_version("patient")
    patient_model.record_login_event(
        patient['id'],
        user_agent=request.headers.get('User-Agent'),
        ip_address=request.remote_addr,
    )
    return redirect(url_for('patient.patient_dashboard'))

@patient_bp.route('/patient_logout', methods=['GET', 'POST'])
def patient_logout():
    session.pop('patient_id', None)
    return redirect(url_for('patient.patient_login'))


@patient_bp.route('/patient_dashboard')
def patient_dashboard():
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    result = patient_portal_model.get_patient_dashboard_data(patient_id)
    extras = patient_portal_model.get_dashboard_extras(patient_id, patient.get("sex"))
    return render_template('patient/patient_dashboard.html', result=result, **extras)


@patient_bp.route('/patient_health_results')
def patient_health_results():
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    history = patient_portal_model.get_full_screening_history(patient_id, patient.get("sex"))
    trend = patient_portal_model.build_trend(history)
    return render_template(
        'patient/patient_health_results.html', history=history, trend=trend,
        location_has_provinces=lookup_model.psgc_has_provinces(),
    )


@patient_bp.route('/patient_settings', methods=['GET', 'POST'])
def patient_settings():
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    login_events = patient_model.get_recent_login_events(patient_id)

    if request.method == 'GET':
        return render_template(
            'patient/patient_settings.html',
            patient=patient,
            login_events=login_events,
            force_change=bool(patient.get('must_change_password')),
        )

    errors = patient_auth_controller.change_patient_password(patient, request.form)
    if errors:
        return render_template('patient/patient_settings.html', patient=patient,
                                login_events=login_events, message=errors[0], success=False)
    return render_template('patient/patient_settings.html', patient=patient,
                            login_events=login_events, message="Password updated.", success=True)

@patient_bp.route('/patient_download_data')
def patient_download_data():
    if not settings_model.is_role_export_enabled("patient"):
        flash("Data export is temporarily disabled by an administrator.", "error")
        return redirect(url_for('patient.patient_dashboard'))

    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    csv_data = patient_model.export_single_patient_csv(patient['patient_code'], all_visits=True)
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={patient["patient_code"]}_health_data.csv'}
    )

@patient_bp.route('/patient_health_results/<int:visit_id>/edit', methods=['POST'])
def patient_edit_visit(visit_id):
    """
    Lets a patient correct any field a nurse can edit on one of their own
    past visits, except status/assessment_date/pe_*/clinical_notes, which
    stay nurse-only -- see visit_model.PATIENT_EDITABLE_VISIT_FIELDS.
    FBS and the risk result are never editable here. Flags the visit so
    nurses see it in their notification bell.
    """
    # Dropdown fields post "" for their "— No change —" placeholder option --
    # that means "field left alone", not "clear this field". Free-text
    # fields (past_surgical_history, lmp_date) have no such placeholder, so
    # an empty value there is the patient deliberately blanking it out.
    _SELECT_FIELDS = {"smoking_status", "alcohol_intake", "illicit_drug_use",
                       "physical_activity", "diabetes_diagnosis"}

    patient_id = patient_portal_model.get_current_patient_id()
    fields = {}
    for key in visit_model.PATIENT_EDITABLE_VISIT_FIELDS:
        if key not in request.form:
            continue  # field wasn't part of this particular edit form at all
        raw = (request.form.get(key) or "").strip()
        if key in visit_model._NUMERIC_VISIT_FIELDS:
            if not raw:
                continue  # blank numeric field -- nothing submitted, don't clear it
            try:
                fields[key] = float(raw)
            except ValueError:
                flash(f"{key.replace('_', ' ').title()} must be a number.", "error")
                return redirect(url_for('patient.patient_health_results'))
        elif key in _SELECT_FIELDS:
            if raw:  # skip the "— No change —" placeholder entirely
                fields[key] = raw
        else:
            # free text (past_surgical_history, lmp_date, ...): "" is a
            # deliberate clear and goes through as-is.
            fields[key] = raw

    result = visit_model.patient_update_visit_vitals(visit_id, patient_id, fields)
    if result["ok"]:
        flash("Your changes were saved. Your health worker will review them.", "success")
    else:
        flash(result["error"], "error")
    return redirect(url_for('patient.patient_health_results'))


@patient_bp.route('/patient_location_options')
def patient_location_options():
    """Dropdown data for the address cascade (codes + names only).
    ?level=region | province&parent=<region code> | city&parent=<province or region code>
    | barangay&parent=<city code>"""
    level = request.args.get('level', 'region')
    if level not in lookup_model.LOCATION_LEVELS:
        return jsonify({"error": "Unknown level."}), 400
    parent = (request.args.get('parent') or '').strip() or None
    if level != 'region' and parent is None:
        return jsonify({"level": level, "options": []})
    try:
        options = lookup_model.psgc_location_options(level, parent)
    except (OSError, ValueError):
        return jsonify({"error": "Address options are unavailable right now."}), 503
    return jsonify({"level": level, "options": options})


@patient_bp.route('/patient_update_consent', methods=['POST'])
def patient_update_consent():
    patient_id = patient_portal_model.get_current_patient_id()
    consent = request.json.get('consent', False)
    patient_model.update_patient_consent(patient_id, consent)
    return {"ok": True}

@patient_bp.route('/patient_update_demographics', methods=['POST'])
def patient_update_demographics():
    """Patient corrects civil status, occupation and/or address. Name, ID,
    sex, age and assessment date are not accepted here. Each changed field
    flags the nurse through record_patient_profile_edit."""
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    back = url_for('patient.patient_health_results')

    allowed_status = {'Single', 'Married', 'Annulled', 'Widow/Widower', 'Separated'}
    civil = (request.form.get('civil_status') or '').strip()
    occupation = (request.form.get('occupation') or '').strip()
    if civil not in allowed_status:
        flash("Please choose a valid civil status.", "error")
        return redirect(back)
    if len(occupation) > 100:
        flash("Occupation must be 100 characters or fewer.", "error")
        return redirect(back)

    changes, flagged = {}, {}
    if civil != (patient.get('civil_status') or ''):
        changes['civil_status'] = civil
        flagged['civil_status'] = patient.get('civil_status')
    if occupation != (patient.get('occupation') or ''):
        changes['occupation'] = occupation or None
        flagged['occupation'] = patient.get('occupation')

    before_loc = patient_model.format_location(patient)
    region_code = (request.form.get('region_code') or '').strip()
    if region_code:
        barangay_id, error = lookup_model.resolve_psgc_location(
            region_code,
            (request.form.get('city_code') or '').strip(),
            (request.form.get('barangay_code') or '').strip(),
            (request.form.get('province_code') or '').strip() or None,
        )
        address = (request.form.get('address') or '').strip()
        if not error and len(address) > 200:
            error = "Street / house address must be 200 characters or fewer."
        if error:
            flash(error, "error")
            return redirect(back)
        changes['barangay_id'] = barangay_id
        changes['address'] = address or None

    if not changes:
        flash("Nothing to update.", "success")
        return redirect(back)

    patient_model.update_patient(patient_id, changes)

    after_loc = patient_model.format_location(patient_model.get_patient_by_id(patient_id))
    if after_loc != before_loc:
        flagged['location'] = before_loc

    if not flagged:
        flash("Everything is already up to date.", "success")
    else:
        for key, previous in flagged.items():
            visit_model.record_patient_profile_edit(patient_id, key, previous)
        flash("Your details were updated. Your health worker will be notified.", "success")
    return redirect(back)