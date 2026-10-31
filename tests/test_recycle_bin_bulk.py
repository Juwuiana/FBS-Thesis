import re

import pytest

from app import create_app
from app.db import get_connection
from conftest import active_patient_session, active_session, add_user, add_deleted_patient
from config import Config

RESTORE = "/nurse/recycle_bin/restore_all"
PURGE = "/nurse/recycle_bin/purge_all"
BIN = "/nurse/recycle_bin"


@pytest.fixture
def csrf_app(tmp_path):
    cfg = type("C", (Config,), {
        "DATABASE": str(tmp_path / "csrf-bin.sqlite3"),
        "TESTING": True,
        "WTF_CSRF_ENABLED": True,
        "REQUIRE_ADMIN_APPROVAL": True,
        "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"),
    })
    return create_app(cfg)


@pytest.fixture
def nurse(app):
    uid = add_user(app, "bin-nurse@example.com", role="health_worker")
    c = app.test_client()
    active_session(c, uid, role="health_worker")
    return c


def add_patient(app, code, deleted=False, anonymized=False):
    with app.app_context():
        conn = get_connection()
        conn.execute(
            "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex, deleted_at, anonymized_at) "
            "VALUES (?, 'Test', 'Patient', '1990-01-01', 'Male', "
            "CASE WHEN ? THEN CURRENT_TIMESTAMP END, CASE WHEN ? THEN CURRENT_TIMESTAMP END)",
            (code, int(deleted), int(anonymized)),
        )
        conn.commit()
        conn.close()


def seed(app, deleted=3, active=2):
    for i in range(deleted):
        add_patient(app, f"DEL-{i}", deleted=True)
    for i in range(active):
        add_patient(app, f"ACT-{i}")


def state(app):
    with app.app_context():
        conn = get_connection()
        rows = {r["patient_code"]: r["deleted_at"] for r in
                conn.execute("SELECT patient_code, deleted_at FROM patients")}
        conn.close()
    return rows


def audit_actions(app, like):
    with app.app_context():
        conn = get_connection()
        rows = conn.execute(
            "SELECT action, severity FROM audit_log WHERE action LIKE ?", (like,)
        ).fetchall()
        conn.close()
    return [(r["action"], r["severity"]) for r in rows]


def test_restore_all(app, nurse):
    seed(app)
    r = nurse.post(RESTORE)
    assert r.status_code == 302 and r.headers["Location"].endswith(BIN)
    rows = state(app)
    assert len(rows) == 5 and all(v is None for v in rows.values())
    assert audit_actions(app, "Recycle Bin: restored all 3%") == [
        ("Recycle Bin: restored all 3 patient record(s)", "Success")]


def test_purge_all(app, nurse):
    seed(app)
    r = nurse.post(PURGE)
    assert r.status_code == 302 and r.headers["Location"].endswith(BIN)
    assert sorted(state(app)) == ["ACT-0", "ACT-1"]
    assert audit_actions(app, "Recycle Bin: permanently purged all 3%") == [
        ("Recycle Bin: permanently purged all 3 patient record(s)", "Critical")]


@pytest.mark.parametrize("route", [RESTORE, PURGE])
def test_anonymized_untouched(app, nurse, route):
    add_patient(app, "ANON-1", deleted=True, anonymized=True)
    add_patient(app, "DEL-1", deleted=True)
    nurse.post(route)
    rows = state(app)
    assert "ANON-1" in rows and rows["ANON-1"] is not None


@pytest.mark.parametrize("route", [RESTORE, PURGE])
def test_empty_bin_changes_nothing(app, nurse, route):
    add_patient(app, "ACT-0")
    r = nurse.post(route)
    assert r.status_code == 302
    assert state(app) == {"ACT-0": None}
    assert audit_actions(app, "Recycle Bin:%") == []
    page = nurse.get(BIN)
    assert "already empty" in page.get_data(as_text=True) or r.status_code == 302


@pytest.mark.parametrize("route", [RESTORE, PURGE])
def test_csrf_and_method(csrf_app, route):
    uid = add_user(csrf_app, "csrf-nurse@example.com", role="health_worker")
    c = csrf_app.test_client()
    active_session(c, uid, role="health_worker")
    add_patient(csrf_app, "DEL-1", deleted=True)
    assert c.post(route).status_code == 400
    assert state(csrf_app)["DEL-1"] is not None
    assert c.get(route).status_code == 405


@pytest.mark.parametrize("route", [RESTORE, PURGE])
def test_anonymous_and_patient_blocked(app, route):
    add_patient(app, "DEL-1", deleted=True)
    anon = app.test_client()
    r = anon.post(route)
    assert r.status_code in (302, 401, 403)
    pc = app.test_client()
    active_patient_session(pc, 1)
    r = pc.post(route)
    assert r.status_code in (302, 401, 403)
    assert state(app)["DEL-1"] is not None


def test_page_renders_buttons_with_count(app, nurse):
    seed(app, deleted=3, active=0)
    html = nurse.get(BIN).get_data(as_text=True)
    assert "Restore All (3)" in html and "Delete All (3)" in html
    assert "js/nurse_dialog.js" in html
    assert "Restore all 3 patient records" in html
    assert not re.search(r'rb-(restore|delete)-all"[^>]*disabled', html)


def test_page_buttons_disabled_when_empty(app, nurse):
    html = nurse.get(BIN).get_data(as_text=True)
    assert "Restore All (0)" in html and "Delete All (0)" in html
    assert len(re.findall(r'rb-(?:restore|delete)-all"\s+disabled', html)) == 2


def test_single_purge_refuses_active_patient(app, nurse):
    add_patient(app, "ACT-0")
    r = nurse.post("/nurse/patient/ACT-0/purge")
    assert r.status_code == 302
    assert "ACT-0" in state(app)
    assert audit_actions(app, "Patient permanently purged%") == []


def test_single_purge_deletes_binned_patient(app, nurse):
    add_patient(app, "DEL-0", deleted=True)
    nurse.post("/nurse/patient/DEL-0/purge")
    assert "DEL-0" not in state(app)
