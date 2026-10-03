"""
all reads/writes to `visits`, `visit_conditions`, and `cvd_responses`
"""
from app.models.db import get_connection
from app.services import sync_queue
import json
import sqlite3
from datetime import datetime


def create_visit(patient_id: int, visit_type: str, data: dict, staff_id: int | None = None) -> int:
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO visits (
                patient_id, visit_type, assessment_date, recorded_by_staff_id,
                smoking_status, alcohol_intake, illicit_drug_use, physical_activity,
                past_surgical_history, diabetes_diagnosis,
                bp_systolic, bp_diastolic, heart_rate, respiratory_rate,
                height_cm, weight_kg, waist_cm, bmi, obesity_class,
                pe_skin, pe_heent, pe_chest, pe_heart, pe_abdomen, pe_extremities,
                menarche_age, lmp_date, gravida, para, clinical_notes, status
            ) VALUES (?,?,?,?, ?,?,?,?, ?,?, ?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?)
        """, (
            patient_id, visit_type, data["assessment_date"], staff_id,
            data.get("smoking_status"), data.get("alcohol_intake"),
            data.get("illicit_drug_use"), data.get("physical_activity"),
            data.get("past_surgical_history"), data.get("diabetes_diagnosis"),
            data.get("bp_systolic"), data.get("bp_diastolic"), data.get("heart_rate"),
            data.get("respiratory_rate"), data.get("height_cm"), data.get("weight_kg"),
            data.get("waist_cm"), data.get("bmi"), data.get("obesity_class"),
            data.get("pe_skin"), data.get("pe_heent"), data.get("pe_chest"),
            data.get("pe_heart"), data.get("pe_abdomen"), data.get("pe_extremities"),
            data.get("menarche_age"), data.get("lmp_date"), data.get("gravida"),
            data.get("para"), data.get("clinical_notes"), data.get("status", "draft"),
        ))
        visit_id = cur.lastrowid
        # Green Computing module integration point: if the network link is currently down,
        # this queues the visit for the Offline & Sync Status page; if the link is up it does
        # nothing. Same transaction as the insert above -- on_visit_saved never commits itself.
        # See docs/NURSE_BRANCH_INTEGRATION.md.
        sync_queue.on_visit_saved(conn, visit_id)
        conn.commit()
        return visit_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_VISIT_UPDATABLE_COLUMNS = {
    "assessment_date", "smoking_status", "alcohol_intake", "illicit_drug_use",
    "physical_activity", "past_surgical_history", "diabetes_diagnosis",
    "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
    "height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class",
    "pe_skin", "pe_heent", "pe_chest", "pe_heart", "pe_abdomen", "pe_extremities",
    "menarche_age", "lmp_date", "gravida", "para", "clinical_notes", "status",
}


def update_visit(visit_id: int, data: dict) -> None:
    """
    Partial update of a visit row -- used by the Data Management "edit
    record" flow (nurse_patient_file_view). Only columns in
    _VISIT_UPDATABLE_COLUMNS are ever touched, and only the keys actually
    present in `data` are updated, so callers can send just the fields
    that changed. Deliberately excludes anything lab_screenings-owned
    (fbs, test method, risk level, etc.) -- test results are never
    editable from here.
    """
    fields = {k: v for k, v in data.items() if k in _VISIT_UPDATABLE_COLUMNS}
    if not fields:
        return
    set_clause = ", ".join(f"{col} = ?" for col in fields)
    params = list(fields.values()) + [visit_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE visits SET {set_clause} WHERE id = ?", params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def replace_visit_conditions(visit_id: int, category: str, codes: list[str]) -> None:
    """
    Like save_visit_conditions, but for editing: clears this visit's
    existing selections in `category` first, so unchecking a box in the
    edit form actually removes it instead of only ever adding new ones
    (save_visit_conditions is INSERT OR IGNORE-only, meant for first-time
    intake where there's nothing to remove).
    """
    conn = get_connection()
    try:
        conn.execute("""
            DELETE FROM visit_conditions
            WHERE visit_id = ? AND condition_id IN (
                SELECT id FROM condition_catalog WHERE category = ?
            )
        """, (visit_id, category))
        for code in codes or []:
            row = conn.execute(
                "SELECT id FROM condition_catalog WHERE category = ? AND code = ?",
                (category, code)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown condition_catalog entry: ({category!r}, {code!r})")
            conn.execute(
                "INSERT OR IGNORE INTO visit_conditions (visit_id, condition_id) VALUES (?, ?)",
                (visit_id, row["id"])
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_visit_conditions(visit_id: int, category: str, codes: list[str]) -> None:
    if not codes:
        return
    conn = get_connection()
    try:
        for code in codes:
            row = conn.execute(
                "SELECT id FROM condition_catalog WHERE category = ? AND code = ?",
                (category, code)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown condition_catalog entry: ({category!r}, {code!r})")
            conn.execute(
                "INSERT OR IGNORE INTO visit_conditions (visit_id, condition_id) VALUES (?, ?)",
                (visit_id, row["id"])
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_cvd_responses(visit_id: int, answers: dict) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO cvd_responses (
                visit_id, q1_chest_discomfort, q2_pain_center_left_arm,
                q3_occurs_uphill_hurrying, q4_slows_down_if_occurs,
                q5_relieved_by_rest_tablet, q6_relieved_under_10min,
                q7_severe_pain_30min_plus, q8_tia_stroke_symptoms
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(visit_id) DO UPDATE SET
                q1_chest_discomfort = excluded.q1_chest_discomfort,
                q2_pain_center_left_arm = excluded.q2_pain_center_left_arm,
                q3_occurs_uphill_hurrying = excluded.q3_occurs_uphill_hurrying,
                q4_slows_down_if_occurs = excluded.q4_slows_down_if_occurs,
                q5_relieved_by_rest_tablet = excluded.q5_relieved_by_rest_tablet,
                q6_relieved_under_10min = excluded.q6_relieved_under_10min,
                q7_severe_pain_30min_plus = excluded.q7_severe_pain_30min_plus,
                q8_tia_stroke_symptoms = excluded.q8_tia_stroke_symptoms
        """, (
            visit_id,
            int(bool(answers.get("q1_chest_discomfort"))),
            int(bool(answers.get("q2_pain_center_left_arm"))),
            int(bool(answers.get("q3_occurs_uphill_hurrying"))),
            int(bool(answers.get("q4_slows_down_if_occurs"))),
            int(bool(answers.get("q5_relieved_by_rest_tablet"))),
            int(bool(answers.get("q6_relieved_under_10min"))),
            int(bool(answers.get("q7_severe_pain_30min_plus"))),
            int(bool(answers.get("q8_tia_stroke_symptoms"))),
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_visits_for_patient(patient_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT v.id AS visit_id, v.assessment_date AS date,
               ls.fbs_mg_dl AS fbs,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk
        FROM visits v
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
        WHERE v.patient_id = ?
        ORDER BY v.id DESC
    """, (patient_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_clinical_notes(visit_id: int, clinical_notes: str) -> None:
    """The screening page's Clinical Notes textarea posts to the lab-screening
    submit route, but clinical_notes lives on the visit row — this is the
    write path for it."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE visits SET clinical_notes = ? WHERE id = ?",
            (clinical_notes, visit_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_visit_by_id(visit_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_conditions_for_visit(visit_id: int) -> dict:
    conn = get_connection()
    rows = conn.execute("""
        SELECT cc.category, cc.code
        FROM visit_conditions vc
        JOIN condition_catalog cc ON cc.id = vc.condition_id
        WHERE vc.visit_id = ?
    """, (visit_id,)).fetchall()
    conn.close()
    result = {"pmh": [], "family_history": [], "diet": [], "immunization": [], "dm_symptom": []}
    for r in rows:
        result[r["category"]].append(r["code"])
    return result


# ---------------------------------------------------------------------------
# Patient portal: editing a past visit's vitals
# ---------------------------------------------------------------------------
# Patients may correct any field a nurse can edit on a past visit (the same
# set the Data Management "edit record" flow uses -- see
# _VISIT_UPDATABLE_COLUMNS above), minus a few that stay nurse-only even
# though a nurse CAN edit them:
#   - status, assessment_date: workflow/record-identity fields, not patient
#     data -- changing them could pull a visit out of nurse worklists or
#     detach it from when the screening actually happened.
#   - pe_* (pe_skin, pe_heent, pe_chest, pe_heart, pe_abdomen, pe_extremities):
#     the nurse's own physical exam findings, not something a patient
#     observes about themselves.
#   - clinical_notes: the provider's own notes on the visit.
#   - height_cm, weight_kg, waist_cm, bmi, obesity_class: anthropometrics,
#     measured by the nurse (BMI/obesity class are derived from them).
# Whatever is off-limits to a nurse's update_visit() in the first place --
# fbs, test method, risk level, anything on lab_screenings -- stays
# off-limits here too, since this still derives from that same set. If a
# new field is added to _VISIT_UPDATABLE_COLUMNS, patients get it
# automatically unless it's added to _NURSE_ONLY_VISIT_FIELDS below.
_NURSE_ONLY_VISIT_FIELDS = {
    "status", "assessment_date",
    "pe_skin", "pe_heent", "pe_chest", "pe_heart", "pe_abdomen", "pe_extremities",
    "clinical_notes",
    # Anthropometrics are measured by the nurse with calibrated equipment, so a
    # patient can't change them from the portal. BMI and obesity class are
    # derived from height/weight, so they are locked with them.
    "height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class",
}
PATIENT_EDITABLE_VISIT_FIELDS = _VISIT_UPDATABLE_COLUMNS - _NURSE_ONLY_VISIT_FIELDS

# Columns stored as numbers. Everything else in PATIENT_EDITABLE_VISIT_FIELDS
# is text/categorical (smoking_status, clinical_notes, status, dates, ...)
# and is written through as-is, same as update_visit() does for a nurse.
_NUMERIC_VISIT_FIELDS = {
    "bp_systolic", "bp_diastolic", "heart_rate", "respiratory_rate",
    "height_cm", "weight_kg", "waist_cm", "bmi",
    "menarche_age", "gravida", "para",
}


def _recompute_bmi(height_cm, weight_kg):
    if not height_cm or not weight_kg:
        return None, None
    h_m = height_cm / 100
    if h_m <= 0:
        return None, None
    bmi = round(weight_kg / (h_m * h_m), 1)
    if bmi < 18.5: obesity_class = "Underweight"
    elif bmi < 23: obesity_class = "Normal"
    elif bmi < 25: obesity_class = "Overweight"
    elif bmi < 30: obesity_class = "Obese Class I"
    else: obesity_class = "Obese Class II"
    return bmi, obesity_class


def patient_update_visit_vitals(visit_id: int, patient_id: int, data: dict) -> dict:
    """
    Apply a patient-submitted correction to one of their own past visits.
    Only PATIENT_EDITABLE_VISIT_FIELDS can change -- the same set a nurse's
    update_visit() can touch, so a patient can edit what a nurse can edit
    and nothing a nurse cannot (fbs and anything lab_screenings-owned is
    never in that set). BMI/obesity_class are recomputed automatically
    when height or weight changes, mirroring how the nurse intake form
    derives them. Records what changed and its prior value so the nurse
    review view can show a before/after, and stamps edited_by_patient_at
    so the nurse-side bell picks it up.

    Returns {"ok": True, "changed": [...]} on success, or
    {"ok": False, "error": "..."} if the visit doesn't belong to this
    patient, nothing eligible changed, or a value fails the column's own
    database constraint (e.g. an out-of-list smoking_status).
    """
    # None means "field wasn't submitted at all"; "" is a deliberate clear
    # and is allowed through, same as a nurse editing the record can clear
    # a free-text field like clinical_notes or past_surgical_history.
    fields = {k: v for k, v in data.items() if k in PATIENT_EDITABLE_VISIT_FIELDS and v is not None}
    if not fields:
        return {"ok": False, "error": "No editable fields were submitted."}

    conn = get_connection()
    try:
        visit = conn.execute(
            "SELECT * FROM visits WHERE id = ? AND patient_id = ?", (visit_id, patient_id)
        ).fetchone()
        if visit is None:
            return {"ok": False, "error": "Visit not found."}
        visit = dict(visit)

        changed, previous = {}, {}
        for col, new_val in fields.items():
            old_val = visit.get(col)
            if old_val is None and new_val == "":
                continue  # clearing an already-empty field is not a change
            # normalize for comparison -- form values arrive as str/float
            try:
                if old_val is not None and float(old_val) == float(new_val):
                    continue
            except (TypeError, ValueError):
                if old_val == new_val:
                    continue
            changed[col] = new_val
            previous[col] = old_val

        if not changed:
            return {"ok": False, "error": "Nothing changed from the recorded values."}

        # merge with any earlier un-acknowledged edit instead of overwriting it,
        # so a nurse reviewing later sees everything that changed since their
        # last look, not just this most recent save
        prior_fields = set(json.loads(visit.get("edited_fields") or "[]"))
        prior_prev = json.loads(visit.get("patient_edit_previous_values") or "{}")
        for k, v in previous.items():
            prior_prev.setdefault(k, v)
        all_fields = sorted(prior_fields | set(changed.keys()))

        set_clause = ", ".join(f"{col} = ?" for col in changed)
        params = list(changed.values()) + [
            datetime.utcnow().isoformat(timespec="seconds"),
            json.dumps(all_fields),
            json.dumps(prior_prev),
            visit_id,
        ]
        try:
            conn.execute(
                f"""UPDATE visits SET {set_clause},
                    edited_by_patient_at = ?, edited_fields = ?,
                    patient_edit_previous_values = ?,
                    edit_acknowledged_at = NULL, edit_acknowledged_by_staff_id = NULL
                    WHERE id = ?""",
                params,
            )
        except sqlite3.IntegrityError:
            # same CHECK constraints a nurse's update_visit() is bound by
            # (e.g. smoking_status must be one of the listed options) --
            # surface this as a normal validation error, not a 500.
            conn.rollback()
            return {"ok": False, "error": "One of the submitted values isn't a recognized option."}
        conn.commit()
        return {"ok": True, "changed": sorted(changed.keys())}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def acknowledge_patient_edit(visit_id: int, staff_id: int | None = None) -> None:
    """Nurse has reviewed a patient's edit -- clears the flag and the stored
    before-values, but leaves edited_by_patient_at as a permanent audit trail
    of when the patient last changed something."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE visits SET edit_acknowledged_at = datetime('now'),
               edit_acknowledged_by_staff_id = ?, patient_edit_previous_values = NULL
               WHERE id = ?""",
            (staff_id, visit_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _merge_edit_flag(conn, visit: dict, changed_keys, previous: dict) -> None:
    """Stamp a visit as patient-edited, merging with any edit the nurse has not
    reviewed yet (so one review shows everything changed since the last look)."""
    prior_fields = set(json.loads(visit.get("edited_fields") or "[]"))
    prior_prev = json.loads(visit.get("patient_edit_previous_values") or "{}")
    for k, v in previous.items():
        prior_prev.setdefault(k, v)
    conn.execute(
        """UPDATE visits SET edited_by_patient_at = ?, edited_fields = ?,
               patient_edit_previous_values = ?,
               edit_acknowledged_at = NULL, edit_acknowledged_by_staff_id = NULL
           WHERE id = ?""",
        (
            datetime.utcnow().isoformat(timespec="seconds"),
            json.dumps(sorted(prior_fields | set(changed_keys))),
            json.dumps(prior_prev),
            visit["id"],
        ),
    )


def record_patient_profile_edit(patient_id: int, key: str, previous_value) -> bool:
    """
    Flag a patient-level change (e.g. key="location" after they relocate) for
    nurse review. Patient-level data has no visit row of its own, so the flag
    rides on the patient's most recent visit, reusing the same bell and
    before/after machinery as a visit edit. Returns False if the patient has
    no visit to attach it to (nothing for a nurse to see in that case).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM visits WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (patient_id,)
        ).fetchone()
        if row is None:
            return False
        _merge_edit_flag(conn, dict(row), [key], {key: previous_value})
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_LABEL_ACRONYMS = {"bp": "BP", "lmp": "LMP", "bmi": "BMI"}

def flag_patient_submitted_record(visit_id: int) -> None:
    """A patient submitted a brand-new record from the portal. Flags that exact
    visit so it shows in the nurse bell and on the Data Management name flag
    until a nurse reviews it. Nothing to compare, so no previous values."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
        if row is None:
            return
        _merge_edit_flag(conn, dict(row), ["new_record"], {})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _field_label(key: str) -> str:
    """Human label for an edited-field key, e.g. bp_systolic -> 'BP systolic'."""
    if key == "location":
        return "Address / location"
    if key == "new_record":
        return "New record submitted"
    words = key.split("_")
    words = [_LABEL_ACRONYMS.get(w, w) for w in words]
    if words[0] not in _LABEL_ACRONYMS.values():
        words[0] = words[0].capitalize()
    return " ".join(words)


def attach_pending_patient_edits(patients: list[dict]) -> list[dict]:
    """
    Adds p["pending_edit"] = {"at": iso, "fields": [labels], "visits": n} to every
    patient row (keyed by p["patient_id"]) that has unreviewed patient edits, or
    None when there are none. One query for the whole page, not one per row.
    """
    ids = [p["patient_id"] for p in patients if p.get("patient_id") is not None]
    pending: dict[int, dict] = {}
    if ids:
        conn = get_connection()
        try:
            marks = ",".join("?" * len(ids))
            rows = conn.execute(f"""
                SELECT patient_id, edited_by_patient_at, edited_fields
                FROM visits
                WHERE patient_id IN ({marks})
                  AND edited_by_patient_at IS NOT NULL AND edit_acknowledged_at IS NULL
            """, ids).fetchall()
        finally:
            conn.close()
        for r in rows:
            entry = pending.setdefault(r["patient_id"], {"at": "", "fields": set(), "visits": 0})
            entry["at"] = max(entry["at"], r["edited_by_patient_at"] or "")
            entry["fields"].update(json.loads(r["edited_fields"] or "[]"))
            entry["visits"] += 1
    for p in patients:
        e = pending.get(p.get("patient_id"))
        p["pending_edit"] = (
            {"at": e["at"], "fields": sorted(_field_label(k) for k in e["fields"]), "visits": e["visits"]}
            if e else None
        )
    return patients


def acknowledge_patient_edits_for_patient(patient_id: int, staff_id: int | None = None) -> int:
    """Nurse marks everything a patient edited as reviewed (all their visits).
    Returns how many visits were cleared."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """UPDATE visits SET edit_acknowledged_at = datetime('now'),
                   edit_acknowledged_by_staff_id = ?, patient_edit_previous_values = NULL
               WHERE patient_id = ? AND edited_by_patient_at IS NOT NULL
                 AND edit_acknowledged_at IS NULL""",
            (staff_id, patient_id),
        )
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def count_pending_patient_edits() -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM visits WHERE edited_by_patient_at IS NOT NULL AND edit_acknowledged_at IS NULL"
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


def list_pending_patient_edits(limit: int = 20) -> list[dict]:
    """Newest first, for the nurse notification bell dropdown."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT v.id AS visit_id, v.patient_id, v.edited_by_patient_at, v.edited_fields,
               v.patient_edit_previous_values,
               p.patient_code, p.first_name, p.last_name
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE v.edited_by_patient_at IS NOT NULL AND v.edit_acknowledged_at IS NULL
          AND p.deleted_at IS NULL AND p.anonymized_at IS NULL
        ORDER BY v.edited_by_patient_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["edited_fields"] = json.loads(d["edited_fields"] or "[]")
        d["patient_edit_previous_values"] = json.loads(d["patient_edit_previous_values"] or "{}")
        result.append(d)
    return result


def get_cvd_responses_for_visit(visit_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM cvd_responses WHERE visit_id = ?", (visit_id,)).fetchone()
    conn.close()
    return dict(row) if row else None