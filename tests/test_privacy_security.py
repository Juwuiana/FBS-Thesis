from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_connection
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
        session.update({"patient_id": patient_id, "security_version": version})


def add_deleted_patient(app, code, age_days):
    deleted_at = (datetime.utcnow() - timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        conn = get_connection()
        conn.execute(
            "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex, deleted_at) "
            "VALUES (?, 'Test', 'Patient', '1990-01-01', 'Male', ?)",
            (code, deleted_at),
        )
        conn.commit()
        conn.close()


def test_retention_setting_changes_automatic_purge_and_persists(app):
    add_deleted_patient(app, "OLD-180", 181)
    add_deleted_patient(app, "NEW-180", 179)
    with app.app_context():
        settings_model.set_data_retention_days(180)
        assert settings_model.get_data_retention_days() == 180
        assert patient_model.purge_expired_deleted_patients() == 1
        conn = get_connection()
        remaining = conn.execute(
            "SELECT patient_code FROM patients WHERE deleted_at IS NOT NULL"
        ).fetchall()
        conn.close()
        assert [row["patient_code"] for row in remaining] == ["NEW-180"]


def test_never_purge_leaves_soft_deleted_patients_untouched(app):
    add_deleted_patient(app, "VERY-OLD", 5000)
    with app.app_context():
        settings_model.set_data_retention_days(None)
        assert patient_model.purge_expired_deleted_patients() == 0
        conn = get_connection()
        found = conn.execute(
            "SELECT 1 FROM patients WHERE patient_code = 'VERY-OLD'"
        ).fetchone()
        conn.close()
        assert found is not None


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
        assert "account has been locked" in error
        assert user_model.get_user_by_id(user_id)["status"] == "recovery"
        assert "awaiting a password reset" in authenticate("locked@example.com", "Password123!")[1]


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