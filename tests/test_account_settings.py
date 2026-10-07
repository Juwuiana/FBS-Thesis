import io
import os
import sys

from conftest import issue_token
import pytest
from werkzeug.security import check_password_hash, generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.controllers.auth_controller import authenticate
from app.db import get_db
from app.models import user as user_model
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = type(
        "C",
        (Config,),
        {
            "DATABASE": str(tmp_path / "settings.sqlite3"),
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "REQUIRE_ADMIN_APPROVAL": True,
        },
    )
    return create_app(cfg)


def add_user(app, email, role="medical_officer", password="OldPassword123!"):
    with app.app_context():
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
            },
            generate_password_hash(password),
            status="approved",
        )


def login(client, user_id, role):
    with client.session_transaction() as session:
        session["session_token"] = issue_token(client, user_id)
        session["user_id"] = user_id
        session["user_role"] = role
        session["user_name"] = "Test User"
        session["security_version"] = 1


def test_admin_change_password_rejects_wrong_current_password(app):
    user_id = add_user(app, "admin@example.com")
    client = app.test_client()
    login(client, user_id, "medical_officer")

    response = client.post(
        "/admin/privacy-security/change-password",
        data={
            "current_password": "WrongPassword123!",
            "new_password": "NewPassword123!",
            "confirm_password": "NewPassword123!",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        assert check_password_hash(
            user_model.get_user_by_id(user_id)["password_hash"], "OldPassword123!"
        )


def test_nurse_change_password_rejects_mismatched_confirmation(app):
    user_id = add_user(app, "nurse@example.com", role="health_worker")
    client = app.test_client()
    login(client, user_id, "health_worker")

    response = client.post(
        "/nurse/privacy_security/change-password",
        data={
            "current_password": "OldPassword123!",
            "new_password": "NewPassword123!",
            "confirm_password": "DifferentPassword123!",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        assert check_password_hash(
            user_model.get_user_by_id(user_id)["password_hash"], "OldPassword123!"
        )


def test_change_password_succeeds_logs_audit_and_invalidates_old_password(app):
    user_id = add_user(app, "admin@example.com")
    client = app.test_client()
    login(client, user_id, "medical_officer")

    response = client.post(
        "/admin/privacy-security/change-password",
        data={
            "current_password": "OldPassword123!",
            "new_password": "NewPassword123!",
            "confirm_password": "NewPassword123!",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        user_model.clear_session(user_id)
        old_user, old_error = authenticate("admin@example.com", "OldPassword123!")
        new_user, new_error = authenticate("admin@example.com", "NewPassword123!")
        assert old_user is None and old_error == "Invalid email or password."
        assert new_user is not None and new_error is None
        assert get_db().execute(
            "SELECT 1 FROM audit_log WHERE user_id = ? AND action = 'Password changed'",
            (user_id,),
        ).fetchone() is not None


def test_avatar_upload_accepts_image_and_rejects_invalid_or_oversized_files(app, tmp_path):
    user_id = add_user(app, "admin@example.com")
    app.static_folder = str(tmp_path / "static")
    client = app.test_client()
    login(client, user_id, "medical_officer")

    valid = client.post(
        "/profile/avatar",
        data={"avatar": (io.BytesIO(b"fake image data"), "profile.png")},
        content_type="multipart/form-data",
    )
    assert valid.status_code == 302
    with app.app_context():
        assert user_model.get_user_by_id(user_id)["avatar_filename"] == f"user_{user_id}.png"
    assert (tmp_path / "static" / "uploads" / "avatars" / f"user_{user_id}.png").exists()

    wrong_type = client.post(
        "/profile/avatar",
        data={"avatar": (io.BytesIO(b"not an image"), "profile.txt")},
        content_type="multipart/form-data",
    )
    assert wrong_type.status_code == 302

    oversized = client.post(
        "/profile/avatar",
        data={"avatar": (io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "large.png")},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 302
