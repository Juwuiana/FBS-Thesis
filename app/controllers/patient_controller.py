from flask import Blueprint, current_app, render_template, request
from app.models import patient_portal_model, patient_model

patient_bp = Blueprint('patient', __name__)


# SECURITY NOTE: there is no patient login yet -- patients are not in the `users` table and
# have no credential of any kind (see docs/NURSE_BRANCH_INTEGRATION.md and
# patient_portal_model.get_current_patient_id, which is the single place this will be wired
# up once a real patient-auth design exists). Until then this blueprint fails CLOSED: every
# route below 404s in any normal deployment. The only way to view it is the explicit,
# clearly-named local opt-in FBS_DEV_NO_AUTH=1 (never set outside your own dev machine).
@patient_bp.before_request
def _block_until_patient_auth_exists():
    if not current_app.config.get("DEV_NO_AUTH"):
        from flask import abort
        abort(404)


@patient_bp.app_context_processor
def inject_current_patient():
    try:
        patient_id = patient_portal_model.get_current_patient_id()
        return {"patient": patient_model.get_patient_by_id(patient_id)}
    except NotImplementedError:
        return {"patient": None}


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

    if request.method == 'GET':
        return render_template('patient/patient_settings.html', patient=patient)

    # TODO(auth): password change belongs to the auth branch
    return render_template('patient/patient_settings.html', patient=patient,
                            message="Password changes aren't available yet.", success=False)
