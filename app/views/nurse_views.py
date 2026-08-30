from flask import Blueprint, render_template, request, jsonify
import hashlib
import uuid
from datetime import datetime

nurse_bp = Blueprint('nurse', __name__)

BARANGAYS = ["Aplaya", "Balibago", "Caingin", "Dila", "Dita", "Don Jose",
             "Ibaba", "Kanluran (Poblacion Uno)", "Labas", "Macabling",
             "Malitlit", "Malusak (Poblacion Dos)", "Market Area (Poblacion Tres)",
             "Pooc (Pook)", "Pulong Santa Cruz", "Santo Domingo", "Sinalhan", "Tagapo"]

# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# Single shared mock patient record used by nurse_patient_file_view and
# nurse_new_record, so both demo pages agree on the same values instead of
# drifting apart. There is no Patient model / DB on this branch — every
# route below accepts `patient_id` but returns this same mock record
# regardless of the ID passed in. When the real Patient model lands,
# replace MOCK_PATIENT with an actual query by patient_id
# (e.g. Patient.query.filter_by(patient_code=patient_id).first_or_404())
# and delete this block.
MOCK_PATIENT = {
    "patient_id": "CAB-2025-0156",
    "last_name": "Dela Cruz",
    "first_name": "Juan",
    "middle_name": "Santos",
    "father_last_name": "Dela Cruz",
    "father_first_name": "Pedro",
    "mother_last_name": "Santos",
    "mother_first_name": "Maria",
    "spouse_last_name": "Dela Cruz",
    "spouse_first_name": "Ana",
    "contact_number": "0917 123 4567",
    "birthdate": "1995-03-12",
    "birthdate_display": "Mar 12, 1995",
    "age": 30,
    "sex": "Male",
    "civil_status": "Married",
    "religion": "Roman Catholic",
    "occupation": "Tricycle Driver",
    "education": "High School",
    "barangay": "Poblacion",
    "address": "123 Rizal St., Barangay Poblacion, Santa Rosa City",
    "phic_membership": "Member",
    "phic_type": "Employed - Private",
}

# Mock screening visit history for the same mock patient, most recent first.
# Shared by nurse_patient_file_view (and can be reused by nurse_screening
# later) so the numbers don't drift apart across templates.
MOCK_SCREENING_HISTORY = [
    {"date": "May 27, 2025", "fbs": "142 mg/dL", "risk": "High"},
    {"date": "Jan 15, 2025", "fbs": "118 mg/dL", "risk": "Moderate"},
    {"date": "Aug 20, 2024", "fbs": "105 mg/dL", "risk": "Pre-diab."},
    {"date": "Feb 10, 2024", "fbs": "92 mg/dL", "risk": "Low"},
]
# ── END TEMPORARY STUB ───────────────────────────────────────────────────


@nurse_bp.route('/nurse_dashboard')
def nurse_dashboard():
    low = 77.1
    mod = 17.0
    high = 5.9
    return render_template('nurse/nurse_dashboard.html', risk_data=[low, mod, high])


@nurse_bp.route('/nurse_intake')
def nurse_intake():
    return render_template('nurse/nurse_intake.html', barangays=BARANGAYS)


# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# This does NOT persist to a database. It only exists so the intake form's
# "Save Intake & Proceed to Lab Screening" button works end-to-end on this
# branch. feature/intake-patient owns the real Patient model + DB save —
# when merging, DELETE this stub and let that branch's version take over.
@nurse_bp.route('/api/patients', methods=['POST'])
def create_patient_stub():
    payload = request.get_json(silent=True) or {}

    required = ("last_name", "first_name", "birthdate", "sex")
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    # Fake, non-persistent patient_code just so the UI has something to show.
    raw = f"{payload.get('last_name')}|{payload.get('first_name')}|{datetime.utcnow().isoformat()}|{uuid.uuid4().hex}"
    fake_code = "PT-" + hashlib.sha256(raw.encode()).hexdigest()[:10].upper()

    return jsonify({
        "message": "Patient intake received (stub — not saved to DB on this branch)",
        "patient": {**payload, "patient_code": fake_code},
    }), 201
# ── END TEMPORARY STUB ───────────────────────────────────────────────────


@nurse_bp.route('/nurse_screening')
def nurse_screening():
    return render_template('nurse/nurse_screening.html')


# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# Static demo data only — see MOCK_PATIENT above. `patient_id` is accepted
# but not actually looked up. This renders a read-only view of the mock
# record so the "View" button in Data Management has somewhere to go.
@nurse_bp.route('/nurse_patient_file_view/<patient_id>')
def nurse_patient_file_view(patient_id):
    return render_template(
        'nurse/nurse_patient_file_view.html',
        patient_id=patient_id,
        patient=MOCK_PATIENT,
        records=MOCK_SCREENING_HISTORY,
    )
# ── END TEMPORARY STUB ───────────────────────────────────────────────────


# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# Static demo data only — see MOCK_PATIENT above. Renders the intake-style
# form pre-filled with the existing patient's repeatable demographic info
# (name, parents, spouse, birthday, address, PHIC, etc.) so a returning
# patient's new screening visit doesn't require retyping it. Vitals, the
# CVD questionnaire, lifestyle factors, and diabetes history are left blank
# since those get reassessed at every visit.
#
# The submit button on this page currently posts to the same /api/patients
# stub above (it creates a "new patient" record, not a new screening record
# tied to an existing one). When the real backend lands, this should post
# to something like POST /api/patients/<patient_id>/records instead, so a
# returning patient's visits accumulate under the same patient rather than
# creating duplicate patient rows.
@nurse_bp.route('/nurse_new_record/<patient_id>')
def nurse_new_record(patient_id):
    return render_template('nurse/nurse_new_record.html', patient_id=patient_id, patient=MOCK_PATIENT, barangays=BARANGAYS)
# ── END TEMPORARY STUB ───────────────────────────────────────────────────


@nurse_bp.route('/nurse_health_results')
def nurse_health_results():
    return render_template('nurse/nurse_health_results.html')


@nurse_bp.route('/nurse_data_management')
def nurse_data_management():
    return render_template('nurse/nurse_data_management.html', barangays=BARANGAYS)


@nurse_bp.route('/nurse_privacy_security')
def nurse_privacy_security():
    return render_template('nurse/nurse_privacy_security.html')
