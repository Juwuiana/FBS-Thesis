"""Patient 'Add New Record' + self-reported FBS, exercised together with the
record-retention feature and the nurse-side review card."""
import uuid

from app.models import patient_fbs_model, settings as settings_model
from app.models.db import get_connection

from test_record_retention import _admin_client, _apply_retention, _download_archive, _seed_patient


def _patient(app, sex="Male"):
    code = f"ADD-{uuid.uuid4().hex[:8]}"
    with app.app_context():
        conn = get_connection()
        pid = conn.execute(
            "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex) "
            "VALUES (?, 'Add', 'Record', '1985-02-02', ?)", (code, sex)).lastrowid
        vid = conn.execute(
            "INSERT INTO visits (patient_id, visit_type, assessment_date, status, smoking_status, "
            "alcohol_intake, illicit_drug_use) VALUES (?, 'intake', '2026-01-10', 'submitted', "
            "'Never smoked', 'Never Consumed', 'No')", (pid,)).lastrowid
        conn.execute("INSERT INTO lab_screenings (visit_id, fbs_mg_dl, final_risk_level, test_datetime) VALUES (?, 95, 'Low', '2026-01-10 08:00')", (vid,))
        conn.commit()
        conn.close()
    return pid, code


def _patient_client(app, pid):
    client = app.test_client()
    with client.session_transaction() as s:
        s["patient_id"] = pid
        s["patient_sv"] = 0
        s["security_version"] = settings_model.get_security_version("patient") if False else None
    with app.app_context():
        with client.session_transaction() as s:
            s["security_version"] = settings_model.get_security_version("patient")
    return client


FORM = {
    "smoking_status": "Never smoked", "alcohol_intake": "Never Consumed", "illicit_drug_use": "No",
    "pmh_none": "1", "fh_none": "1",
}


def test_portal_page_renders_add_tab_and_bell(app):
    pid, _ = _patient(app)
    c = _patient_client(app, pid)
    r = c.get("/patient_health_results?view=add")
    assert r.status_code == 200
    assert b'id="addRecordForm"' in r.data and b"patientBellBtn" in r.data


def test_add_record_saves_draft_with_self_reported_fbs(app):
    pid, _ = _patient(app)
    c = _patient_client(app, pid)
    r = c.post("/patient_add_record", data={**FORM, "self_fbs_value": "5.6",
               "self_fbs_unit": "mmol_l", "self_fbs_fasted": "yes"})
    assert r.status_code == 302
    with app.app_context():
        conn = get_connection()
        v = conn.execute("SELECT * FROM visits WHERE patient_id=? AND status='draft'", (pid,)).fetchone()
        assert v is not None and v["edited_by_patient_at"] is not None  # nurse bell flag
        e = patient_fbs_model.list_entries_for_patient(pid)
        conn.close()
    assert len(e) == 1 and e[0]["visit_id"] == v["id"] and round(e[0]["fbs_mg_dl"]) == 101


def test_add_record_validation_rejects_missing_and_future(app):
    pid, _ = _patient(app)
    c = _patient_client(app, pid)
    bad = dict(FORM); bad.pop("smoking_status")
    c.post("/patient_add_record", data=bad)
    c.post("/patient_add_record", data={**FORM, "assessment_date": "2999-01-01"})
    c.post("/patient_add_record", data={**FORM, "self_fbs_value": "5", "self_fbs_unit": "mmol_l"})  # no fasted answer
    with app.app_context():
        conn = get_connection()
        n = conn.execute("SELECT COUNT(*) FROM visits WHERE patient_id=? AND status='draft'", (pid,)).fetchone()[0]
        conn.close()
    assert n == 0


def test_retention_delete_and_anonymize_work_with_self_reported_fbs(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
    del_id = _seed_patient(app, patient_code="RET-FBS-DEL")
    anon_id = _seed_patient(app, patient_code="RET-FBS-ANON")
    with app.app_context():
        for p in (del_id, anon_id):
            patient_fbs_model.create_entry(p, None, 100, "mg_dl", "yes")
    client = _admin_client(app)
    assert _download_archive(client, [del_id]).status_code == 200
    _apply_retention(client, [del_id], action="delete")
    with app.app_context():
        conn = get_connection()
        assert conn.execute("SELECT COUNT(*) FROM patients WHERE id=?", (del_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM patient_fbs_entries WHERE patient_id=?", (del_id,)).fetchone()[0] == 0
        conn.close()
    client = _admin_client(app)
    assert _download_archive(client, [anon_id]).status_code == 200
    _apply_retention(client, [anon_id], action="anonymize")
    with app.app_context():
        conn = get_connection()
        row = conn.execute("SELECT anonymized_at FROM patients WHERE id=?", (anon_id,)).fetchone()
        conn.close()
    assert row is None or row["anonymized_at"] is not None  # anonymized, or deleted when no research consent


def test_new_migration_numbering_has_no_duplicates():
    from app.db import MIGRATIONS_DIR
    nums = [p.name[:4] for p in MIGRATIONS_DIR.glob("*.sql")]
    assert len(nums) == len(set(nums))
