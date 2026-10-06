document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("intakeForm");
    const patientId = form.dataset.patientId;

    // ---------------------------------------------------------------
    // Accordion — one section open at a time (same behavior as Nurse Intake)
    // ---------------------------------------------------------------
    document.querySelectorAll(".card-header.section-toggle").forEach((header) => {
        header.addEventListener("click", () => {
            const body = header.nextElementSibling;
            if (!body || !body.classList.contains("card-body")) return;
            const isCollapsed = header.classList.contains("collapsed");

            if (isCollapsed) {
                document.querySelectorAll(".card-header.section-toggle").forEach((h) => {
                    if (h === header) return;
                    h.classList.add("collapsed");
                    const b = h.nextElementSibling;
                    if (b) b.classList.add("collapsed");
                });
                header.classList.remove("collapsed");
                body.classList.remove("collapsed");
            } else {
                header.classList.add("collapsed");
                body.classList.add("collapsed");
            }
        });
    });

    function openSectionFor(input) {
        if (!input) return;
        const card = input.closest(".form-card");
        if (!card) return;
        const header = card.querySelector(".card-header.section-toggle");
        const body = card.querySelector(".card-body");
        if (!header || !body) return;
        document.querySelectorAll(".card-header.section-toggle").forEach((h) => {
            if (h === header) return;
            h.classList.add("collapsed");
            const b = h.nextElementSibling;
            if (b) b.classList.add("collapsed");
        });
        header.classList.remove("collapsed");
        body.classList.remove("collapsed");
    }

    // Name is locked for good once the patient exists (this page is only
    // ever reached for an EXISTING patient_code — /nurse_new_record/<id>).
    // Server also ignores these fields on update; this just makes the UI honest.
    ["lastName", "firstName"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            el.readOnly = true;
            el.title = "Name cannot be edited after the patient record is created.";
            el.style.background = "var(--bg-muted, #f1f5f9)";
            el.style.cursor = "not-allowed";
        }
    });

    function wireNoneExclusive(groupSelector, noneSelector) {
        const group = document.querySelectorAll(groupSelector);
        const none = document.querySelector(noneSelector);
        if (!none) return;
        none.addEventListener("change", () => {
            if (none.checked) group.forEach((cb) => { if (cb !== none) cb.checked = false; });
        });
        group.forEach((cb) => {
            if (cb === none) return;
            cb.addEventListener("change", () => { if (cb.checked) none.checked = false; });
        });
    }
    wireNoneExclusive(".pmh", ".pmh-none");
    wireNoneExclusive(".fh", ".fh-none");

    // Menstrual & Pregnancy History is female-only: hide the whole card for male patients
    const FEMALE_ONLY_IDS = ["menarcheAge", "lmp", "gravida", "para"];
    function toggleFemaleOnlyCard() {
        const sexEl = document.getElementById("sex");
        const isMale = !!sexEl && sexEl.value.trim().toLowerCase() === "male";
        const card = document.getElementById("obGyneCard");
        if (card) card.style.display = isMale ? "none" : "";
        if (isMale) {
            // don't submit stale values (buildPayload sends empty fields as null)
            FEMALE_ONLY_IDS.forEach((id) => { const el = document.getElementById(id); if (el) el.value = ""; });
        }
    }
    const sexSelect = document.getElementById("sex");
    if (sexSelect) sexSelect.addEventListener("change", toggleFemaleOnlyCard);
    toggleFemaleOnlyCard(); // sex is pre-filled, so apply on load

    // ---------------------------------------------------------------
    // Prefill from the patient's previous record (all fields stay editable).
    // Only carries over things that tend to stay the same between visits.
    // NOT carried over: assessment date, vitals/measurements, physical exam,
    // CVD questionnaire answers, LMP -- those are re-taken each visit.
    // ---------------------------------------------------------------
    function setField(id, value) {
        const el = document.getElementById(id);
        if (!el || value === null || value === undefined || value === "") return;
        el.value = value; // <option>s have no value attr, so text == value
    }

    function setChecks(className, values) {
        const wanted = new Set(values || []);
        document.querySelectorAll(`.${className}`).forEach((cb) => {
            if (cb.value !== "None") cb.checked = wanted.has(cb.value);
        });
    }

    function applyPrefill() {
        const p = window.__prefill;
        if (!p || !p.visit) return;
        const v = p.visit;
        const c = p.conditions || {};

        // Section 3 & 4: PMH / Family History. Empty list on a submitted record = "None reported".
        [["pmh", "pmh-none", c.pmh], ["fh", "fh-none", c.family_history]].forEach(([cls, noneCls, list]) => {
            setChecks(cls, list);
            const none = document.querySelector(`.${noneCls}`);
            if (none && (!list || list.length === 0) && v.status === "submitted") none.checked = true;
        });
        setField("pastSurgical", v.past_surgical_history);

        // Section 6: lifestyle
        if (v.smoking_status) {
            const r = Array.from(document.querySelectorAll('input[name="smoke"]')).find((x) => x.value === v.smoking_status);
            if (r) r.checked = true;
        }
        setField("alcohol", v.alcohol_intake);
        setField("illicitDrugs", v.illicit_drug_use);
        setField("physicalActivity", v.physical_activity);
        setChecks("diet", c.diet);

        // Section 7: diabetes history
        setField("diabetesDiagnosis", v.diabetes_diagnosis);
        setChecks("dm-sym", c.dm_symptom);

        // Section 8: immunizations (nurse ticks any new ones)
        setChecks("immu", c.immunization);

        // Section 9: menstrual history (stable parts only; LMP is re-entered)
        setField("menarcheAge", v.menarche_age);
        setField("gravida", v.gravida);
        setField("para", v.para);
    }
    applyPrefill();
    toggleFemaleOnlyCard(); // re-run so male patients still get the card hidden/cleared



    // ---------------------------------------------------------------
    // Validation feedback: open the section(s) holding missing fields,
    // wait for the expand animation to finish, THEN scroll to the first
    // missing field (scrolling while the section is still collapsed lands
    // in the wrong place), shake/pulse every missing field, flag the section
    // headers, and show a short toast.
    // ---------------------------------------------------------------
    (function injectValidationStyles() {
        if (document.getElementById('validation-fx-style')) return;
        const s = document.createElement('style');
        s.id = 'validation-fx-style';
        s.textContent = `
        @keyframes nurse-shake { 0%,100%{transform:translateX(0)} 20%{transform:translateX(-7px)} 40%{transform:translateX(7px)} 60%{transform:translateX(-4px)} 80%{transform:translateX(4px)} }
        @keyframes nurse-pulse { 0%{box-shadow:0 0 0 0 rgba(220,38,38,.55)} 100%{box-shadow:0 0 0 14px rgba(220,38,38,0)} }
        .nurse-attn { animation: nurse-shake .45s ease, nurse-pulse .9s ease-out 2; }
        .field-input.field-error, .group-error { border-color:#dc2626; }
        .card-header.section-has-error { color:#b91c1c; }
        .section-error-badge { margin-left:auto; margin-right:.75rem; padding:.15rem .6rem; border-radius:999px; background:#fee2e2; color:#b91c1c; font-size:.7rem; font-weight:700; text-transform:none; white-space:nowrap; }
        .validation-toast { position:fixed; top:16px; left:50%; transform:translate(-50%,-12px); background:#b91c1c; color:#fff; padding:.65rem 1.1rem; border-radius:10px; font-size:.9rem; font-weight:600; box-shadow:0 8px 24px rgba(0,0,0,.25); opacity:0; transition:opacity .2s ease, transform .2s ease; z-index:10000; pointer-events:none; }
        .validation-toast.visible { opacity:1; transform:translate(-50%,0); }
        @media (prefers-reduced-motion: reduce) { .nurse-attn { animation:none; outline:3px solid #dc2626; } }
`;
        document.head.appendChild(s);
    })();

    function refreshSectionBadges() {
        document.querySelectorAll('.form-card').forEach((card) => {
            const header = card.querySelector('.card-header.section-toggle');
            if (!header) return;
            const has = !!card.querySelector('.field-error, .group-error');
            header.classList.toggle('section-has-error', has);
            let badge = header.querySelector('.section-error-badge');
            if (has && !badge) {
                badge = document.createElement('span');
                badge.className = 'section-error-badge';
                badge.textContent = 'Required fields missing';
                header.insertBefore(badge, header.querySelector('.section-toggle-icon'));
            } else if (!has && badge) {
                badge.remove();
            }
        });
    }
    (function wireBadgeRefresh() {
        const f = document.getElementById('intakeForm');
        if (!f) return;
        const sched = () => setTimeout(refreshSectionBadges, 0);
        f.addEventListener('input', sched);
        f.addEventListener('change', sched);
    })();

    let toastTimer = null;
    function showValidationToast(message) {
        let t = document.querySelector('.validation-toast');
        if (!t) {
            t = document.createElement('div');
            t.className = 'validation-toast';
            t.setAttribute('role', 'alert');
            document.body.appendChild(t);
        }
        t.textContent = message;
        requestAnimationFrame(() => t.classList.add('visible'));
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => t.classList.remove('visible'), 4000);
    }

    function attention(el) {
        el.classList.remove('nurse-attn');
        void el.offsetWidth; // restart the animation if it is already running
        el.classList.add('nurse-attn');
        el.addEventListener('animationend', () => el.classList.remove('nurse-attn'), { once: true });
    }

    function afterExpand(el, wasCollapsed, cb) {
        const body = el.closest('.card-body');
        if (!wasCollapsed || !body) { cb(); return; }
        let done = false;
        const finish = () => {
            if (done) return;
            done = true;
            body.removeEventListener('transitionend', onEnd);
            cb();
        };
        const onEnd = (e) => { if (e.target === body) finish(); };
        body.addEventListener('transitionend', onEnd);
        const dur = parseFloat(getComputedStyle(body).transitionDuration) || 0;
        if (!dur) requestAnimationFrame(finish);
        else setTimeout(finish, dur * 1000 + 150); // fallback if transitionend never fires
    }

    // Returns true when there is at least one missing field.
    function revealErrors(invalids) {
        refreshSectionBadges();
        if (!invalids.length) return false;

        // First missing field in page order, not in the order we happened to check.
        invalids.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
        const first = invalids[0];

        const firstBody = first.closest('.card-body');
        const wasCollapsed = !!(firstBody && firstBody.classList.contains('collapsed'));
        openSectionFor(first);
        refreshSectionBadges();

        const n = invalids.length;
        showValidationToast(`Please complete ${n} required field${n > 1 ? 's' : ''} (highlighted in red).`);

        afterExpand(first, wasCollapsed, () => {
            first.scrollIntoView({ behavior: 'smooth', block: 'center' });
            if (!first.matches('input, select, textarea, button') && !first.hasAttribute('tabindex')) first.tabIndex = -1;
            first.focus({ preventScroll: true });
            invalids.forEach(attention);
        });
        return true;
    }

    function clearAllErrors() {
        document.querySelectorAll(".field-input.field-error").forEach((el) => el.classList.remove("field-error"));
        document.querySelectorAll(".field-error-text, .group-error-text").forEach((m) => m.remove());
        document.querySelectorAll(".group-error").forEach((g) => g.classList.remove("group-error"));
        refreshSectionBadges();
    }

    function markGroupError(groupEl, message, clearOnSelector) {
        groupEl.classList.add("group-error");
        let msg = groupEl.parentElement.querySelector(".group-error-text");
        if (!msg) {
            msg = document.createElement("span");
            msg.className = "group-error-text";
            groupEl.insertAdjacentElement("afterend", msg);
        }
        msg.textContent = message;
        const clearOnce = () => {
            groupEl.classList.remove("group-error");
            if (msg) msg.remove();
            document.querySelectorAll(clearOnSelector).forEach((cb) => cb.removeEventListener("change", clearOnce));
        };
        document.querySelectorAll(clearOnSelector).forEach((cb) => cb.addEventListener("change", clearOnce));
    }

    function markFieldError(input, message) {
        input.classList.add("field-error");
        let msg = input.parentElement.querySelector(".field-error-text");
        if (!msg) {
            msg = document.createElement("span");
            msg.className = "field-error-text";
            input.insertAdjacentElement("afterend", msg);
        }
        msg.textContent = message;
        const clearOnce = () => {
            input.classList.remove("field-error");
            const m = input.parentElement.querySelector(".field-error-text");
            if (m) m.remove();
            input.removeEventListener("input", clearOnce);
            input.removeEventListener("change", clearOnce);
        };
        input.addEventListener("input", clearOnce);
        input.addEventListener("change", clearOnce);
    }

    // requireClinicalGroups: only enforced on final submit, not a draft save --
    // a draft is explicitly allowed to be incomplete.
    // Returns true when the record is valid.
    function validateRecord(visit, requireClinicalGroups) {
        clearAllErrors();
        const invalids = [];

        const need = (id, value, message) => {
            const input = document.getElementById(id);
            if (!input) return;
            if (value === null || value === undefined || value === "") {
                markFieldError(input, message);
                invalids.push(input);
            }
        };

        need("dateAssessment", visit.assessment_date, "Date of Assessment is required.");

        if (requireClinicalGroups) {
            [
                { wrapper: document.getElementById("pmhGroup"), selector: ".pmh" },
                { wrapper: document.getElementById("fhGroup"), selector: ".fh" },
            ].forEach(({ wrapper, selector }) => {
                if (!wrapper) return;
                const anyChecked = Array.from(document.querySelectorAll(selector)).some((cb) => cb.checked);
                if (!anyChecked) {
                    markGroupError(wrapper, 'Select at least one, or check "None reported".', selector);
                    invalids.push(wrapper);
                }
            });

            const smokeWrapper = document.querySelector('input[name="smoke"]')?.closest(".radio-card-wrapper");
            if (smokeWrapper && !document.querySelector('input[name="smoke"]:checked')) {
                markGroupError(smokeWrapper, "Please select an option.", 'input[name="smoke"]');
                invalids.push(smokeWrapper);
            }

            need("bpSystolic",  visit.bp_systolic,       "Systolic BP is required.");
            need("bpDiastolic", visit.bp_diastolic,      "Diastolic BP is required.");
            need("hr",          visit.heart_rate,        "Heart Rate is required.");
            need("rr",          visit.respiratory_rate,  "Respiratory Rate is required.");
            need("height",      visit.height_cm,         "Height is required.");
            need("weight",      visit.weight_kg,         "Weight is required.");
            need("waist",       visit.waist_cm,          "Waist Circumference is required.");
        }

        return !revealErrors(invalids);
    }

    const submitBtn = document.getElementById("submitIntakeBtn");
    const draftBtn = document.getElementById("saveDraftBtn");

    submitBtn.addEventListener("click", () => submitRecord("submitted"));
    draftBtn.addEventListener("click", () => submitRecord("draft"));

    async function submitRecord(status) {
        const payload = buildPayload(status);

        if (!validateRecord(payload.visit, status === "submitted")) {
            return;
        }

        submitBtn.disabled = true;
        draftBtn.disabled = true;

        try {
            const res = await fetch(`/api/patients/${encodeURIComponent(patientId)}/records`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            const data = await res.json();

            if (!res.ok) {
                alert(data.error || "Something went wrong saving this record.");
                submitBtn.disabled = false;
                draftBtn.disabled = false;
                return;
            }

            if (status === "draft") {
                submitBtn.disabled = false;
                draftBtn.disabled = false;
                showDraftSavedDialog({
                    message: "Draft saved.",
                    onGo: () => { window.location.href = window.__dataManagementUrl || "/nurse_data_management"; },
                    onStay: () => {},
                });
            } else {
                window.location.href = window.__screeningUrl || `/nurse/screening/${encodeURIComponent(patientId)}`;
            }
        } catch (err) {
            console.error(err);
            alert("Network error — please check your connection and try again.");
            submitBtn.disabled = false;
            draftBtn.disabled = false;
        }
    }

    function calculateBMI() {
    const heightCm = parseFloat(document.getElementById("height").value);
    const weightKg = parseFloat(document.getElementById("weight").value);
    const bmiField = document.getElementById("bmi");
    const obesityField = document.getElementById("obesityClass");

    if (!heightCm || !weightKg || heightCm <= 0) {
        bmiField.value = "";
        obesityField.value = "";
        return;
    }

    const heightM = heightCm / 100;
    const bmi = weightKg / (heightM * heightM);
    bmiField.value = bmi.toFixed(1);
    obesityField.value = classifyBMI(bmi);
}

    function classifyBMI(bmi) {
        if (bmi < 18.5) return "Underweight";
        if (bmi < 23) return "Normal";
        if (bmi < 25) return "Overweight (At Risk)";
        if (bmi < 30) return "Obese I";
        return "Obese II";
    }

    document.getElementById("height").addEventListener("input", calculateBMI);
    document.getElementById("weight").addEventListener("input", calculateBMI);
    
    function val(id) {
        const el = document.getElementById(id);
        return el ? (el.value === "" ? null : el.value) : null;
    }

    function checkedValues(className) {
        return Array.from(document.querySelectorAll(`.${className}:checked`)).map(el => el.value);
    }

    function buildPayload(status) {
        return {
            patient: {
                last_name: val("lastName"),
                first_name: val("firstName"),
                middle_name: val("middleName"),
                father_last_name: val("fatherLastName"),
                father_first_name: val("fatherFirstName"),
                mother_last_name: val("motherLastName"),
                mother_first_name: val("motherFirstName"),
                contact_number: val("contactNumber"),
                spouse_last_name: val("spouseLastName"),
                spouse_first_name: val("spouseFirstName"),
                birthdate: val("birthdate"),
                sex: val("sex"),
                civil_status: val("civilStatus"),
                religion: val("religion"),
                occupation: val("occupation"),
                education: val("education"),
                barangay_name: val("barangay"),
                address: val("address"),
                phic_membership: val("phicMembership"),
                phic_type: val("phicType"),
            },

            visit: {
                assessment_date: val("dateAssessment"),
                status: status,
                smoking_status: document.querySelector('input[name="smoke"]:checked')?.value || null,
                alcohol_intake: val("alcohol"),
                illicit_drug_use: val("illicitDrugs"),
                physical_activity: val("physicalActivity"),
                past_surgical_history: val("pastSurgical"),
                diabetes_diagnosis: val("diabetesDiagnosis"),
                bp_systolic: val("bpSystolic"),
                bp_diastolic: val("bpDiastolic"),
                heart_rate: val("hr"),
                respiratory_rate: val("rr"),
                height_cm: val("height"),
                weight_kg: val("weight"),
                waist_cm: val("waist"),
                bmi: val("bmi"),
                obesity_class: val("obesityClass"),
                pe_skin: val("peSkin"),
                pe_heent: val("peHeent"),
                pe_chest: val("peChest"),
                pe_heart: val("peHeart"),
                pe_abdomen: val("peAbdomen"),
                pe_extremities: val("peExtremities"),
                menarche_age: val("menarcheAge"),
                lmp_date: val("lmp"),
                gravida: val("gravida"),
                para: val("para"),
                clinical_notes: null,
            },

            conditions: {
                pmh: checkedValues("pmh").filter((v) => v !== "None"),
                family_history: checkedValues("fh").filter((v) => v !== "None"),
                diet: checkedValues("diet"),
                immunization: checkedValues("immu"),
                dm_symptom: checkedValues("dm-sym"),
            },

            cvd_responses: buildCvdResponses(),
        };
    }

    function buildCvdResponses() {
        const keys = [
            "q1_chest_discomfort",
            "q2_pain_center_left_arm",
            "q3_occurs_uphill_hurrying",
            "q4_slows_down_if_occurs",
            "q5_relieved_by_rest_tablet",
            "q6_relieved_under_10min",
            "q7_severe_pain_30min_plus",
            "q8_tia_stroke_symptoms",
        ];
        const selects = document.querySelectorAll(".cvd-q");
        const responses = {};
        selects.forEach((el, i) => {
            if (i < keys.length) {
                responses[keys[i]] = el.value.toLowerCase().startsWith("yes");
            }
        });
        return responses;
    }
});

// Shared "what next?" dialog after a draft save -- same preference key as
// nurse_intake.js so the nurse's choice carries across both pages.
function showDraftSavedDialog({ message, onGo, onStay }) {
    const PREF_KEY = 'nurseDraftGoToDataMgmt'; // '' = ask each time, 'always', 'never'
    const pref = localStorage.getItem(PREF_KEY) || '';
    if (pref === 'always') { onGo(); return; }
    if (pref === 'never') { onStay(); return; }

    const overlay = document.createElement('div');
    overlay.className = 'nurse-modal-overlay';
    overlay.innerHTML = `
        <div class="nurse-modal" role="dialog" aria-modal="true" aria-labelledby="draftModalTitle">
            <h3 id="draftModalTitle">What's next?</h3>
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
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close('stay'); });
    document.addEventListener('keydown', function escOnce(ev) {
        if (ev.key === 'Escape') { close('stay'); document.removeEventListener('keydown', escOnce); }
    });
}