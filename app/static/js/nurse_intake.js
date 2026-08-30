/**
 * Nurse Patient Intake — client-side logic.
 * Fields are kept atomic (split first/last names, split systolic/diastolic BP)
 * so the saved data maps cleanly to individual CSV/database columns instead
 * of needing to be re-parsed out of combined strings later.
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

    // ---- Age auto-calculation ----
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

    // ---- BMI auto-calculation ----
    function calcBmi() {
        const h = parseFloat(heightInput.value);
        const w = parseFloat(weightInput.value);
        if (!h || !w) { bmiInput.value = ''; obesityInput.value = ''; return; }
        const bmi = w / Math.pow(h / 100, 2);
        bmiInput.value = bmi.toFixed(1) + ' kg/m²';
        let cls = 'Obese Class II';
        if (bmi < 18.5) cls = 'Underweight';
        else if (bmi < 23) cls = 'Normal';
        else if (bmi < 25) cls = 'Overweight';
        else if (bmi < 30) cls = 'Obese Class I';
        obesityInput.value = cls;
    }
    heightInput.addEventListener('input', calcBmi);
    weightInput.addEventListener('input', calcBmi);

    // ---- Show/hide OB-Gyne section based on sex ----
    function toggleObGyne() {
        obGyneCard.style.display = (sexSelect.value === 'Female') ? '' : 'none';
    }
    sexSelect.addEventListener('change', toggleObGyne);
    toggleObGyne();

    // ---- Collect checkbox-group values ----
    function checkedValues(selector) {
        return Array.from(document.querySelectorAll(selector + ':checked')).map(el => el.value);
    }

    function buildPayload() {
        return {
            last_name: $('lastName').value.trim(),
            first_name: $('firstName').value.trim(),
            middle_name: $('middleName').value.trim(),

            // Split name fields -> clean, independent CSV/DB columns
            father_first_name: $('fatherFirstName').value.trim(),
            father_last_name: $('fatherLastName').value.trim(),
            mother_first_name: $('motherFirstName').value.trim(),
            mother_last_name: $('motherLastName').value.trim(),
            spouse_first_name: $('spouseFirstName').value.trim(),
            spouse_last_name: $('spouseLastName').value.trim(),

            date_of_assessment: $('dateAssessment').value,
            birthdate: birthdateInput.value,
            sex: sexSelect.value,
            civil_status: $('civilStatus').value,
            religion: $('religion').value.trim(),
            contact_number: $('contactNumber').value.trim(),
            address: $('address').value.trim(),
            barangay: $('barangay').value,
            occupation: $('occupation').value.trim(),
            educational_attainment: $('education').value,

            phic_membership: $('phicMembership').value,
            phic_type: $('phicType').value,

            past_medical_history: checkedValues('.pmh'),
            past_surgical_history: $('pastSurgical').value.trim(),
            family_history: checkedValues('.fh'),

            smoking_status: (document.querySelector('input[name="smoke"]:checked') || {}).value || '',
            alcohol_intake: $('alcohol').value,
            illicit_drugs: $('illicitDrugs').value,
            physical_activity: $('physicalActivity').value,
            dietary_factors: checkedValues('.diet'),

            cvd_answers: Array.from(document.querySelectorAll('.cvd-q')).map(el => el.value),

            diabetes_diagnosis: $('diabetesDiagnosis').value,
            diabetes_symptoms: checkedValues('.dm-sym'),

            immunizations: checkedValues('.immu'),

            menarche_age: $('menarcheAge').value,
            lmp: $('lmp').value,
            gravida: $('gravida').value,
            para: $('para').value,

            pe_findings: {
                skin: $('peSkin').value.trim(),
                heent: $('peHeent').value.trim(),
                chest: $('peChest').value.trim(),
                heart: $('peHeart').value.trim(),
                abdomen: $('peAbdomen').value.trim(),
                extremities: $('peExtremities').value.trim(),
            },

            // Split BP -> two numeric columns instead of one "120/80" string
            bp_systolic: $('bpSystolic').value || null,
            bp_diastolic: $('bpDiastolic').value || null,
            heart_rate: $('hr').value.trim(),
            respiratory_rate: $('rr').value.trim(),
            height_cm: heightInput.value || null,
            weight_kg: weightInput.value || null,
            waist_cm: $('waist').value || null,
        };
    }

    function validate(payload) {
        const errors = [];
        if (!payload.last_name) errors.push('Last name is required.');
        if (!payload.first_name) errors.push('First name is required.');
        if (!payload.birthdate) errors.push('Date of birth is required.');
        if (!payload.sex) errors.push('Sex is required.');
        return errors;
    }

    async function submitIntake(redirectAfter) {
        const payload = buildPayload();
        const errors = validate(payload);
        if (errors.length) {
            alert(errors.join('\n'));
            return;
        }

        try {
            const res = await fetch('/api/patients', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
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
                window.location.href = '/nurse_screening';
            } else {
                alert('Draft saved. Patient ID: ' + data.patient.patient_code);
            }
        } catch (err) {
            console.error(err);
            alert('Network error while saving intake. Please try again.');
        }
    }

    $('submitIntakeBtn').addEventListener('click', () => submitIntake(true));
    $('saveDraftBtn').addEventListener('click', () => submitIntake(false));
});
