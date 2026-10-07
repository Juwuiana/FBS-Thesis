import os
import sqlite3
import sys

from conftest import issue_token
import pytest
from werkzeug.security import check_password_hash, generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app, db as app_db
from app.controllers.auth_controller import authenticate
from app.db import get_db
from app.models import settings as settings_model, user as user_model
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = type("C", (Config,), {
        "DATABASE": str(tmp_path / "staff-controls.sqlite3"),
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "REQUIRE_ADMIN_APPROVAL": True,
        "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"),
    })
    return create_app(cfg)


def add_user(app, email, role="health_worker", status="approved", password="Password123!"):
    with app.app_context():
        return user_model.create_user({
            "first_name": "Test", "middle_name": None, "last_name": "User",
            "birthday": "1990-01-01", "sex": "female", "email": email,
            "phone": "9171234567", "role": role, "facility": "lhui",
            "barangay": "aplaya",
        }, generate_password_hash(password), status=status)


def active_session(client, user_id, role="medical_officer"):
    with client.session_transaction() as session:
        session["session_token"] = issue_token(client, user_id)
        session.update({
            "user_id": user_id,
            "user_role": role,
            "user_name": "Test User",
            "security_version": 1,
        })


def set_login_state(app, user_id, status, attempts):
    with app.app_context():
        get_db().execute(
            "UPDATE users SET status = ?, failed_login_attempts = ? WHERE id = ?",
            (status, attempts, user_id),
        )
        get_db().commit()


def test_lockout_suspends_account_and_reactivation_allows_login(app):
    admin_id = add_user(app, "admin@example.com", role="medical_officer")
    nurse_id = add_user(app, "nurse@example.com")
    with app.app_context():
        max_attempts = settings_model.get_max_login_attempts()
    client = app.test_client()
    active_session(client, admin_id)

    with app.app_context():
        for _ in range(max_attempts - 1):
            assert authenticate("nurse@example.com", "WrongPassword!")[1] == "Invalid email or password."
        _, error = authenticate("nurse@example.com", "WrongPassword!")
        assert error == (
            "Too many failed attempts. Your account has been suspended - "
            "contact your LHU administrator."
        )
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["status"] == "approved"
        assert nurse["is_suspended"] == 1
        assert nurse["failed_login_attempts"] == max_attempts
        audit = get_db().execute(
            "SELECT action, severity FROM audit_log WHERE action = ?",
            (f"Account suspended after {max_attempts} failed login attempts: nurse@example.com",),
        ).fetchone()
        assert audit is not None and audit["severity"] == "Critical"

    table_response = client.get("/admin/data-management")
    assert b'data-status="suspended"' in table_response.data
    assert b'class="risk-pill risk-suspended">Suspended</span>' in table_response.data
    response = client.post(f"/admin/data-management/EMP-{nurse_id:05d}/reactivate")
    assert response.status_code == 302
    with app.app_context():
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["status"] == "approved"
        assert nurse["is_suspended"] == 0
        assert nurse["failed_login_attempts"] == 0
        signed_in, error = authenticate("nurse@example.com", "Password123!")
        assert signed_in["id"] == nurse_id and error is None


@pytest.mark.parametrize(
    ("status", "attempts"),
    [("recovery", 1), ("approved", 0)],
    ids=["password-recovery-request", "approved-account"],
)
def test_unlock_refuses_accounts_that_are_not_locked(app, status, attempts):
    admin_id = add_user(app, "admin@example.com", role="medical_officer")
    nurse_id = add_user(app, "nurse@example.com")
    set_login_state(app, nurse_id, status, attempts)
    client = app.test_client()
    active_session(client, admin_id)

    response = client.post(f"/admin/data-management/EMP-{nurse_id:05d}/unlock")

    assert response.status_code == 302
    with app.app_context():
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["status"] == status
        assert nurse["failed_login_attempts"] == attempts
        assert get_db().execute(
            "SELECT 1 FROM audit_log WHERE action LIKE 'Account unlocked:%'"
        ).fetchone() is None


def test_reset_password_clears_failed_login_attempts(app):
    nurse_id = add_user(app, "nurse@example.com")
    set_login_state(app, nurse_id, "recovery", 4)

    with app.app_context():
        user_model.reset_password(nurse_id, generate_password_hash("NewPassword123!"))
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["status"] == "approved"
        assert nurse["failed_login_attempts"] == 0
        assert check_password_hash(nurse["password_hash"], "NewPassword123!")


def test_forgot_password_remains_recovery_and_not_suspended(app):
    nurse_id = add_user(app, "nurse@example.com")

    response = app.test_client().post(
        "/forgot-password", data={"email": "nurse@example.com"}
    )

    assert response.status_code == 200
    with app.app_context():
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["status"] == "recovery"
        assert nurse["is_suspended"] == 0
        record = next(
            row for row in user_model.get_staff_records()
            if row["email"] == "nurse@example.com"
        )
        assert record["status"] == "Password Recovery"
        assert record["is_password_recovery"] is True


def test_reset_password_endpoint_reactivates_suspended_account(app):
    admin_id = add_user(app, "admin@example.com", role="medical_officer")
    nurse_id = add_user(app, "nurse@example.com")
    with app.app_context():
        user_model.set_suspended(nurse_id, True)
        get_db().execute(
            "UPDATE users SET failed_login_attempts = 5 WHERE id = ?", (nurse_id,)
        )
        get_db().commit()
    client = app.test_client()
    active_session(client, admin_id)

    response = client.post(f"/admin/staff/EMP-{nurse_id:05d}/reset-password")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["temp_password"]
    with app.app_context():
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["status"] == "approved"
        assert nurse["is_suspended"] == 0
        assert nurse["failed_login_attempts"] == 0
        signed_in, error = authenticate("nurse@example.com", payload["temp_password"])
        assert signed_in["id"] == nurse_id and error is None


def test_suspended_account_rejects_correct_password_but_counts_wrong_password(app):
    nurse_id = add_user(app, "nurse@example.com")
    with app.app_context():
        user_model.set_suspended(nurse_id, True)
        signed_in, error = authenticate("nurse@example.com", "Password123!")
        assert signed_in is None
        assert error == "Your account has been suspended. Contact your LHU administrator."
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["failed_login_attempts"] == 0
        assert nurse["last_login_at"] is None

        signed_in, error = authenticate("nurse@example.com", "WrongPassword!")
        assert signed_in is None and error == "Invalid email or password."
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["failed_login_attempts"] == 1
        assert nurse["status"] == "approved"


def test_suspended_user_with_active_session_is_signed_out(app):
    nurse_id = add_user(app, "nurse@example.com")
    with app.app_context():
        user_model.set_suspended(nurse_id, True)
    client = app.test_client()
    active_session(client, nurse_id, "health_worker")

    response = client.get("/nurse/dashboard", follow_redirects=True)

    assert response.status_code == 200
    assert b"Your account has been suspended. Contact your LHU administrator." in response.data
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_admin_can_suspend_and_reactivate_staff_without_changing_status(app):
    admin_id = add_user(app, "admin@example.com", role="medical_officer")
    nurse_id = add_user(app, "nurse@example.com")
    client = app.test_client()
    active_session(client, admin_id)

    suspended = client.post(f"/admin/data-management/EMP-{nurse_id:05d}/suspend")
    assert suspended.status_code == 302
    with app.app_context():
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["is_suspended"] == 1 and nurse["status"] == "approved"
        event = get_db().execute(
            "SELECT severity FROM audit_log WHERE action = ?",
            (f"Staff account suspended: EMP-{nurse_id:05d}",),
        ).fetchone()
        assert event and event["severity"] == "Critical"

    with app.app_context():
        get_db().execute(
            "UPDATE users SET failed_login_attempts = 4 WHERE id = ?", (nurse_id,)
        )
        get_db().commit()
    reactivated = client.post(f"/admin/data-management/EMP-{nurse_id:05d}/reactivate")
    assert reactivated.status_code == 302
    with app.app_context():
        nurse = user_model.get_user_by_id(nurse_id)
        assert nurse["is_suspended"] == 0 and nurse["status"] == "approved"
        assert nurse["failed_login_attempts"] == 0
        signed_in, error = authenticate("nurse@example.com", "Password123!")
        assert signed_in["id"] == nurse_id and error is None
        event = get_db().execute(
            "SELECT severity FROM audit_log WHERE action = ?",
            (f"Staff account reactivated: EMP-{nurse_id:05d}",),
        ).fetchone()
        assert event and event["severity"] == "Warning"


def test_admin_cannot_suspend_self_or_last_active_admin(app):
    self_admin_id = add_user(app, "self@example.com", role="medical_officer")
    client = app.test_client()
    active_session(client, self_admin_id)
    response = client.post(f"/admin/data-management/EMP-{self_admin_id:05d}/suspend")
    assert response.status_code == 302
    with app.app_context():
        assert user_model.get_user_by_id(self_admin_id)["is_suspended"] == 0
        get_db().execute(
            "UPDATE users SET status = 'rejected' WHERE id = ?",
            (self_admin_id,),
        )
        get_db().commit()

    actor_id = add_user(app, "inactive-admin@example.com", role="medical_officer", status="rejected")
    target_id = add_user(app, "last-admin@example.com", role="medical_officer")
    with app.app_context():
        get_db().execute(
            "UPDATE users SET status = 'rejected' WHERE role = ? AND id != ?",
            ("medical_officer", target_id),
        )
        get_db().commit()
    active_session(client, actor_id)
    response = client.post(f"/admin/data-management/EMP-{target_id:05d}/suspend")
    assert response.status_code == 302
    with app.app_context():
        assert user_model.get_user_by_id(target_id)["is_suspended"] == 0


def test_health_worker_cannot_unlock_suspend_or_reactivate(app):
    nurse_id = add_user(app, "nurse@example.com")
    target_id = add_user(app, "target@example.com")
    with app.app_context():
        max_attempts = settings_model.get_max_login_attempts()
    set_login_state(app, target_id, "recovery", max_attempts)
    with app.app_context():
        user_model.set_suspended(target_id, True)
    client = app.test_client()
    active_session(client, nurse_id, "health_worker")

    for action in ("unlock", "suspend", "reactivate"):
        response = client.post(f"/admin/data-management/EMP-{target_id:05d}/{action}")
        assert response.status_code == 403


def test_staff_records_distinguish_lock_recovery_and_suspension(app):
    recovery_id = add_user(app, "recovery@example.com")
    locked_id = add_user(app, "locked@example.com")
    suspended_id = add_user(app, "suspended@example.com")
    set_login_state(app, recovery_id, "recovery", 1)
    with app.app_context():
        max_attempts = settings_model.get_max_login_attempts()
    set_login_state(app, locked_id, "recovery", max_attempts)
    with app.app_context():
        user_model.set_suspended(suspended_id, True)
        records = {row["email"]: row for row in user_model.get_staff_records()}
    assert records["recovery@example.com"]["is_password_recovery"] is True
    assert records["recovery@example.com"]["is_locked"] is False
    assert records["locked@example.com"]["is_locked"] is True
    assert records["locked@example.com"]["is_password_recovery"] is True
    assert records["suspended@example.com"]["status"] == "Suspended"


def test_suspension_migration_applies_to_fresh_and_existing_databases(app, tmp_path):
    with app.app_context():
        columns = {row["name"] for row in get_db().execute("PRAGMA table_info(users)")}
        assert "is_suspended" in columns
        assert get_db().execute(
            "SELECT 1 FROM schema_migrations WHERE filename = ?",
            ("0029_add_is_suspended_to_users.sql",),
        ).fetchone() is not None

    existing_path = tmp_path / "existing.sqlite3"
    conn = sqlite3.connect(existing_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, status TEXT)")
    conn.execute("CREATE TABLE schema_migrations (filename TEXT PRIMARY KEY)")
    for migration in app_db.migration_files():
        if migration.name != "0029_add_is_suspended_to_users.sql":
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (migration.name,))
    conn.commit()
    assert app_db.run_migrations(conn) == ["0029_add_is_suspended_to_users.sql"]
    column = conn.execute("PRAGMA table_info(users)").fetchall()
    suspended_column = next(row for row in column if row["name"] == "is_suspended")
    assert suspended_column["notnull"] == 1 and suspended_column["dflt_value"] == "0"
    conn.close()