"""
Patient self-service edits: what a patient may change, and that a nurse is told.

  - anthropometrics (height/weight/waist/BMI/obesity class) and the
    assessment date can never be changed from the patient portal
  - any other allowed edit flags the visit for the nurse's Data Management bell
  - a relocation (address change) flags the patient's latest visit too
  - the address cascade only accepts a region/city/barangay chain that really exists
Goes in tests/ next to the other test_*.py files.
"""
import json
import uuid

from app.models import lookup_model, visit_model
from app.models.db import get_connection


def _seed(app):
    code = f"EDIT-{uuid.uuid4().hex[:8]}"
    with app.app_context():
        conn = get_connection()
        pid = conn.execute(
            """INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex)
               VALUES (?, 'Test', 'Edit', '1990-01-01', 'Male')""", (code,)
        ).lastrowid
        vid = conn.execute(
            """INSERT INTO visits (patient_id, visit_type, assessment_date,
                                   height_cm, weight_kg, waist_cm, bmi, bp_systolic)
               VALUES (?, 'intake', '2026-09-23', 160, 60, 80, 23.4, 120)""", (pid,)
        ).lastrowid
        conn.commit()
        conn.close()
    return pid, vid


def _visit(app, vid):
    with app.app_context():
        conn = get_connection()
        row = dict(conn.execute("SELECT * FROM visits WHERE id = ?", (vid,)).fetchone())
        conn.close()
    return row


def test_patient_cannot_edit_anthropometrics_or_assessment_date(app):
    pid, vid = _seed(app)
    with app.app_context():
        for locked in ("height_cm", "weight_kg", "waist_cm", "bmi", "obesity_class", "assessment_date"):
            assert locked not in visit_model.PATIENT_EDITABLE_VISIT_FIELDS
        result = visit_model.patient_update_visit_vitals(
            vid, pid, {"height_cm": 999, "weight_kg": 1, "waist_cm": 1, "assessment_date": "2000-01-01"}
        )
    assert result["ok"] is False
    row = _visit(app, vid)
    assert (row["height_cm"], row["weight_kg"], row["waist_cm"]) == (160, 60, 80)
    assert row["assessment_date"] == "2026-09-23"
    assert row["edited_by_patient_at"] is None          # a refused edit must not raise a flag


def test_allowed_edit_is_applied_and_flags_nurse_until_reviewed(app):
    pid, vid = _seed(app)
    with app.app_context():
        # the locked fields riding along with an allowed one are ignored, not applied
        result = visit_model.patient_update_visit_vitals(vid, pid, {"bp_systolic": 135, "height_cm": 999})
    assert result["ok"] and result["changed"] == ["bp_systolic"]
    row = _visit(app, vid)
    assert row["bp_systolic"] == 135 and row["height_cm"] == 160 and row["bmi"] == 23.4

    with app.app_context():
        patients = visit_model.attach_pending_patient_edits([{"patient_id": pid}, {"patient_id": -1}])
        assert patients[0]["pending_edit"]["fields"] == ["BP systolic"]
        assert patients[1]["pending_edit"] is None
        assert visit_model.acknowledge_patient_edits_for_patient(pid, staff_id=None) == 1
        assert visit_model.attach_pending_patient_edits([{"patient_id": pid}])[0]["pending_edit"] is None


def test_relocation_flags_the_latest_visit_with_the_old_address(app):
    pid, vid = _seed(app)
    with app.app_context():
        assert visit_model.record_patient_profile_edit(pid, "location", "Blk 1, Don Jose, Santa Rosa") is True
    row = _visit(app, vid)
    assert json.loads(row["edited_fields"]) == ["location"]
    assert json.loads(row["patient_edit_previous_values"])["location"] == "Blk 1, Don Jose, Santa Rosa"
    with app.app_context():
        flagged = visit_model.attach_pending_patient_edits([{"patient_id": pid}])[0]["pending_edit"]
    assert flagged["fields"] == ["Address / location"]


def test_location_edit_without_any_visit_has_nothing_to_flag(app):
    with app.app_context():
        conn = get_connection()
        pid = conn.execute(
            """INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex)
               VALUES (?, 'No', 'Visits', '1990-01-01', 'Male')""", (f"NOVIS-{uuid.uuid4().hex[:6]}",)
        ).lastrowid
        conn.commit()
        conn.close()
        assert visit_model.record_patient_profile_edit(pid, "location", "x") is False


def test_address_cascade_rejects_chains_that_do_not_exist(app, monkeypatch):
    monkeypatch.setattr(lookup_model, "_psgc_cache", {
        "regions": [{"code": "R1", "name": "Region One"}, {"code": "R2", "name": "Region Two"}],
        "cities": [{"code": "C1", "name": "City One", "regionCode": "R1"},
                   {"code": "C2", "name": "City Two", "regionCode": "R2"}],
        "barangays": [{"code": "B1", "name": "Alpha", "cityCode": "C1"},
                      {"code": "B2", "name": "Beta", "cityCode": "C2"}],
    })
    monkeypatch.setattr(lookup_model, "_psgc_index", None)
    with app.app_context():
        barangay_id, error = lookup_model.resolve_psgc_location("R1", "C1", "B1")
        assert barangay_id and error is None
        for bad in (("R1", "C1", "B2"),        # barangay belongs to another city
                    ("R2", "C1", "B1"),        # city belongs to another region
                    ("R1", "C1", "nope"), ("", "", ""), (None, None, None)):
            assert lookup_model.resolve_psgc_location(*bad)[0] is None
    monkeypatch.setattr(lookup_model, "_psgc_index", None)   # don't leak the fake dataset to other tests
