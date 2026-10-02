import os
import sys

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.db import get_db
from app.models import lookup_model, user as user_model
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = type(
        "C",
        (Config,),
        {
            "DATABASE": str(tmp_path / "staff-edit.sqlite3"),
            "TESTING": True,
            "REQUIRE_ADMIN_APPROVAL": True,
        },
    )
    return create_app(cfg)


def add_user(app, email, role="medical_officer"):
    with app.app_context():
        barangay_id = lookup_model.get_or_create_barangay(
            "0403428001",
            "Aplaya",
            "0403428000",
            "City of Santa Rosa",
            "0400000000",
            "Region IV-A (CALABARZON)",
        )
        return user_model.create_user(
            {
                "first_name": "Test",
                "middle_name": None,
                "last_name": "User",
                "birthday": "1990-01-01",
                "sex": "female",
                "email": email,
                "phone": "9171234567",
                "role": role,
                "facility": "lhui",
                "barangay": "aplaya",
                "barangay_id": barangay_id,
            },
            generate_password_hash("OldPassword123!"),
            status="approved",
        )


def login(client, user_id, role="medical_officer"):
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["user_role"] = role
        session["user_name"] = "Test User"
        session["security_version"] = 1


def valid_details(**overrides):
    data = {
        "role": "LHU Nurse",
        "contact": "09181234567",
        "station": "LHU II",
        "region_code": "0400000000",
        "region_name": "Region IV-A (CALABARZON)",
        "city_code": "0403428000",
        "city_name": "City of Santa Rosa",
        "barangay_code": "0403428002",
        "barangay_name": "Balibago",
    }
    data.update(overrides)
    return data


def test_staff_view_renders_avatar_and_initials_fallback(app):
    avatar_id = add_user(app, "avatar@example.com")
    plain_id = add_user(app, "plain@example.com")
    with app.app_context():
        user_model.update_avatar(avatar_id, "staff-photo.png")

    client = app.test_client()
    login(client, avatar_id)
    avatar_response = client.get(f"/admin/data-management/EMP-{avatar_id:05d}/view")
    assert b"uploads/avatars/staff-photo.png" in avatar_response.data
    assert b"onerror=" in avatar_response.data

    fallback_response = client.get(f"/admin/data-management/EMP-{plain_id:05d}/view")
    assert b"staff-profile-avatar-fallback" in fallback_response.data
    assert b">TU</div>" in fallback_response.data


def test_admin_updates_staff_details_and_audits_masked_phone(app):
    admin_id = add_user(app, "admin@example.com")
    employee_id = add_user(app, "employee@example.com", role="health_worker")
    client = app.test_client()
    login(client, admin_id)

    response = client.post(
        f"/admin/data-management/EMP-{employee_id:05d}/update-details",
        data=valid_details(),
    )

    assert response.status_code == 302
    with app.app_context():
        employee = user_model.get_user_by_id(employee_id)
        assert employee["phone"] == "9181234567"
        assert employee["facility"] == "lhuii"
        assert employee["role"] == "health_worker"
        assert employee["barangay_id"] == lookup_model.get_barangay_id_by_code("0403428002")
        audit = get_db().execute(
            "SELECT action, severity FROM audit_log WHERE action LIKE '%Staff details changed%'"
        ).fetchone()
        assert audit is not None
        assert audit["severity"] == "Warning"
        assert "917****567" in audit["action"]
        assert "918****567" in audit["action"]
        assert "9171234567" not in audit["action"]
        assert f"EMP-{employee_id:05d}" in audit["action"]


def test_admin_updates_role_with_other_staff_details_and_audits_change(app):
    admin_id = add_user(app, "admin@example.com")
    employee_id = add_user(app, "employee@example.com", role="health_worker")
    client = app.test_client()
    login(client, admin_id)

    response = client.post(
        f"/admin/data-management/EMP-{employee_id:05d}/update-details",
        data=valid_details(role="Health Officer"),
    )

    assert response.status_code == 302
    with app.app_context():
        employee = user_model.get_user_by_id(employee_id)
        assert employee["role"] == "medical_officer"
        assert employee["phone"] == "9181234567"
        assert employee["facility"] == "lhuii"
        assert employee["barangay_id"] == lookup_model.get_barangay_id_by_code("0403428002")
        audit = get_db().execute(
            "SELECT action FROM audit_log WHERE action LIKE '%Staff details changed%'"
        ).fetchone()
        assert audit is not None
        assert "Role: LHU Nurse -> Health Officer" in audit["action"]
        role_audit = get_db().execute(
            "SELECT action FROM audit_log WHERE action LIKE 'Role changed:%'"
        ).fetchone()
        assert role_audit["action"] == (
            f"Role changed: LHU Nurse -> Health Officer (user: EMP-{employee_id:05d})"
        )


def test_invalid_role_is_rejected_without_changing_staff_details(app):
    admin_id = add_user(app, "admin@example.com")
    employee_id = add_user(app, "employee@example.com", role="health_worker")
    client = app.test_client()
    login(client, admin_id)

    response = client.post(
        f"/admin/data-management/EMP-{employee_id:05d}/update-details",
        data=valid_details(role="Administrator"),
    )

    assert response.status_code == 302
    with app.app_context():
        employee = user_model.get_user_by_id(employee_id)
        assert employee["role"] == "health_worker"
        assert employee["phone"] == "9171234567"
        assert employee["facility"] == "lhui"


@pytest.mark.parametrize(
    "overrides",
    [
        {"contact": "123"},
        {"station": "Invalid Station"},
        {"barangay_code": "", "barangay_name": ""},
    ],
    ids=["invalid-phone", "invalid-station", "unresolved-barangay"],
)
def test_invalid_staff_details_are_rejected_without_changes(app, overrides):
    admin_id = add_user(app, "admin@example.com")
    employee_id = add_user(app, "employee@example.com", role="health_worker")
    client = app.test_client()
    login(client, admin_id)

    response = client.post(
        f"/admin/data-management/EMP-{employee_id:05d}/update-details",
        data=valid_details(**overrides),
    )

    assert response.status_code == 302
    with app.app_context():
        employee = user_model.get_user_by_id(employee_id)
        assert employee["phone"] == "9171234567"
        assert employee["facility"] == "lhui"
        assert employee["barangay_id"] == lookup_model.get_barangay_id_by_code("0403428001")
        assert get_db().execute(
            "SELECT 1 FROM audit_log WHERE action LIKE '%Staff details changed%'"
        ).fetchone() is None


def test_health_worker_cannot_update_staff_details(app):
    nurse_id = add_user(app, "nurse@example.com", role="health_worker")
    employee_id = add_user(app, "employee@example.com", role="health_worker")
    client = app.test_client()
    login(client, nurse_id, "health_worker")

    response = client.post(
        f"/admin/data-management/EMP-{employee_id:05d}/update-details",
        data=valid_details(),
    )

    assert response.status_code == 403


def test_admin_cannot_change_own_role(app):
    admin_id = add_user(app, "admin@example.com")
    client = app.test_client()
    login(client, admin_id)

    response = client.post(
        f"/admin/data-management/EMP-{admin_id:05d}/update-details",
        data=valid_details(role="LHU Nurse"),
    )

    assert response.status_code == 302
    with app.app_context():
        assert user_model.get_user_by_id(admin_id)["role"] == "medical_officer"
    assert b"You cannot change your own role." in client.get(
        f"/admin/data-management/EMP-{admin_id:05d}", follow_redirects=True
    ).data


def test_last_active_admin_cannot_be_demoted(app):
    actor_id = add_user(app, "actor@example.com", role="health_worker")
    admin_id = add_user(app, "last-admin@example.com", role="medical_officer")
    with app.app_context():
        get_db().execute(
            "UPDATE users SET status = 'rejected' WHERE role = ? AND id != ?",
            ("medical_officer", admin_id),
        )
        get_db().commit()
    client = app.test_client()
    login(client, actor_id)

    response = client.post(
        f"/admin/data-management/EMP-{admin_id:05d}/update-details",
        data=valid_details(role="LHU Nurse"),
    )

    assert response.status_code == 302
    with app.app_context():
        assert user_model.get_user_by_id(admin_id)["role"] == "medical_officer"
    assert b"The last active Health Officer cannot be demoted." in client.get(
        f"/admin/data-management/EMP-{admin_id:05d}", follow_redirects=True
    ).data


def test_reset_password_is_available_from_edit_page(app):
    admin_id = add_user(app, "admin@example.com")
    employee_id = add_user(app, "recovery@example.com", role="health_worker")
    with app.app_context():
        get_db().execute(
            "UPDATE users SET status = ? WHERE id = ?", ("recovery", employee_id)
        )
        get_db().commit()
    client = app.test_client()
    login(client, admin_id)

    edit_page = client.get(f"/admin/data-management/EMP-{employee_id:05d}")
    assert b"reset-password-btn" in edit_page.data
    assert f"/admin/staff/EMP-{employee_id:05d}/reset-password".encode() in edit_page.data
    assert b"resetPasswordModal" in edit_page.data

    response = client.post(f"/admin/staff/EMP-{employee_id:05d}/reset-password")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["temp_password"]
    assert payload["email"] == "recovery@example.com"
    assert payload["name"] == "Test User"


def test_non_admin_cannot_reset_staff_password(app):
    nurse_id = add_user(app, "nurse@example.com", role="health_worker")
    employee_id = add_user(app, "recovery@example.com", role="health_worker")
    with app.app_context():
        get_db().execute(
            "UPDATE users SET status = ? WHERE id = ?", ("recovery", employee_id)
        )
        get_db().commit()
    client = app.test_client()
    login(client, nurse_id, role="health_worker")

    response = client.post(f"/admin/staff/EMP-{employee_id:05d}/reset-password")

    assert response.status_code == 403