document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("intakeForm");
    const patientId = form.dataset.patientId;

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

    function clearAllErrors() {
        document.querySelectorAll(".radio-card-wrapper.group-error").forEach((g) => {
            g.classList.remove("group-error");
            const msg = g.parentElement.querySelector(".group-error-text");
            if (msg) msg.remove();
        });
        const dateInput = document.getElementById("dateAssessment");
        dateInput.classList.remove("field-error");
        const dateMsg = dateInput.parentElement.querySelector(".field-error-text");
        if (dateMsg) dateMsg.remove();
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
    }

    // requireClinicalGroups: only enforced on final submit, not a draft save --
    // a draft is explicitly allowed to be incomplete.
    function validateRecord(visit, requireClinicalGroups) {
        clearAllErrors();
        let firstInvalid = null;

        if (!visit.assessment_date) {
            const dateInput = document.getElementById("dateAssessment");
            markFieldError(dateInput, "Date of Assessment is required.");
            firstInvalid = dateInput;
        }

        if (requireClinicalGroups) {
            [
                { wrapper: document.getElementById("pmhGroup"), selector: ".pmh" },
                { wrapper: document.getElementById("fhGroup"), selector: ".fh" },
            ].forEach(({ wrapper, selector }) => {
                if (!wrapper) return;
                const anyChecked = Array.from(document.querySelectorAll(selector)).some((cb) => cb.checked);
                if (!anyChecked) {
                    markGroupError(wrapper, 'Select at least one, or check "None reported".', selector);
                    if (!firstInvalid) firstInvalid = wrapper;
                }
            });

            // Smoking is a radio group -- no single input to attach an error
            // to, so it's checked the same way as PMH/Family History above.
            const smokeWrapper = document.querySelector('input[name="smoke"]')?.closest(".radio-card-wrapper");
            if (smokeWrapper && !document.querySelector('input[name="smoke"]:checked')) {
                markGroupError(smokeWrapper, "Please select an option.", 'input[name="smoke"]');
                if (!firstInvalid) firstInvalid = smokeWrapper;
            }

            [
                { input: document.getElementById("alcohol"),      value: visit.alcohol_intake,   message: "Alcohol Intake is required." },
                { input: document.getElementById("illicitDrugs"), value: visit.illicit_drug_use, message: "Illicit Drug Use is required." },
                { input: document.getElementById("bpSystolic"),   value: visit.bp_systolic,       message: "Systolic BP is required." },
                { input: document.getElementById("bpDiastolic"),  value: visit.bp_diastolic,      message: "Diastolic BP is required." },
                { input: document.getElementById("hr"),           value: visit.heart_rate,        message: "Heart Rate is required." },
                { input: document.getElementById("rr"),           value: visit.respiratory_rate,  message: "Respiratory Rate is required." },
                { input: document.getElementById("height"),       value: visit.height_cm,         message: "Height is required." },
                { input: document.getElementById("weight"),       value: visit.weight_kg,         message: "Weight is required." },
                { input: document.getElementById("waist"),        value: visit.waist_cm,          message: "Waist Circumference is required." },
            ].forEach(({ input, value, message }) => {
                if (!input) return;
                if (value === null || value === undefined || value === "") {
                    markFieldError(input, message);
                    if (!firstInvalid) firstInvalid = input;
                }
            });
        }

        if (firstInvalid) {
            firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
            if (typeof firstInvalid.focus === "function") firstInvalid.focus({ preventScroll: true });
        }
        return firstInvalid === null;
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
                    onGo: () => { window.location.href = window.__dataManagementUrl || "/nurse/data_management"; },
                    onStay: () => {},
                });
            } else {
                window.location.href = `/nurse/screening/${encodeURIComponent(patientId)}`;
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