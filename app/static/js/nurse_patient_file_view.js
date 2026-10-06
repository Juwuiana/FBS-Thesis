// app/static/js/nurse_patient_file_view.js
// Logic for the "Patient Record" edit form (Data Management > View patient).
// Requires window.__psgcUrl to be set by an inline <script> in the template
// (Jinja needs to render that one URL; everything else here is static).

(function () {
    const editBtn = document.getElementById('editRecordBtn');
    const saveBtn = document.getElementById('saveRecordBtn');
    const cancelBtn = document.getElementById('cancelEditBtn');
    const subtitle = document.getElementById('pageSubtitle');

    // Section dropdowns: each header toggles only itself. Bound before the
    // early return below so Portal Access / Past Records still open and close
    // for a patient who has no visit yet (and therefore no edit form).
    document.querySelectorAll('.section-toggle').forEach(header => {
        header.addEventListener('click', () => {
            const body = header.nextElementSibling;
            if (!body || !body.classList.contains('card-body')) return;
            const nowCollapsed = header.classList.toggle('collapsed');
            body.classList.toggle('collapsed', nowCollapsed);
        });
    });

    // --- Patient Portal Access: account-help request ---------------------
    // Also bound before the early return below: a patient with no visit yet
    // still has this card, and may be the one who asked for account help.
    const portalCard = document.getElementById('portalAccessCard');
    if (portalCard && window.location.hash === '#portalAccessCard') {
        // Arrived from the notification bell: open the card and scroll to it.
        const portalHeader = portalCard.querySelector('.section-toggle');
        if (portalHeader) {
            portalHeader.classList.remove('collapsed');
            if (portalHeader.nextElementSibling) portalHeader.nextElementSibling.classList.remove('collapsed');
        }
        portalCard.scrollIntoView({ block: 'start' });
    }

    // Dismiss a request without reissuing credentials (e.g. a duplicate).
    // Reissuing credentials resolves the request on its own.
    const dismissHelpBtn = document.getElementById('dismissAccountHelpBtn');
    if (dismissHelpBtn) {
        dismissHelpBtn.addEventListener('click', async () => {
            dismissHelpBtn.disabled = true;
            try {
                const res = await fetch(dismissHelpBtn.dataset.url, { method: 'POST' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                window.location.reload();
            } catch (err) {
                console.error(err);
                dismissHelpBtn.disabled = false;
                if (typeof nurseAlert === 'function') nurseAlert('Could not dismiss the request. Please try again.');
            }
        });
    }

    if (!editBtn) return; // no latest_visit -> nothing to edit

    const form = document.getElementById('recordForm');
    const isDraft = form.dataset.isDraft === 'true';
    const editUrl = form.dataset.editUrl;
    const editableFields = document.querySelectorAll('.editable-field');

    function setEditing(on) {
        editingNow = on;
        editableFields.forEach(el => { el.disabled = !on; });
        editBtn.style.display = on ? 'none' : '';
        saveBtn.style.display = on ? '' : 'none';
        cancelBtn.style.display = on ? '' : 'none';
        subtitle.textContent = on
            ? "Editing this visit's record — test results are not editable here."
            : "Read-only view of the patient's assessment record";
        toggleMaidenName();
    }

    editBtn.addEventListener('click', () => setEditing(true));
    cancelBtn.addEventListener('click', () => window.location.reload());

    // Maiden Last Name only makes sense for a married female patient --
    // reactive so it appears/disappears immediately if the nurse changes
    // Sex or Civil Status while editing, not just on next page load.
    // Same condition also unlocks the actual Last Name field itself (a
    // married woman's surname can legitimately change), on top of the
    // draft-only unlock every other name field gets.
    const fvSex = document.getElementById('fv_sex');
    const fvCivilStatus = document.getElementById('fv_civilStatus');
    const fvMaidenNameGroup = document.getElementById('fv_maidenNameGroup');
    const fvLastName = document.getElementById('fv_lastName');
    let editingNow = false;

    function isMarriedFemale() {
        return !!fvSex && !!fvCivilStatus && fvSex.value === 'Female' && fvCivilStatus.value === 'Married';
    }

    function toggleMaidenName() {
        if (fvMaidenNameGroup) fvMaidenNameGroup.style.display = isMarriedFemale() ? '' : 'none';
        if (fvLastName) fvLastName.disabled = !(editingNow && (isDraft || isMarriedFemale()));
    }
    if (fvSex) fvSex.addEventListener('change', toggleMaidenName);
    if (fvCivilStatus) fvCivilStatus.addEventListener('change', toggleMaidenName);

    // A draft hasn't been finalized yet, so open it straight into edit mode
    // (same layout as nurse_intake: all sections still start collapsed --
    // the user clicks a section header to expand it, just like intake).
    if (isDraft) {
        setEditing(true);
    }

    // Draft "continue" link from Data Management drops straight into edit mode.
    if (new URLSearchParams(window.location.search).get('edit') === '1') {
        setEditing(true);
    }

    // --- Region / City / Barangay cascade -------------------------------
    const regionSel = document.getElementById('fv_region');
    const citySel = document.getElementById('fv_city');
    const brgySel = document.getElementById('fv_barangay');
    const brgyManual = document.getElementById('fv_barangayManual');
    let psgcData = null;

    function fillCities(regionCode, preselectCity) {
        citySel.innerHTML = '<option value="">Select City</option>';
        const cities = (psgcData ? psgcData.cities : []).filter(c => c.regionCode === regionCode);
        cities.forEach(c => citySel.add(new Option(c.name, c.code)));
        // Enabled/disabled state tracks every .editable-field uniformly via
        // setEditing() above -- this function only ever repopulates options.
        if (preselectCity) citySel.value = preselectCity;
    }

    function fillBarangays(regionCode, cityCode, preselectBrgy) {
        brgySel.innerHTML = '<option value="">Select Barangay</option>';
        const list = (psgcData ? psgcData.barangays : []).filter(b => b.cityCode === cityCode);
        list.forEach(b => brgySel.add(new Option(b.name, b.code)));
        brgyManual.style.display = (cityCode && list.length === 0) ? '' : 'none';
        if (preselectBrgy) brgySel.value = preselectBrgy;
    }

    fetch(window.__psgcUrl).then(r => r.json()).then(data => {
        psgcData = data;
        const curRegion = form.dataset.currentRegion;
        const curCity = form.dataset.currentCity;
        const curBrgy = form.dataset.currentBarangay;

        data.regions.forEach(r => regionSel.add(new Option(r.name, r.code)));
        if (curRegion) {
            regionSel.value = curRegion;
            fillCities(curRegion, curCity);
        }
        if (curRegion && curCity) fillBarangays(curRegion, curCity, curBrgy);

        regionSel.addEventListener('change', () => fillCities(regionSel.value));
        citySel.addEventListener('change', () => fillBarangays(regionSel.value, citySel.value));
    }).catch(err => console.error('Could not load PSGC data', err));

    // Email is optional, but if one is typed it has to look like an email.
    // Flags the field inline, opens its section if collapsed, and scrolls to it
    // once the section has finished expanding. Returns true when valid.
    const emailInput = document.querySelector('[data-field="patient.email"]');
    const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    function clearEmailError() {
        if (!emailInput) return;
        emailInput.classList.remove('field-error');
        const m = emailInput.parentElement.querySelector('.field-error-text');
        if (m) m.remove();
    }
    if (emailInput) emailInput.addEventListener('input', clearEmailError);

    function validateEmail(reveal = true) {
        clearEmailError();
        if (!emailInput) return true;
        const v = emailInput.value.trim();
        if (!v || EMAIL_RE.test(v)) return true;

        emailInput.classList.add('field-error');
        const msg = document.createElement('span');
        msg.className = 'field-error-text';
        msg.textContent = 'Enter a valid email address (e.g. name@example.com).';
        emailInput.insertAdjacentElement('afterend', msg);

        if (!reveal) return false; // live check on blur: just flag it, don't move the page

        const body = emailInput.closest('.card-body');
        const header = body && body.previousElementSibling;
        const wasCollapsed = !!(body && body.classList.contains('collapsed'));
        if (wasCollapsed) {
            body.classList.remove('collapsed');
            if (header) header.classList.remove('collapsed');
        }
        setTimeout(() => {
            emailInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
            emailInput.focus({ preventScroll: true });
        }, wasCollapsed ? 350 : 0);
        return false;
    }

    // Live check as soon as the nurse leaves the field (only while editing).
    if (emailInput) emailInput.addEventListener('blur', () => { if (!emailInput.disabled) validateEmail(false); });

    saveBtn.addEventListener('click', async () => {
        if (!validateEmail()) return;
        const payload = { patient: {}, visit: {}, conditions: {}, cvd_responses: {} };

        editableFields.forEach(el => {
            const field = el.dataset.field;
            if (!field) return;
            const [scope, key] = field.split('.');
            let value = el.value.trim();
            // assessment_date and birthdate are required (NOT NULL) columns --
            // never submit them as a blank/null, which would fail the save.
            // A blank here means the field wasn't touched (or its stored
            // value didn't parse into the date input), not a deliberate clear.
            if (value === '' && (field === 'visit.assessment_date' || field === 'patient.birthdate')) {
                return;
            }
            if (value === '') value = null;
            else if (field === 'patient.email') value = value.toLowerCase();
            else if (el.type === 'number' && value !== null) value = Number(value);
            payload[scope][key] = value;
        });

        // Region/City/Barangay: send PSGC codes (authoritative) plus their
        // display names, exactly like nurse_intake.js does, so the backend
        // resolves the barangay the same way for both pages. Guard against
        // sending a select's placeholder label ("Select City", etc.) as if
        // it were a real name -- only send a name when a real option (with
        // a non-empty value) is actually selected.
        if (regionSel) {
            payload.patient.region_code = regionSel.value || null;
            payload.patient.region_name = regionSel.value ? (regionSel.options[regionSel.selectedIndex]?.text || null) : null;
            payload.patient.city_code = citySel.value || null;
            payload.patient.city_name = citySel.value ? (citySel.options[citySel.selectedIndex]?.text || null) : null;

            if (brgyManual.style.display !== 'none' && brgyManual.value.trim()) {
                payload.patient.barangay_code = null;
                payload.patient.barangay_name = brgyManual.value.trim();
            } else if (brgySel.value) {
                payload.patient.barangay_code = brgySel.value;
                payload.patient.barangay_name = brgySel.options[brgySel.selectedIndex]?.text || null;
            } else {
                payload.patient.barangay_code = null;
                payload.patient.barangay_name = null;
            }
        }

        ['pmh', 'family_history', 'diet', 'immunization', 'dm_symptom'].forEach(cat => {
            payload.conditions[cat] = Array.from(
                document.querySelectorAll('.cond-' + cat + ':checked')
            ).map(el => el.value);
        });

        document.querySelectorAll('.cvd-field').forEach(sel => {
            payload.cvd_responses[sel.dataset.cvd] = sel.value === '1';
        });

        const markSubmittedCheck = document.getElementById('markSubmittedCheck');
        if (markSubmittedCheck && markSubmittedCheck.checked) {
            payload.visit.status = 'submitted';
        }

        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving…';
        try {
            const res = await fetch(editUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || 'Save failed');
            }
            // Preserve return_qs (Data Management's filters/page) through
            // the reload -- window.location.search would also work, but
            // this stays correct even if other one-off params like ?edit=1
            // were on the URL and shouldn't survive the reload.
            const returnQs = form.dataset.returnQs;
            window.location.href = window.location.pathname + (returnQs ? '?return_qs=' + encodeURIComponent(returnQs) : '');
        } catch (err) {
            console.error(err);
            alert(err.message && err.message !== 'Save failed' ? err.message : 'Could not save changes. Please try again.');
            saveBtn.disabled = false;
            saveBtn.textContent = '💾 Save Changes';
        }
    });
})();