/**
 * Nurse Patient Intake — client-side logic
 */
document.addEventListener('DOMContentLoaded', () => {
    const $ = (id) => document.getElementById(id);

    const birthdateInput = $('birthdate');
    const ageInput = $('age');
    const sexSelect = $('sex');
    const heightInput = $('height');
    const weightInput = $('weight');
    const bmiInput = $('bmi');
    const obesityInput = $('obesityClass');
    const obGyneCard = $('obGyneCard');
    const patientIdInput = $('patientId');

    function calcAge() {
        if (!birthdateInput.value) { ageInput.value = ''; return; }
        const bd = new Date(birthdateInput.value);
        const today = new Date();
        let age = today.getFullYear() - bd.getFullYear();
        const m = today.getMonth() - bd.getMonth();
        if (m < 0 || (m === 0 && today.getDate() < bd.getDate())) age--;
        ageInput.value = age >= 0 ? age : '';
    }
    birthdateInput.addEventListener('change', calcAge);

    function calcBmi() {
        const h = parseFloat(heightInput.value);
        const w = parseFloat(weightInput.value);
        if (!h || !w) {
            bmiInput.value = '';
            bmiInput.dataset.raw = '';
            obesityInput.value = '';
            return;
        }
        const bmi = w / Math.pow(h / 100, 2);
        bmiInput.value = bmi.toFixed(1) + ' kg/m²';
        bmiInput.dataset.raw = bmi.toFixed(1);

        let cls = 'Obese Class II';
        if (bmi < 18.5) cls = 'Underweight';
        else if (bmi < 23) cls = 'Normal';
        else if (bmi < 25) cls = 'Overweight';
        else if (bmi < 30) cls = 'Obese Class I';
        obesityInput.value = cls;
    }
    heightInput.addEventListener('input', calcBmi);
    weightInput.addEventListener('input', calcBmi);

    function toggleObGyne() {
        obGyneCard.style.display = (sexSelect.value === 'Female') ? '' : 'none';
    }
    sexSelect.addEventListener('change', toggleObGyne);
    toggleObGyne();

    // helpers ito
    function checkedValues(selector) {
        return Array.from(document.querySelectorAll(selector + ':checked')).map(el => el.value);
    }

    function strOrNull(id) {
        const v = $(id).value.trim();
        return v === '' ? null : v;
    }

    function numOrNull(id) {
        const v = $(id).value;
        return v === '' ? null : Number(v);
    }

    // toh yung sa cvd
    function cvdAnswers() {
        const selects = document.querySelectorAll('.cvd-q');
        const keys = [
            'q1_chest_discomfort', 'q2_pain_center_left_arm',
            'q3_occurs_uphill_hurrying', 'q4_slows_down_if_occurs',
            'q5_relieved_by_rest_tablet', 'q6_relieved_under_10min',
            'q7_severe_pain_30min_plus', 'q8_tia_stroke_symptoms',
        ];
        const answers = {};
        selects.forEach((sel, i) => {
            answers[keys[i]] = sel.value.startsWith('Yes');
        });
        return answers;
    }

    function buildPayload(status) {
        const patient = {
            last_name: strOrNull('lastName'),
            first_name: strOrNull('firstName'),
            middle_name: strOrNull('middleName'),
            father_last_name: strOrNull('fatherLastName'),
            father_first_name: strOrNull('fatherFirstName'),
            mother_last_name: strOrNull('motherLastName'),
            mother_first_name: strOrNull('motherFirstName'),
            spouse_last_name: strOrNull('spouseLastName'),
            spouse_first_name: strOrNull('spouseFirstName'),
            contact_number: strOrNull('contactNumber'),
            birthdate: strOrNull('birthdate'),
            sex: strOrNull('sex'),
            civil_status: strOrNull('civilStatus'),
            religion: strOrNull('religion'),
            occupation: strOrNull('occupation'),
            education: strOrNull('education'),
            barangay_name: strOrNull('barangay'),
            address: strOrNull('address'),
            phic_membership: strOrNull('phicMembership'),
            phic_type: strOrNull('phicType'),
        };

        const visit = {
            assessment_date: strOrNull('dateAssessment') || new Date().toISOString().slice(0, 10),
            smoking_status: (document.querySelector('input[name="smoke"]:checked') || {}).value || null,
            alcohol_intake: strOrNull('alcohol'),
            illicit_drug_use: strOrNull('illicitDrugs'),
            physical_activity: strOrNull('physicalActivity'),
            past_surgical_history: strOrNull('pastSurgical'),
            diabetes_diagnosis: strOrNull('diabetesDiagnosis'),
            bp_systolic: numOrNull('bpSystolic'),
            bp_diastolic: numOrNull('bpDiastolic'),
            heart_rate: numOrNull('hr'),
            respiratory_rate: numOrNull('rr'),
            height_cm: numOrNull('height'),
            weight_kg: numOrNull('weight'),
            waist_cm: numOrNull('waist'),
            bmi: bmiInput.dataset.raw ? Number(bmiInput.dataset.raw) : null,
            obesity_class: strOrNull('obesityClass'),
            pe_skin: strOrNull('peSkin'),
            pe_heent: strOrNull('peHeent'),
            pe_chest: strOrNull('peChest'),
            pe_heart: strOrNull('peHeart'),
            pe_abdomen: strOrNull('peAbdomen'),
            pe_extremities: strOrNull('peExtremities'),
            menarche_age: numOrNull('menarcheAge'),
            lmp_date: strOrNull('lmp'),
            gravida: numOrNull('gravida'),
            para: numOrNull('para'),
            clinical_notes: null,
            status: status, 
        };

        const conditions = {
            pmh: checkedValues('.pmh'),
            family_history: checkedValues('.fh'),
            diet: checkedValues('.diet'),
            immunization: checkedValues('.immu'),
            dm_symptom: checkedValues('.dm-sym'),
        };

        const cvd_responses = cvdAnswers();

        return { patient, visit, conditions, cvd_responses };
    }

    function clearFieldError(input) {
        input.classList.remove('field-error');
        const msg = input.parentElement.querySelector('.field-error-text');
        if (msg) msg.remove();
    }

    function markFieldError(input, message) {
        input.classList.add('field-error');
        let msg = input.parentElement.querySelector('.field-error-text');
        if (!msg) {
            msg = document.createElement('span');
            msg.className = 'field-error-text';
            input.insertAdjacentElement('afterend', msg);
        }
        msg.textContent = message;
        const clearOnce = () => { clearFieldError(input); input.removeEventListener('input', clearOnce); input.removeEventListener('change', clearOnce); };
        input.addEventListener('input', clearOnce);
        input.addEventListener('change', clearOnce);
    }

    function clearAllFieldErrors() {
        document.querySelectorAll('.field-input.field-error').forEach(clearFieldError);
    }

    function validate(patient, visit) {
        clearAllFieldErrors();

        const requiredFields = [
            { input: $('lastName'),  value: patient.last_name,  message: 'Last name is required.' },
            { input: $('firstName'), value: patient.first_name, message: 'First name is required.' },
            { input: birthdateInput, value: patient.birthdate,  message: 'Date of birth is required.' },
            { input: sexSelect,      value: patient.sex,        message: 'Sex is required.' },
        ];

        let firstInvalid = null;
        requiredFields.forEach(({ input, value, message }) => {
            if (!value) {
                markFieldError(input, message);
                if (!firstInvalid) firstInvalid = input;
            }
        });

        if (firstInvalid) {
            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
            firstInvalid.focus({ preventScroll: true });
        }

        return firstInvalid !== null; 
    }

    async function submitIntake(redirectAfter) {
    const status = redirectAfter ? 'submitted' : 'draft';
    const { patient, visit, conditions, cvd_responses } = buildPayload(status);

    const hasErrors = validate(patient, visit);
    if (hasErrors) return;

    const submitBtn = $('submitIntakeBtn');
    const draftBtn = $('saveDraftBtn');
    submitBtn.disabled = true;
    draftBtn.disabled = true;

    try {
        const res = await fetch('/api/patients', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ patient, visit, conditions, cvd_responses }),
        });

        if (res.status === 401) {
            alert('Your session has expired. Please sign in again.');
            window.location.href = '/login';
            return;
        }

        const data = await res.json();
        if (!res.ok) {
            alert(data.error || 'Could not save patient intake.');
            return;
        }

        patientIdInput.value = data.patient.patient_code;
        if (redirectAfter) {
            window.location.href = `/nurse_screening/${data.patient.patient_code}`;
        } else {
            alert('Draft saved. Patient ID: ' + data.patient.patient_code);
        }
    } catch (err) {
        console.error(err);
        alert('Network error while saving intake. Please try again.');
    } finally {
        submitBtn.disabled = false;
        draftBtn.disabled = false;
    }
}  

$('submitIntakeBtn').addEventListener('click', () => submitIntake(true));
$('saveDraftBtn').addEventListener('click', () => submitIntake(false));

}); 