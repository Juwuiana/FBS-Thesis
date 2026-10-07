import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_connection
from app.models import patient_model, user as user_model
from config import Config

PASSWORD = "Password123!"
META_TOKEN = re.compile(rb'<meta name="csrf-token" content="([^"]+)"')
FORM_TOKEN = re.compile(rb'name="csrf_token" value="([^"]+)"')


@pytest.fixture
def app(tmp_path):
    config = type("CsrfTestConfig", (Config,), {
        "DATABASE": str(tmp_path / "csrf.sqlite3"),
        "TESTING": True,
        "WTF_CSRF_ENABLED": True,
        "DEMO_MODE": True,
        "REQUIRE_ADMIN_APPROVAL": True,
        "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"),
    })
    return create_app(config)


def _add_user(app, email, role):
    with app.app_context():
        return user_model.create_user(
            {
                "first_name": "Test", "middle_name": None, "last_name": "User",
                "birthday": "1990-01-01", "sex": "female", "email": email,
                "phone": "9171234567", "role": role, "facility": "lhui", "barangay": "aplaya",
            },
            generate_password_hash(PASSWORD),
            status="approved",
        )


def _add_patient(app):
    with app.app_context():
        conn = get_connection()
        barangay_id = conn.execute("SELECT id FROM barangays ORDER BY id LIMIT 1").fetchone()[0]
        patient_id = conn.execute(
            "INSERT INTO patients (patient_code,last_name,first_name,birthdate,sex,barangay_id,password_hash,must_change_password) "
            "VALUES ('PATIENT-2026-0001', 'Portal', 'Patient', '1990-01-01', 'Female', ?, ?, 0)",
            (barangay_id, generate_password_hash(PASSWORD)),
        ).lastrowid
        conn.commit()
        conn.close()
        return patient_id


def _staff_client(app, role):
    user_id = _add_user(app, f"{role}@example.com", role)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update({
            "user_id": user_id, "user_role": role,
            "user_name": "Test User", "security_version": 1,
        })
    return client


def _meta_token(client, path):
    response = client.get(path)
    assert response.status_code == 200
    match = META_TOKEN.search(response.data)
    assert match is not None
    return match.group(1).decode()


def test_get_is_not_affected_by_csrf(app):
    assert app.test_client().get("/login").status_code == 200


def test_login_post_without_or_with_bad_token_is_rejected(app):
    client = app.test_client()
    data = {"email": "x@example.com", "password": "nope"}
    response = client.post("/login", data=data)
    assert response.status_code == 400
    assert b"This page has expired" in response.data
    assert b"Go back" in response.data
    assert client.post("/login", data={**data, "csrf_token": "forged"}).status_code == 400


@pytest.mark.parametrize("path", ["/login", "/signup", "/forgot-password"])
def test_auth_forms_validate_for_anonymous_users(app, path):
    client = app.test_client()
    rejected = client.post(path, data={})
    assert rejected.status_code == 400 and b"This page has expired" in rejected.data
    token = FORM_TOKEN.search(client.get(path).data).group(1).decode()
    assert b"This page has expired" not in client.post(path, data={"csrf_token": token}).data


def test_login_succeeds_and_token_is_fresh_after_session_clear(app):
    _add_user(app, "login@example.com", "medical_officer")
    client = app.test_client()
    old_token = FORM_TOKEN.search(client.get("/login").data).group(1).decode()
    response = client.post(
        "/login",
        data={"csrf_token": old_token, "email": "login@example.com", "password": PASSWORD},
    )
    assert response.status_code == 302

    new_token = _meta_token(client, "/admin/privacy-security")
    assert new_token != old_token
    url = "/admin/privacy-security/session-timeout"
    assert client.post(url, data={"csrf_token": new_token}).status_code != 400
    assert client.post(url, data={"csrf_token": old_token}).status_code == 400


def test_admin_post_requires_token(app):
    client = _staff_client(app, "medical_officer")
    url = "/admin/privacy-security/session-timeout"
    assert client.post(url, data={}).status_code == 400
    token = _meta_token(client, "/admin/privacy-security")
    assert client.post(url, data={"csrf_token": token}).status_code != 400


def test_nurse_post_requires_token(app):
    client = _staff_client(app, "health_worker")
    url = "/nurse/data_management/recalculate_pending"
    assert client.post(url, data={}).status_code == 400
    token = _meta_token(client, "/nurse/dashboard")
    assert client.post(url, data={"csrf_token": token}).status_code != 400


def test_patient_post_requires_token(app):
    patient_id = _add_patient(app)
    with app.app_context():
        state = patient_model.get_session_state(patient_id)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update({"patient_id": patient_id, "security_version": 1, "patient_sv": state["session_version"]})
    assert client.post("/patient_logout", data={}).status_code == 400
    token = _meta_token(client, "/patient_settings")
    assert client.post("/patient_logout", data={"csrf_token": token}).status_code == 302


def test_metrics_api_returns_json_error_and_accepts_header(app):
    client = _staff_client(app, "medical_officer")
    url = "/api/v1/green/demo/disconnect"
    response = client.post(url, json={})
    assert response.status_code == 400
    assert response.get_json() == {"error": "csrf"}

    token = _meta_token(client, "/admin/privacy-security")
    response = client.post(url, json={}, headers={"X-CSRFToken": token})
    assert response.status_code == 200


def test_nurse_json_api_accepts_fetch_style_header(app):
    client = _staff_client(app, "health_worker")
    response = client.post("/api/patients", json={})
    assert response.status_code == 400
    assert response.get_json() == {"error": "csrf"}

    token = _meta_token(client, "/nurse/dashboard")
    response = client.post("/api/patients", json={}, headers={"X-CSRFToken": token})
    assert not (response.status_code == 400 and response.get_json() == {"error": "csrf"})


def test_every_form_on_admin_privacy_page_has_a_token(app):
    client = _staff_client(app, "medical_officer")
    html = client.get("/admin/privacy-security").data.decode()
    post_forms = [
        body for tag, body in re.findall(r"(<form\b[^>]*>)(.*?)</form>", html, re.S | re.I)
        if re.search(r'method="post"', tag, re.I)
    ]
    assert post_forms
    assert all('name="csrf_token"' in body for body in post_forms)


def test_layouts_load_csrf_helper_before_other_scripts(app):
    client = _staff_client(app, "medical_officer")
    html = client.get("/admin/privacy-security").data.decode()
    helper = html.index("js/csrf.js")
    for other in ("js/main.js", "bootstrap.bundle.min.js"):
        assert helper < html.index(other)
