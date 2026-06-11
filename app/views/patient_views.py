from flask import Blueprint, render_template

patient_bp = Blueprint('patient', __name__)

@patient_bp.route('/patient_dashboard')
def patient_dashboard():
    result_data = {
        'risk_level': 'Moderate Risk',
        'fbs_score': 124,
        'recommendation_type': 'diet_and_exercise'
    }
    return render_template('patient/patient_dashboard.html', result=result_data)

@patient_bp.route('/patient_health_results')
def patient_health_results():
    result_data = {
        'risk_level': 'Moderate Risk',
        'fbs_score': 124,
        'recommendation_type': 'diet_and_exercise'
    }
    return render_template('patient/patient_health_results.html', result=result_data)

@patient_bp.route('/patient_settings')
def patient_settings():
    return render_template('patient/patient_settings.html')