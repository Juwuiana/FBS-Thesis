from flask import Blueprint, current_app, render_template, request, session, redirect, url_for
from app.models import patient_portal_model, patient_model
from app.controllers import patient_auth_controller
from flask import Response


patient_bp = Blueprint('patient', __name__)


@patient_bp.before_request
def _require_patient_login():
    if current_app.config.get("DEV_NO_AUTH"):
        return
    if request.endpoint in ("patient.patient_login",):
        return
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

    session.clear()
    session['patient_id'] = patient['id']
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
    result = patient_portal_model.get_patient_dashboard_data(patient_id)
    return render_template('patient/patient_dashboard.html', result=result)


@patient_bp.route('/patient_health_results')
def patient_health_results():
    patient_id = patient_portal_model.get_current_patient_id()
    history = patient_portal_model.get_full_screening_history(patient_id)
    return render_template('patient/patient_health_results.html', history=history)


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
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    csv_data = patient_model.export_single_patient_csv(patient['patient_code'], all_visits=True)
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={patient["patient_code"]}_health_data.csv'}
    )

@patient_bp.route('/patient_update_consent', methods=['POST'])
def patient_update_consent():
    patient_id = patient_portal_model.get_current_patient_id()
    consent = request.json.get('consent', False)
    patient_model.update_patient_consent(patient_id, consent)
    return {"ok": True}