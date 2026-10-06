from datetime import datetime, timedelta, timezone
import time

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_connection, get_db
from app.controllers.auth_controller import authenticate
from app.models import patient_model, settings as settings_model, user as user_model
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = type("C", (Config,), {
        "DATABASE": str(tmp_path / "privacy.sqlite3"),
        "TESTING": True,
        "REQUIRE_ADMIN_APPROVAL": True,
        "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"),
    })
    return create_app(cfg)


def add_user(app, email, role="medical_officer"):
    with app.app_context():
        return user_model.create_user({
            "first_name": "Test", "middle_name": None, "last_name": "User",
            "birthday": "1990-01-01", "sex": "female", "email": email,
            "phone": "9171234567", "role": role, "facility": "lhui",
            "barangay": "aplaya",
        }, generate_password_hash("Password123!"), status="approved")


def add_patient(app, code="PATIENT-2026-0001"):
    with app.app_context():
        conn = get_connection()
        barangay_id = conn.execute("SELECT id FROM barangays ORDER BY id LIMIT 1").fetchone()[0]
        patient_id = conn.execute(
            "INSERT INTO patients (patient_code,last_name,first_name,birthdate,sex,barangay_id,password_hash,must_change_password) "
            "VALUES (?, 'Portal', 'Patient', '1990-01-01', 'Female', ?, ?, 0)",
            (code, barangay_id, generate_password_hash("PatientPassword123!")),
        ).lastrowid
        conn.commit()
        return patient_id


def active_session(client, user_id, role="medical_officer"):
    with client.session_transaction() as session:
        session.update({
            "user_id": user_id,
            "user_role": role,
            "user_name": "Test User",
            "security_version": 1,
        })


def active_patient_session(client, patient_id, version=1):
    with client.session_transaction() as session:
        session.update({"patient_id": patient_id, "security_version": version, "patient_sv": 0})


def add_deleted_patient(app, code, age_days):
    deleted_at = (datetime.now(timezone.utc) - timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        conn = get_connection()
        conn.execute(
            "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex, deleted_at) "
            "VALUES (?, 'Test', 'Patient', '1990-01-01', 'Male', ?)",
            (code, deleted_at),
        )
        conn.commit()
        conn.close()
    return deleted_at


def test_recycle_bin_setting_falls_back_on_missing_or_invalid_values(app):
    with app.app_context():
        assert settings_model.get_recycle_bin_days() == 15
        settings_model.set_setting(settings_model.RECYCLE_BIN_DAYS_KEY, "invalid")
        assert settings_model.get_recycle_bin_days() == 15
        settings_model.set_setting(settings_model.RECYCLE_BIN_DAYS_KEY, "365")
        assert settings_model.get_recycle_bin_days() == 15


@pytest.mark.parametrize("days", [7, 15, 30])
def test_recycle_bin_setting_accepts_only_supported_days(app, days):
    with app.app_context():
        settings_model.set_recycle_bin_days(days)
        assert settings_model.get_recycle_bin_days() == days


@pytest.mark.parametrize("days", [None, 0, 8, 14, 31, "7"])
def test_recycle_bin_setting_rejects_disallowed_days(app, days):
    with app.app_context(), pytest.raises(ValueError):
        settings_model.set_recycle_bin_days(days)


@pytest.mark.parametrize("days", [7, 15, 30])
def test_purge_uses_selected_recycle_bin_period(app, days):
    add_deleted_patient(app, f"OLD-{days}", days + 2)
    add_deleted_patient(app, f"NEW-{days}", days - 2)
    with app.app_context():
        settings_model.set_recycle_bin_days(days)
        assert patient_model.purge_expired_deleted_patients() == 1
        conn = get_connection()
        remaining = conn.execute(
            "SELECT patient_code FROM patients WHERE deleted_at IS NOT NULL"
        ).fetchall()
        conn.close()
        assert [row["patient_code"] for row in remaining] == [f"NEW-{days}"]


def test_legacy_data_retention_setting_does_not_control_recycle_bin(app):
    add_deleted_patient(app, "LEGACY-SETTING", 20)
    with app.app_context():
        settings_model.set_data_retention_days(None)
        assert settings_model.get_data_retention_days() is None
        assert settings_model.get_recycle_bin_days() == 15
        assert patient_model.purge_expired_deleted_patients() == 1


def test_deleted_patient_days_remaining_uses_configured_days_and_clamps_at_zero(app):
    add_deleted_patient(app, "BIN-RECENT", 4)
    add_deleted_patient(app, "BIN-EXPIRED", 40)
    with app.app_context():
        settings_model.set_recycle_bin_days(30)
        patients = {row["patient_code"]: row for row in patient_model.list_deleted_patients()}
        assert patients["BIN-RECENT"]["days_remaining"] == 26
        assert patients["BIN-EXPIRED"]["days_remaining"] == 0


def test_run_retention_purge_audits_once_only_when_records_are_removed(app):
    add_deleted_patient(app, "AUDITED-OLD", 20)
    admin_id = add_user(app, "purge-audit-admin@example.com")
    with app.app_context():
        settings_model.set_recycle_bin_days(7)
        assert patient_model.run_retention_purge(force=True) == 1
        rows = get_db().execute(
            "SELECT user_id, user_name, action, severity FROM audit_log "
            "WHERE action LIKE 'Automatic Recycle Bin purge%'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["user_id"] is None
        assert rows[0]["user_name"] == "system"
        assert "1 patient record(s) older than 7 days" in rows[0]["action"]
        assert rows[0]["severity"] == "Warning"
        assert patient_model.run_retention_purge(force=True) == 0
        assert get_db().execute(
            "SELECT COUNT(*) FROM audit_log WHERE action LIKE 'Automatic Recycle Bin purge%'"
        ).fetchone()[0] == 1

    client = app.test_client()
    active_session(client, admin_id)
    audit_page = client.get("/admin/audit-trails")
    assert audit_page.status_code == 200
    assert b"system" in audit_page.data


def test_retention_purge_throttles_repeated_calls(app, monkeypatch):
    add_deleted_patient(app, "THROTTLE-FIRST", 20)
    with app.app_context():
        settings_model.set_recycle_bin_days(7)
    monkeypatch.setattr(patient_model, "_last_retention_purge_at", None)

    with app.app_context():
        assert patient_model.run_retention_purge() == 1
    add_deleted_patient(app, "THROTTLE-SECOND", 20)
    with app.app_context():
        assert patient_model.run_retention_purge() == 0
        assert get_db().execute(
            "SELECT 1 FROM patients WHERE patient_code = ?", ("THROTTLE-SECOND",)
        ).fetchone() is not None


def test_nurse_recycle_bin_page_survives_purge_failure(app, monkeypatch):
    nurse_id = add_user(app, "purge-failure-nurse@example.com", role="health_worker")

    def fail_purge():
        raise RuntimeError("simulated purge failure")

    monkeypatch.setattr(patient_model, "_last_retention_purge_at", None)
    monkeypatch.setattr(patient_model, "purge_expired_deleted_patients", fail_purge)
    client = app.test_client()
    active_session(client, nurse_id, "health_worker")

    response = client.get("/nurse/recycle_bin")

    assert response.status_code == 200
    assert b"Recycle Bin" in response.data


def test_recycle_bin_pages_render_configured_period(app):
    nurse_id = add_user(app, "retention-nurse@example.com", role="health_worker")
    add_patient(app)
    with app.app_context():
        settings_model.set_recycle_bin_days(30)
    client = app.test_client()
    active_session(client, nurse_id, "health_worker")

    management_page = client.get("/nurse/data_management")
    recycle_page = client.get("/nurse/recycle_bin")

    assert b"permanently deleted after 30 days" in management_page.data
    assert b"permanently deleted after 15 days" not in management_page.data
    assert b"permanently removed 30 days after deletion" in recycle_page.data
    assert b"15 days" not in recycle_page.data


def test_admin_can_shorten_retention_and_purge_immediately(app):
    add_deleted_patient(app, "SHORTEN-POLICY", 8)
    admin_id = add_user(app, "retention-admin@example.com")
    with app.app_context():
        settings_model.set_recycle_bin_days(30)
    client = app.test_client()
    active_session(client, admin_id)

    response = client.post(
        "/admin/privacy-security/data-retention",
        data={"recycle_bin_days": "7"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Recycle Bin retention updated to 7 days" in response.data
    assert b"1 expired patient record(s) removed immediately" in response.data
    with app.app_context():
        assert settings_model.get_recycle_bin_days() == 7
        assert get_db().execute(
            "SELECT 1 FROM patients WHERE patient_code = ?", ("SHORTEN-POLICY",)
        ).fetchone() is None


def test_non_admin_cannot_change_recycle_bin_retention(app):
    nurse_id = add_user(app, "retention-nonadmin@example.com", role="health_worker")
    client = app.test_client()
    active_session(client, nurse_id, "health_worker")

    response = client.post(
        "/admin/privacy-security/data-retention",
        data={"recycle_bin_days": "7"},
    )

    assert response.status_code == 403


def test_admin_page_shows_recycle_bin_and_due_counts(app, monkeypatch):
    oldest = add_deleted_patient(app, "STATUS-OLD", 9)
    add_deleted_patient(app, "STATUS-NEWER", 2)
    admin_id = add_user(app, "retention-status-admin@example.com")
    with app.app_context():
        settings_model.set_recycle_bin_days(7)
    monkeypatch.setattr(patient_model, "_last_retention_purge_at", time.monotonic())
    client = app.test_client()
    active_session(client, admin_id)

    response = client.get("/admin/privacy-security")

    assert response.status_code == 200
    assert b"Records in Recycle Bin" in response.data
    assert b"Due for purge" in response.data
    assert b"Oldest deleted record" in response.data
    assert b">2</strong>" in response.data
    assert b">1</strong>" in response.data
    assert oldest.encode() in response.data


def test_privacy_page_has_retention_cards_and_only_three_tabs(app):
    admin_id = add_user(app, "retention-cards-admin@example.com")
    client = app.test_client()
    active_session(client, admin_id)

    response = client.get("/admin/privacy-security")

    assert response.status_code == 200
    assert response.data.count(b'class="retention-card"') == 2
    assert response.data.count(b'class="retention-status-item"') == 6
    assert b"Data Retention &amp; Anonymization" in response.data
    assert b"Save Recycle Bin Retention" in response.data
    assert b"Save Record Retention" in response.data
    assert b"Encryption &amp; Storage" not in response.data
    assert b'Save Key Policies' not in response.data
    assert b"Retention, anonymization, roles, agreements" in response.data
    assert b"Timeout, failed login attempts" in response.data
    assert b"Review records" not in response.data
    tab_names = [
        response.data.index(b'data-tab="password"'),
        response.data.index(b'data-tab="data"'),
        response.data.index(b'data-tab="session"'),
    ]
    assert tab_names == sorted(tab_names)


def test_retention_saves_redirect_to_data_privacy_tab(app):
    admin_id = add_user(app, "retention-redirect-admin@example.com")
    client = app.test_client()
    active_session(client, admin_id)

    recycle_response = client.post(
        "/admin/privacy-security/data-retention",
        data={"recycle_bin_days": "30"},
    )
    record_response = client.post(
        "/admin/privacy-security/patient-retention/policy",
        data={"patient_retention_days": "730"},
    )

    assert recycle_response.status_code == 302
    assert recycle_response.headers["Location"].endswith("/admin/privacy-security#data")
    assert record_response.status_code == 302
    assert record_response.headers["Location"].endswith("/admin/privacy-security#data")
    with app.app_context():
        assert settings_model.get_recycle_bin_days() == 30
        assert settings_model.get_patient_retention_days() == 730


def test_purge_cascades_and_database_check_passes(app):
    add_deleted_patient(app, "CASCADE-OLD", 10)
    with app.app_context():
        settings_model.set_recycle_bin_days(7)
        patient_id = get_db().execute(
            "SELECT id FROM patients WHERE patient_code = ?", ("CASCADE-OLD",)
        ).fetchone()["id"]
        visit_id = get_db().execute(
            "INSERT INTO visits (patient_id, visit_type, assessment_date) VALUES (?, 'intake', '2026-09-01')",
            (patient_id,),
        ).lastrowid
        get_db().execute(
            "INSERT INTO lab_screenings (visit_id, fbs_mg_dl, test_datetime) VALUES (?, 100, '2026-09-01 08:00:00')",
            (visit_id,),
        )
        get_db().execute("INSERT INTO cvd_responses (visit_id) VALUES (?)", (visit_id,))
        get_db().commit()
        assert patient_model.purge_expired_deleted_patients() == 1
        assert get_db().execute("SELECT COUNT(*) FROM visits WHERE id = ?", (visit_id,)).fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM lab_screenings WHERE visit_id = ?", (visit_id,)).fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM cvd_responses WHERE visit_id = ?", (visit_id,)).fetchone()[0] == 0

    result = app.test_cli_runner().invoke(args=["db-check"])
    assert result.exit_code == 0
    assert "No foreign key violations." in result.output


def test_purge_expired_cli_forces_purge_and_reports_count(app):
    add_deleted_patient(app, "CLI-OLD", 20)
    with app.app_context():
        settings_model.set_recycle_bin_days(7)

    result = app.test_cli_runner().invoke(args=["purge-expired"])

    assert result.exit_code == 0
    assert "Purged 1 expired patient record(s)." in result.output


def test_failed_login_attempts_increment_and_reset_on_success(app):
    user_id = add_user(app, "login@example.com")
    with app.app_context():
        assert authenticate("login@example.com", "wrong")[1] == "Invalid email or password."
        assert user_model.get_user_by_id(user_id)["failed_login_attempts"] == 1
        assert authenticate("login@example.com", "Password123!")[0]["id"] == user_id
        assert user_model.get_user_by_id(user_id)["failed_login_attempts"] == 0


def test_configured_max_login_attempts_locks_account(app):
    user_id = add_user(app, "locked@example.com")
    with app.app_context():
        settings_model.set_max_login_attempts(3)
        for _ in range(2):
            assert authenticate("locked@example.com", "wrong")[1] == "Invalid email or password."
        error = authenticate("locked@example.com", "wrong")[1]
        assert "account has been suspended" in error
        assert user_model.get_user_by_id(user_id)["status"] == "approved"
        assert "account has been suspended" in authenticate("locked@example.com", "Password123!")[1]


def test_admin_security_settings_change_lockout_threshold_and_page_markup(app):
    user_id = add_user(app, "settings-admin@example.com")
    client = app.test_client()
    active_session(client, user_id)
    response = client.get("/admin/privacy-security")
    assert b"Two-Factor Authentication" not in response.data
    assert b"Recent Login Activity" not in response.data
    assert b'name="max_login_attempts"' in response.data

    response = client.post("/admin/privacy-security/session-timeout", data={
        "session_timeout_minutes": "30", "max_login_attempts": "3",
    })
    assert response.status_code == 302
    with app.app_context():
        assert settings_model.get_max_login_attempts() == 3


def test_disabling_nurse_login_does_not_disable_medical_officer_login(app):
    nurse_id = add_user(app, "role-nurse@example.com", role="health_worker")
    admin_id = add_user(app, "role-admin@example.com", role="medical_officer")
    with app.app_context():
        settings_model.set_role_login_enabled("health_worker", False)
        nurse_user, nurse_error = authenticate("role-nurse@example.com", "Password123!")
        admin_user, admin_error = authenticate("role-admin@example.com", "Password123!")
    assert nurse_user is None
    assert nurse_error == "Logins for this role have been temporarily disabled by an administrator."
    assert admin_user["id"] == admin_id and admin_error is None
    assert nurse_id != admin_id


def test_medical_officer_login_cannot_be_disabled(app):
    with app.app_context():
        with pytest.raises(ValueError, match="cannot be disabled"):
            settings_model.set_role_login_enabled("medical_officer", False)
        assert settings_model.is_role_login_enabled("medical_officer") is True


def test_disabling_nurse_export_blocks_nurse_but_not_admin_export(app):
    nurse_id = add_user(app, "export-nurse@example.com", role="health_worker")
    admin_id = add_user(app, "export-admin@example.com", role="medical_officer")
    with app.app_context():
        settings_model.set_role_export_enabled("health_worker", False)
        nurse_version = settings_model.get_security_version("health_worker")
        admin_version = settings_model.get_security_version("medical_officer")

    nurse = app.test_client()
    active_session(nurse, nurse_id, "health_worker")
    with nurse.session_transaction() as session:
        session["security_version"] = nurse_version
    blocked = nurse.post("/nurse/data_management/export", data={})
    assert blocked.status_code == 302
    assert blocked.headers["Location"].endswith("/nurse/data_management")

    admin = app.test_client()
    active_session(admin, admin_id)
    with admin.session_transaction() as session:
        session["security_version"] = admin_version
    assert admin.get("/admin/audit-trails/export").status_code == 200


def test_force_signout_isolated_by_role(app):
    nurse_id = add_user(app, "signout-nurse@example.com", role="health_worker")
    admin_id = add_user(app, "signout-admin@example.com", role="medical_officer")
    admin = app.test_client()
    nurse = app.test_client()
    active_session(admin, admin_id)
    active_session(nurse, nurse_id, "health_worker")

    assert admin.post(
        "/admin/privacy-security/role-force-signout",
        data={"role": "health_worker"},
    ).status_code == 302
    assert nurse.get("/nurse/dashboard").status_code == 302
    assert admin.get("/admin/privacy-security").status_code == 200

    fresh_admin = app.test_client()
    fresh_nurse = app.test_client()
    active_session(fresh_admin, admin_id)
    active_session(fresh_nurse, nurse_id, "health_worker")
    with app.app_context():
        admin_version = settings_model.get_security_version("medical_officer")
        nurse_version = settings_model.get_security_version("health_worker")
    with fresh_admin.session_transaction() as session:
        session["security_version"] = admin_version
    with fresh_nurse.session_transaction() as session:
        session["security_version"] = nurse_version

    assert fresh_admin.post(
        "/admin/privacy-security/role-force-signout",
        data={"role": "medical_officer"},
    ).status_code == 302
    assert fresh_admin.get("/admin/privacy-security").status_code == 200
    assert fresh_nurse.get("/nurse/dashboard").status_code == 200


def test_patient_login_control_does_not_affect_staff_login(app):
    patient_id = add_patient(app)
    nurse_id = add_user(app, "patient-control-nurse@example.com", role="health_worker")
    admin_id = add_user(app, "patient-control-admin@example.com")
    with app.app_context():
        settings_model.set_role_login_enabled("patient", False)
        from app.controllers.auth_controller import authenticate
        from app.controllers.patient_auth_controller import authenticate_patient
        patient_user, patient_error = authenticate_patient("PATIENT-2026-0001", "PatientPassword123!")
        nurse_user, nurse_error = authenticate("patient-control-nurse@example.com", "Password123!")
        admin_user, admin_error = authenticate("patient-control-admin@example.com", "Password123!")
    assert patient_id == patient_user["id"] and patient_error is None
    assert nurse_user["id"] == nurse_id and nurse_error is None
    assert admin_user["id"] == admin_id and admin_error is None

    client = app.test_client()
    response = client.post("/patient_login", data={
        "patient_code": "PATIENT-2026-0001",
        "password": "PatientPassword123!",
    })
    assert response.status_code == 200
    assert b"Patient portal access is temporarily disabled" in response.data


def test_patient_export_control_does_not_block_nurse_export(app):
    patient_id = add_patient(app, "PATIENT-2026-0002")
    nurse_id = add_user(app, "patient-export-nurse@example.com", role="health_worker")
    with app.app_context():
        settings_model.set_role_export_enabled("patient", False)
        patient_version = settings_model.get_security_version("patient")
        nurse_version = settings_model.get_security_version("health_worker")

    patient = app.test_client()
    active_patient_session(patient, patient_id, patient_version)
    blocked = patient.get("/patient_download_data")
    assert blocked.status_code == 302
    assert blocked.headers["Location"].endswith("/patient_dashboard")

    nurse = app.test_client()
    active_session(nurse, nurse_id, "health_worker")
    with nurse.session_transaction() as session:
        session["security_version"] = nurse_version
    assert nurse.post("/nurse/data_management/export", data={}).status_code == 200


def test_patient_force_signout_does_not_touch_staff_session(app):
    patient_id = add_patient(app, "PATIENT-2026-0003")
    admin_id = add_user(app, "patient-signout-admin@example.com")
    admin = app.test_client()
    patient = app.test_client()
    active_session(admin, admin_id)
    with app.app_context():
        patient_version = settings_model.get_security_version("patient")
        admin_version = settings_model.get_security_version("medical_officer")
    active_patient_session(patient, patient_id, patient_version)
    with admin.session_transaction() as session:
        session["security_version"] = admin_version

    assert admin.post(
        "/admin/privacy-security/role-force-signout",
        data={"role": "patient"},
    ).status_code == 302
    assert patient.get("/patient_dashboard").status_code == 302
    assert admin.get("/admin/privacy-security").status_code == 200