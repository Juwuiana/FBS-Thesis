import os
import sys

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.db import get_db
from app.controllers.auth_controller import authenticate
from app.models import user as user_model
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = type(
        "C",
        (Config,),
        {
            "DATABASE": str(tmp_path / "recovery.sqlite3"),
            "TESTING": True,
            "REQUIRE_ADMIN_APPROVAL": True,
        },
    )
    return create_app(cfg)


def add_user(app, email, role="health_worker", status="approved", password="OldPassword123!"):
    with app.app_context():
        return user_model.create_user(
            {
                "first_name": "Test",
                "middle_name": None,
                "last_name": "Employee",
                "birthday": "1990-01-01",
                "sex": "female",
                "email": email,
                "phone": "9171234567",
                "role": role,
                "facility": "lhui",
                "barangay": "aplaya",
            },
            generate_password_hash(password),
            status=status,
        )


def login_as_admin(client, user_id=1):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["user_role"] = "medical_officer"
        session["user_name"] = "Test Admin"
        session["security_version"] = 1


def test_forgot_password_sets_approved_account_to_recovery(app):
    add_user(app, "nurse@example.com")
    client = app.test_client()

    response = client.post("/forgot-password", data={"email": "nurse@example.com"})

    assert response.status_code == 200
    assert b"If that email is registered, an administrator has been notified." in response.data
    with app.app_context():
        assert user_model.get_user_by_email("nurse@example.com")["status"] == "recovery"
        assert get_db().execute(
            "SELECT action FROM audit_log WHERE action = 'Password recovery requested'"
        ).fetchone() is not None


def test_login_is_blocked_while_account_is_in_recovery(app):
    add_user(app, "nurse@example.com", status="recovery")

    with app.app_context():
        user, error = authenticate("nurse@example.com", "OldPassword123!")

    assert user is None
    assert error == "Your account is awaiting a password reset from an administrator."


def test_admin_reset_regenerates_password_and_approves_account(app):
    admin_id = add_user(app, "admin@example.com", role="medical_officer")
    employee_id = add_user(app, "nurse@example.com", status="recovery")
    client = app.test_client()
    login_as_admin(client, admin_id)

    response = client.post(f"/admin/staff/EMP-{employee_id:05d}/reset-password")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["name"] == "Test Employee"
    assert payload["email"] == "nurse@example.com"
    assert len(payload["temp_password"]) == 10
    with app.app_context():
        employee = user_model.get_user_by_id(employee_id)
        assert employee["status"] == "approved"
        assert employee["password_hash"] != "OldPassword123!"
        assert check_password_hash(employee["password_hash"], payload["temp_password"])
        assert get_db().execute(
            "SELECT action FROM audit_log WHERE action = ?",
            ("Password reset for nurse@example.com (recovery request)",),
        ).fetchone() is not None


def test_non_recovery_employee_cannot_be_reset(app):
    admin_id = add_user(app, "admin@example.com", role="medical_officer")
    employee_id = add_user(app, "nurse@example.com", status="approved")
    client = app.test_client()
    login_as_admin(client, admin_id)

    response = client.post(f"/admin/staff/EMP-{employee_id:05d}/reset-password")

    assert response.status_code == 400
    with app.app_context():
        assert user_model.get_user_by_id(employee_id)["status"] == "approved"
