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
    const maidenNameGroup = $('maidenNameGroup');
    const patientIdInput = $('patientId');

    // ---------------------------------------------------------------
    // Sections toggle independently: opening one leaves the others as they
    // are, so a nurse can keep several open while filling out the form.
    // ---------------------------------------------------------------
    document.querySelectorAll('.card-header.section-toggle').forEach((header) => {
        header.addEventListener('click', () => {
            const body = header.nextElementSibling;
            if (!body || !body.classList.contains('card-body')) return;
            const nowCollapsed = header.classList.toggle('collapsed');
            body.classList.toggle('collapsed', nowCollapsed);
        });
    });

    function openSectionFor(input) {
        if (!input) return;
        const card = input.closest('.form-card');
        if (!card) return;
        const header = card.querySelector('.card-header.section-toggle');
        const body = card.querySelector('.card-body');
        if (!header || !body) return;
        // Only open the section holding the invalid field; leave the rest alone.
        header.classList.remove('collapsed');
        body.classList.remove('collapsed');
    }

    // ---------------------------------------------------------------
    // Region -> City -> Barangay cascade (offline PSGC dataset)
    //
    // CHANGED: the old psgcTree was keyed by NAME at every level
    // ({ "CALABARZON": { "Santa Rosa": [...] } }). That breaks the
    // moment two places share a name — e.g. there is a "Santa Rosa"
    // municipality in Nueva Ecija (Region III) AND a "City of Santa
    // Rosa" in Laguna (CALABARZON), each with a totally different
    // barangay list, and name-only lookups can resolve to the wrong
    // one. The dataset is now three flat arrays keyed by PSGC CODE
    // (regions / cities / barangays, each city carrying its
    // regionCode and each barangay its cityCode), so City and
    // Barangay selects store the code as their value and filter by
    // that code — never by name.
    // ---------------------------------------------------------------
    const regionSelect = $('region');
    const citySelect = $('city');
    const barangaySelect = $('barangay');
    const barangayManual = $('barangayManual');
    let psgcData = null; // { regions:[{code,name}], cities:[{code,name,regionCode}], barangays:[{code,name,cityCode}] }

    function fillSelect(select, items, placeholder) {
        // items: [{code, name}]
        select.innerHTML = '';
        const opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = placeholder;
        select.appendChild(opt0);
        items.forEach(({ code, name }) => {
            const opt = document.createElement('option');
            opt.value = code;
            opt.textContent = name;
            select.appendChild(opt);
        });
    }

    function populateCities(regionCode) {
        const cities = psgcData.cities
            .filter((c) => c.regionCode === regionCode)
            .sort((a, b) => a.name.localeCompare(b.name));
        fillSelect(citySelect, cities, cities.length ? 'Select City / Municipality' : 'No cities found');
        citySelect.disabled = cities.length === 0;
        fillSelect(barangaySelect, [], 'Select City first');
        barangaySelect.disabled = true;
        barangayManual.style.display = 'none';
    }

    function populateBarangays(cityCode) {
        const brgys = psgcData.barangays
            .filter((b) => b.cityCode === cityCode)
            .sort((a, b) => a.name.localeCompare(b.name));
        if (brgys.length) {
            fillSelect(barangaySelect, brgys, 'Select Barangay');
            barangaySelect.disabled = false;
            barangayManual.style.display = 'none';
            barangayManual.value = '';
        } else {
            // No barangay list available for this city — fall back to manual entry
            // (e.g. "City of Manila" itself has none; its districts like
            // "Tondo I/II" carry the barangays instead — that's normal PSGC
            // structure, not missing data)
            fillSelect(barangaySelect, [], 'Not available — type below');
            barangaySelect.disabled = true;
            barangayManual.style.display = 'block';
        }
    }

    regionSelect.addEventListener('change', () => {
        if (!psgcData) return;
        if (!regionSelect.value) {
            fillSelect(citySelect, [], 'Select Region first');
            citySelect.disabled = true;
            fillSelect(barangaySelect, [], 'Select City first');
            barangaySelect.disabled = true;
            barangayManual.style.display = 'none';
            return;
        }
        populateCities(regionSelect.value);
    });

    citySelect.addEventListener('change', () => {
        if (!psgcData || !regionSelect.value) return;
        if (!citySelect.value) {
            fillSelect(barangaySelect, [], 'Select City first');
            barangaySelect.disabled = true;
            barangayManual.style.display = 'none';
            return;
        }
        populateBarangays(citySelect.value);
    });

    if (window.__psgcUrl) {
        fetch(window.__psgcUrl)
            .then((res) => res.json())
            .then((data) => {
                psgcData = data;
                fillSelect(regionSelect, data.regions, 'Select Region');
                // No default region/city — the nurse always chooses explicitly.
            })
            .catch((err) => {
                console.error('Could not load region/city/barangay data:', err);
                regionSelect.innerHTML = '<option value="">Unavailable</option>';
                citySelect.innerHTML = '<option value="">Unavailable</option>';
                barangaySelect.disabled = true;
                barangayManual.style.display = 'block';
            });
    }

    function selectedOptionText(select) {
        const opt = select.options[select.selectedIndex];
        return opt ? opt.textContent : null;
    }

    function currentBarangay() {
        if (barangayManual.style.display !== 'none' && barangayManual.value.trim()) {
            return barangayManual.value.trim();
        }
        return barangaySelect.value ? selectedOptionText(barangaySelect) : null;
    }

    function currentBarangayCode() {
        if (barangayManual.style.display !== 'none' && barangayManual.value.trim()) {
            return null; // typed manually, no PSGC code to attach
        }
        return barangaySelect.value || null;
    }

    function currentCity() {
        return citySelect.value ? selectedOptionText(citySelect) : null;
    }

    function currentRegion() {
        return regionSelect.value ? selectedOptionText(regionSelect) : null;
    }

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

    function toggleMaidenName() {
        const civilStatusSelect = $('civilStatus');
        const isMarried = civilStatusSelect && civilStatusSelect.value === 'Married';
        maidenNameGroup.style.display = (sexSelect.value === 'Female' && isMarried) ? '' : 'none';
    }
    sexSelect.addEventListener('change', toggleMaidenName);
    $('civilStatus').addEventListener('change', toggleMaidenName);
    toggleMaidenName();

    // "None reported" is mutually exclusive with every real condition in its
    // group -- checking it clears the others, and checking any real condition
    // clears it, so the group can never end up as "None" + something else.
    function wireNoneExclusive(groupSelector, noneSelector) {
        const group = document.querySelectorAll(groupSelector);
        const none = document.querySelector(noneSelector);
        if (!none) return;
        none.addEventListener('change', () => {
            if (none.checked) group.forEach(cb => { if (cb !== none) cb.checked = false; });
        });
        group.forEach(cb => {
            if (cb === none) return;
            cb.addEventListener('change', () => { if (cb.checked) none.checked = false; });
        });
    }
    wireNoneExclusive('.pmh', '.pmh-none');
    wireNoneExclusive('.fh', '.fh-none');

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
            maiden_name: (sexSelect.value === 'Female') ? strOrNull('maidenName') : null,
            contact_number: strOrNull('contactNumber'),
            birthdate: strOrNull('birthdate'),
            sex: strOrNull('sex'),
            civil_status: strOrNull('civilStatus'),
            religion: strOrNull('religion'),
            occupation: strOrNull('occupation'),
            education: strOrNull('education'),
            region_name: currentRegion(),
            city_name: currentCity(),
            barangay_name: currentBarangay(),
            // NEW: PSGC codes, additive — the backend doesn't have to use these
            // yet, but they're the only unambiguous way to identify the exact
            // barangay once it isn't limited to Santa Rosa's 18 anymore (see
            // the barangay_id / barangays-table discussion).
            region_code: regionSelect.value || null,
            city_code: citySelect.value || null,
            barangay_code: currentBarangayCode(),
            address: strOrNull('address'),
            phic_membership: strOrNull('phicMembership'),
            phic_type: strOrNull('phicType'),
        };

        const visit = {
            assessment_date: strOrNull('dateAssessment'),
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
            pmh: checkedValues('.pmh').filter(v => v !== 'None'),
            family_history: checkedValues('.fh').filter(v => v !== 'None'),
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
        document.querySelectorAll('.radio-card-wrapper.group-error').forEach(g => {
            g.classList.remove('group-error');
            const msg = g.parentElement.querySelector('.group-error-text');
            if (msg) msg.remove();
        });
    }

    function markGroupError(groupEl, message, clearOnSelector) {
        groupEl.classList.add('group-error');
        let msg = groupEl.parentElement.querySelector('.group-error-text');
        if (!msg) {
            msg = document.createElement('span');
            msg.className = 'group-error-text';
            groupEl.insertAdjacentElement('afterend', msg);
        }
        msg.textContent = message;
        const clearOnce = () => {
            groupEl.classList.remove('group-error');
            if (msg) msg.remove();
            document.querySelectorAll(clearOnSelector).forEach(cb => cb.removeEventListener('change', clearOnce));
        };
        document.querySelectorAll(clearOnSelector).forEach(cb => cb.addEventListener('change', clearOnce));
    }

    function validate(patient, visit, { requireClinicalGroups } = {}) {
        clearAllFieldErrors();

        const requiredFields = [
            { input: $('lastName'),      value: patient.last_name,        message: 'Last name is required.' },
            { input: $('firstName'),     value: patient.first_name,       message: 'First name is required.' },
            { input: birthdateInput,     value: patient.birthdate,        message: 'Date of birth is required.' },
            { input: sexSelect,          value: patient.sex,              message: 'Sex is required.' },
            { input: $('dateAssessment'), value: visit.assessment_date,   message: 'Date of Assessment is required.' },
        ];

        let firstInvalid = null;
        requiredFields.forEach(({ input, value, message }) => {
            if (!value) {
                markFieldError(input, message);
                if (!firstInvalid) firstInvalid = input;
            }
        });

        if (requireClinicalGroups) {
            const groups = [
                { wrapper: $('pmhGroup'), selector: '.pmh', message: 'Select at least one, or check "None reported".' },
                { wrapper: $('fhGroup'),  selector: '.fh',  message: 'Select at least one, or check "None reported".' },
            ];
            groups.forEach(({ wrapper, selector, message }) => {
                if (!wrapper) return;
                const anyChecked = Array.from(document.querySelectorAll(selector)).some(cb => cb.checked);
                if (!anyChecked) {
                    markGroupError(wrapper, message, selector);
                    if (!firstInvalid) firstInvalid = wrapper;
                }
            });

            // Smoking is a radio group (no single input to attach an error
            // to), so it's checked the same way as PMH/Family History above.
            const smokeWrapper = document.querySelector('input[name="smoke"]')?.closest('.radio-card-wrapper');
            if (smokeWrapper && !document.querySelector('input[name="smoke"]:checked')) {
                markGroupError(smokeWrapper, 'Please select an option.', 'input[name="smoke"]');
                if (!firstInvalid) firstInvalid = smokeWrapper;
            }

            const vitalsFields = [
                { input: $('alcohol'),        value: visit.alcohol_intake,     message: 'Alcohol Intake is required.' },
                { input: $('illicitDrugs'),   value: visit.illicit_drug_use,   message: 'Illicit Drug Use is required.' },
                { input: $('bpSystolic'),     value: visit.bp_systolic,        message: 'Systolic BP is required.' },
                { input: $('bpDiastolic'),    value: visit.bp_diastolic,       message: 'Diastolic BP is required.' },
                { input: $('hr'),             value: visit.heart_rate,         message: 'Heart Rate is required.' },
                { input: $('rr'),             value: visit.respiratory_rate,   message: 'Respiratory Rate is required.' },
                { input: heightInput,         value: visit.height_cm,          message: 'Height is required.' },
                { input: weightInput,         value: visit.weight_kg,          message: 'Weight is required.' },
                { input: $('waist'),          value: visit.waist_cm,           message: 'Waist Circumference is required.' },
            ];
            vitalsFields.forEach(({ input, value, message }) => {
                if (!input) return;
                if (value === null || value === undefined || value === '') {
                    markFieldError(input, message);
                    if (!firstInvalid) firstInvalid = input;
                }
            });
        }

        if (firstInvalid) {
            openSectionFor(firstInvalid);
            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
            if (typeof firstInvalid.focus === 'function') firstInvalid.focus({ preventScroll: true });
        }

        return firstInvalid !== null; 
    }

    async function submitIntake(redirectAfter) {
    const status = redirectAfter ? 'submitted' : 'draft';
    const { patient, visit, conditions, cvd_responses } = buildPayload(status);

    const hasErrors = validate(patient, visit, { requireClinicalGroups: redirectAfter });
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
            await nurseAlert('Your session has expired. Please sign in again.');
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
            showDraftSavedDialog({
                message: `Draft saved. Patient ID: ${data.patient.patient_code}.`,
                onGo: () => { window.location.href = window.__dataManagementUrl || '/nurse_data_management'; },
                onStay: () => { resetIntakeForm(); },
            });
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

    // Draft saved as-is; the nurse is done with this patient for now -- clear
    // the form so the next patient starts from a blank slate instead of
    // inheriting the last one's data.
    function resetIntakeForm() {
        const form = $('intakeForm') || document.getElementById('intakeForm');
        if (form) form.reset();
        clearAllFieldErrors();
        patientIdInput.value = '';
        ageInput.value = '';
        bmiInput.value = '';
        bmiInput.dataset.raw = '';
        obesityInput.value = '';
        toggleObGyne();
        toggleMaidenName();
        // form.reset() puts the region/city/barangay selects back to their
        // first <option>, but doesn't re-run the cascade logic that disables
        // city/barangay and restores their placeholder text.
        fillSelect(citySelect, [], 'Select Region first');
        citySelect.disabled = true;
        fillSelect(barangaySelect, [], 'Select City first');
        barangaySelect.disabled = true;
        barangayManual.style.display = 'none';
        barangayManual.value = '';
        // Collapse every section back to the page's original opening state
        // (section 1 open, everything else closed).
        document.querySelectorAll('.card-header.section-toggle').forEach((h) => {
            const isFirst = h.dataset.section === '1';
            h.classList.toggle('collapsed', !isFirst);
            const b = h.nextElementSibling;
            if (b) b.classList.toggle('collapsed', !isFirst);
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

});

// ---------------------------------------------------------------------
// Shared "what next?" dialog after a draft save. Also used by
// nurse_new_record.js (continuing an existing patient's draft), which is
// why the preference is stored under one key both pages agree on.
function showDraftSavedDialog({ message, onGo, onStay }) {
    const PREF_KEY = 'nurseDraftGoToDataMgmt'; // '' = ask each time, 'always', 'never'
    const pref = localStorage.getItem(PREF_KEY) || '';
    if (pref === 'always') { onGo(); return; }
    if (pref === 'never') { onStay(); return; }

    const overlay = document.createElement('div');
    overlay.className = 'nurse-modal-overlay';
    overlay.innerHTML = `
        <div class="nurse-modal" role="dialog" aria-modal="true" aria-labelledby="draftModalTitle">
            <div class="nurse-dialog-head">
                <h3 id="draftModalTitle">What's next?</h3>
                <button type="button" class="nurse-dialog-x" id="draftModalClose" aria-label="Close">&times;</button>
            </div>
            <p>${message} Would you like to go to Data Management now, or stay here?</p>
            <label class="nurse-modal-remember"><input type="checkbox" id="draftModalRemember"> Don't ask me this again</label>
            <div class="nurse-modal-actions">
                <button type="button" class="btn btn-secondary" id="draftModalStay">Stay here</button>
                <button type="button" class="btn btn-primary" id="draftModalGo">Go to Data Management</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    function close(choice) {
        const remember = overlay.querySelector('#draftModalRemember').checked;
        if (remember) localStorage.setItem(PREF_KEY, choice === 'go' ? 'always' : 'never');
        overlay.remove();
        if (choice === 'go') onGo(); else onStay();
    }
    overlay.querySelector('#draftModalGo').addEventListener('click', () => close('go'));
    overlay.querySelector('#draftModalStay').addEventListener('click', () => close('stay'));
    overlay.querySelector('#draftModalClose').addEventListener('click', () => close('stay'));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close('stay'); });
    document.addEventListener('keydown', function escOnce(ev) {
        if (ev.key === 'Escape') { close('stay'); document.removeEventListener('keydown', escOnce); }
    });
}

// ---------------------------------------------------------------------
// Floating tooltips for .field-tooltip — appended to <body> and positioned
// with getBoundingClientRect() so they can never be clipped by a section's
// overflow:hidden (needed for the collapse animation) or by a low z-index
// stacking context. Replaces whatever CSS ::before/::after hover tooltip
// the base stylesheet defines for .field-tooltip (that one is disabled by
// the inline <style> injected alongside this script).
document.addEventListener('DOMContentLoaded', () => {
    let tipEl = null;

    function showTip(target) {
        const text = target.getAttribute('data-tip');
        if (!text) return;
        tipEl = document.createElement('div');
        tipEl.className = 'floating-field-tooltip';
        tipEl.textContent = text;
        document.body.appendChild(tipEl);

        const r = target.getBoundingClientRect();
        const tipW = tipEl.offsetWidth;
        const margin = 8;

        // Center under the "?" by default; clamp so it never runs off
        // either edge of the viewport.
        let left = r.left + r.width / 2 - tipW / 2;
        left = Math.max(margin, Math.min(left, window.innerWidth - tipW - margin));
        let top = r.bottom + 6;

        // If there isn't room below, flip above the target instead.
        if (top + tipEl.offsetHeight > window.innerHeight - margin) {
            top = r.top - tipEl.offsetHeight - 6;
        }

        tipEl.style.left = left + 'px';
        tipEl.style.top = top + 'px';
        // Point the arrow at the "?" even after clamping.
        const arrowLeft = Math.max(10, Math.min(r.left + r.width / 2 - left, tipW - 10));
        tipEl.style.setProperty('--arrow-left', arrowLeft + 'px');
        requestAnimationFrame(() => tipEl && tipEl.classList.add('visible'));
    }

    function hideTip() {
        if (tipEl) { tipEl.remove(); tipEl = null; }
    }

    document.addEventListener('mouseover', (e) => {
        const target = e.target.closest('.field-tooltip');
        if (target) showTip(target);
    });
    document.addEventListener('mouseout', (e) => {
        const target = e.target.closest('.field-tooltip');
        if (target) hideTip();
    });
    document.addEventListener('focusin', (e) => {
        const target = e.target.closest('.field-tooltip');
        if (target) showTip(target);
    });
    document.addEventListener('focusout', (e) => {
        const target = e.target.closest('.field-tooltip');
        if (target) hideTip();
    });
    // Any scroll/resize can move the anchor out from under a fixed tooltip.
    window.addEventListener('scroll', hideTip, true);
    window.addEventListener('resize', hideTip);
});