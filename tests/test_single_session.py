from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_connection
from app.models import settings as settings_model, user as user_model
from config import Config

PASSWORD = "CorrectHorse123!"
NEW_PASSWORD = "BrandNewPass456!"


def make_app(tmp_path, policy="block"):
    cfg = type(
        "C",
        (Config,),
        {
            "DATABASE": str(tmp_path / "app.sqlite3"),
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SINGLE_SESSION_POLICY": policy,
            "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"),
        },
    )
    return create_app(cfg)


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path)


@pytest.fixture
def replace_app(tmp_path):
    return make_app(tmp_path, policy="replace")


def add_staff(app, email, role="health_worker"):
    with app.app_context():
        return user_model.create_user(
            {
                "first_name": "Test", "middle_name": None, "last_name": "User",
                "birthday": "1990-01-01", "sex": "female", "email": email,
                "phone": "9171234567", "role": role, "facility": "lhui",
                "barangay": "aplaya",
            },
            generate_password_hash(PASSWORD),
            status="approved",
        )


def login(client, email, password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def is_signed_in(client):
    return client.get("/nurse/dashboard").status_code == 200


def user_row(app, user_id):
    with app.app_context():
        conn = get_connection()
        try:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()


def age_last_seen(app, user_id, minutes):
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with app.app_context():
        conn = get_connection()
        conn.execute("UPDATE users SET active_session_last_seen = ? WHERE id = ?", (stamp, user_id))
        conn.commit()
        conn.close()


def test_second_login_is_rejected_and_first_session_keeps_working(app):
    add_staff(app, "nurse@example.com")
    a, b = app.test_client(), app.test_client()

    assert login(a, "nurse@example.com").status_code == 302
    response = login(b, "nurse@example.com")

    assert response.status_code == 401
    assert b"already signed in on another device" in response.data
    assert is_signed_in(a)
    assert not is_signed_in(b)


def test_logout_releases_the_account(app):
    add_staff(app, "nurse@example.com")
    a, b = app.test_client(), app.test_client()
    login(a, "nurse@example.com")

    a.get("/logout")

    assert login(b, "nurse@example.com").status_code == 302
    assert is_signed_in(b)


def test_stale_session_allows_login_and_signs_out_old_device(app):
    user_id = add_staff(app, "nurse@example.com")
    a, b = app.test_client(), app.test_client()
    login(a, "nurse@example.com")
    with app.app_context():
        minutes = settings_model.get_session_timeout_minutes()
    age_last_seen(app, user_id, minutes + 1)

    assert login(b, "nurse@example.com").status_code == 302

    response = a.get("/nurse/dashboard")
    assert response.status_code == 302 and "/login" in response.headers["Location"]
    assert is_signed_in(b)


def test_replace_policy_signs_out_the_older_device(replace_app):
    add_staff(replace_app, "nurse@example.com")
    a, b = replace_app.test_client(), replace_app.test_client()
    login(a, "nurse@example.com")

    assert login(b, "nurse@example.com").status_code == 302

    assert not is_signed_in(a)
    assert is_signed_in(b)


def test_signed_out_device_sees_message_and_api_gets_401(app):
    user_id = add_staff(app, "nurse@example.com")
    a = app.test_client()
    login(a, "nurse@example.com")
    with app.app_context():
        user_model.clear_session(user_id)

    api_client = app.test_client()
    with api_client.session_transaction() as session, a.session_transaction() as source:
        session.update(dict(source))
    assert api_client.get("/api/v1/anything").status_code == 401

    page = a.get("/nurse/dashboard", follow_redirects=True)
    assert b"signed in on another device" in page.data


def test_rejected_login_does_not_count_as_failed_attempt(app):
    user_id = add_staff(app, "nurse@example.com")
    a, b = app.test_client(), app.test_client()
    login(a, "nurse@example.com")

    for _ in range(10):
        assert login(b, "nurse@example.com").status_code == 401

    row = user_row(app, user_id)
    assert row["failed_login_attempts"] == 0
    assert not row["is_suspended"]


def test_wrong_password_on_active_account_gives_generic_error(app):
    add_staff(app, "nurse@example.com")
    a, b, c = app.test_client(), app.test_client(), app.test_client()
    login(a, "nurse@example.com")

    active = login(b, "nurse@example.com", "wrong-password")
    unknown = login(c, "nobody@example.com", "wrong-password")

    assert active.status_code == unknown.status_code == 401
    assert b"Invalid email or password." in active.data
    assert b"another device" not in active.data


def test_admin_force_signout_kicks_user_and_is_audited(app):
    admin_id = add_staff(app, "admin@example.com", role="medical_officer")
    nurse_id = add_staff(app, "nurse@example.com")
    admin, nurse = app.test_client(), app.test_client()
    login(admin, "admin@example.com")
    login(nurse, "nurse@example.com")

    response = admin.post(f"/admin/data-management/{nurse_id}/force-signout")

    assert response.status_code == 302
    assert user_row(app, nurse_id)["active_session_token"] is None
    assert not is_signed_in(nurse)
    with app.app_context():
        conn = get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action LIKE 'Staff session force signed out%'"
        ).fetchone()[0]
        conn.close()
    assert count == 1
    assert user_row(app, admin_id)["active_session_token"] is not None


def test_health_worker_cannot_force_signout(app):
    add_staff(app, "nurse@example.com")
    other_id = add_staff(app, "other@example.com")
    nurse, other = app.test_client(), app.test_client()
    login(nurse, "nurse@example.com")
    login(other, "other@example.com")

    response = nurse.post(f"/admin/data-management/{other_id}/force-signout")

    assert response.status_code == 403
    assert user_row(app, other_id)["active_session_token"] is not None


def test_password_reset_and_suspension_clear_the_token(app):
    user_id = add_staff(app, "nurse@example.com")
    with app.app_context():
        user_model.start_session(user_id)
        user_model.reset_password(user_id, generate_password_hash("TempPass123!"))
    assert user_row(app, user_id)["active_session_token"] is None

    with app.app_context():
        user_model.start_session(user_id)
        user_model.set_suspended(user_id, True)
    assert user_row(app, user_id)["active_session_token"] is None


def test_own_password_change_keeps_this_device_and_signs_out_others(app):
    add_staff(app, "nurse@example.com")
    a = app.test_client()
    login(a, "nurse@example.com")
    with app.app_context():
        user_id = user_model.get_user_by_email("nurse@example.com")["id"]
        old_token = user_model.get_active_session_state(user_id)["token"]

    response = a.post(
        "/nurse/privacy_security/change-password",
        data={"current_password": PASSWORD, "new_password": NEW_PASSWORD,
              "confirm_password": NEW_PASSWORD},
    )

    assert response.status_code in (200, 302)
    with app.app_context():
        assert user_model.get_active_session_state(user_id)["token"] != old_token
    assert is_signed_in(a)


def test_role_wide_force_signout_clears_tokens_but_keeps_requester(app):
    admin_id = add_staff(app, "admin@example.com", role="medical_officer")
    nurse_id = add_staff(app, "nurse@example.com")
    admin, nurse = app.test_client(), app.test_client()
    login(admin, "admin@example.com")
    login(nurse, "nurse@example.com")

    admin.post("/admin/privacy-security/role-force-signout", data={"role": "health_worker"})

    assert user_row(app, nurse_id)["active_session_token"] is None
    assert not is_signed_in(nurse)
    assert login(nurse, "nurse@example.com").status_code == 302
    assert user_row(app, admin_id)["active_session_token"] is not None
