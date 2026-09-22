document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("intakeForm");
    const patientId = form.dataset.patientId;

    const submitBtn = document.getElementById("submitIntakeBtn");
    const draftBtn = document.getElementById("saveDraftBtn");

    submitBtn.addEventListener("click", () => submitRecord("submitted"));
    draftBtn.addEventListener("click", () => submitRecord("draft"));

    async function submitRecord(status) {
        const payload = buildPayload(status);

        if (!payload.visit.assessment_date) {
            alert("Please set the Date of Assessment before saving.");
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
                alert("Draft saved.");
                submitBtn.disabled = false;
                draftBtn.disabled = false;
            } else {
                window.location.href = `/nurse_screening/${encodeURIComponent(patientId)}`;
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
                pmh: checkedValues("pmh"),
                family_history: checkedValues("fh"),
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