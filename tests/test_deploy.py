import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.db import get_connection
from conftest import active_session
from config import Config

ROOT = Path(__file__).resolve().parent.parent
ADMIN_PASSWORD = "Bootstrap-Pass-123"


def build_app(tmp_path, **overrides):
    cfg = type(
        "C",
        (Config,),
        {
            "DATABASE": str(tmp_path / "app.sqlite3"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SEED_DEMO": False,
            "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"),
            **overrides,
        },
    )
    return create_app(cfg)


def subdir(tmp_path, name):
    path = tmp_path / name
    path.mkdir()
    return path


def user_rows(app):
    with app.app_context():
        conn = get_connection()
        try:
            return conn.execute("SELECT * FROM users").fetchall()
        finally:
            conn.close()


def test_no_demo_accounts_unless_flag_is_on(tmp_path):
    assert user_rows(build_app(tmp_path)) == []


def test_demo_accounts_seed_only_with_explicit_flag(tmp_path):
    assert len(user_rows(build_app(tmp_path, SEED_DEMO=True))) == 3


def test_admin_bootstrap_creates_one_approved_officer(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("FBS_ADMIN_EMAIL", "Boss@Example.com")
    monkeypatch.setenv("FBS_ADMIN_PASSWORD", ADMIN_PASSWORD)
    with caplog.at_level(logging.DEBUG):
        app = build_app(tmp_path)

    rows = user_rows(app)
    assert len(rows) == 1
    admin = rows[0]
    assert admin["email"] == "boss@example.com"
    assert admin["role"] == "medical_officer" and admin["status"] == "approved"
    assert admin["barangay_id"] is not None
    assert admin["password_hash"] != ADMIN_PASSWORD
    assert ADMIN_PASSWORD not in caplog.text

    client = app.test_client()
    response = client.post("/login", data={"email": "boss@example.com", "password": ADMIN_PASSWORD})
    assert response.status_code == 302


def test_admin_bootstrap_is_noop_when_short_password_missing_env_or_users_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("FBS_ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("FBS_ADMIN_PASSWORD", "short")
    assert user_rows(build_app(tmp_path / "a")) == [] if (tmp_path / "a").mkdir() is None else True

    monkeypatch.delenv("FBS_ADMIN_EMAIL")
    monkeypatch.setenv("FBS_ADMIN_PASSWORD", ADMIN_PASSWORD)
    (tmp_path / "b").mkdir()
    assert user_rows(build_app(tmp_path / "b")) == []

    monkeypatch.setenv("FBS_ADMIN_EMAIL", "boss@example.com")
    (tmp_path / "c").mkdir()
    app = build_app(tmp_path / "c", SEED_DEMO=True)
    assert len(user_rows(app)) == 3


def run_config(env):
    clean = {k: v for k, v in os.environ.items() if k not in ("FBS_ENV", "SECRET_KEY")}
    return subprocess.run(
        [sys.executable, "-c", "import config; print(config.Config.SESSION_COOKIE_SECURE)"],
        cwd=ROOT, env={**clean, **env}, capture_output=True, text=True,
    )


@pytest.mark.parametrize("secret", [None, "", "dev-insecure-key-change-in-.env"])
def test_production_refuses_missing_or_default_secret(secret):
    env = {"FBS_ENV": "production"}
    if secret is not None:
        env["SECRET_KEY"] = secret
    result = run_config(env)
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_production_with_real_secret_uses_secure_cookie():
    result = run_config({"FBS_ENV": "production", "SECRET_KEY": "x" * 64})
    assert result.returncode == 0 and result.stdout.strip() == "True"
    assert run_config({}).stdout.strip() == "False"


def test_production_app_is_wrapped_in_proxyfix(tmp_path):
    app = build_app(tmp_path, IS_PRODUCTION=True)
    assert isinstance(app.wsgi_app, ProxyFix)
    assert not isinstance(build_app(subdir(tmp_path, "dev")).wsgi_app, ProxyFix)


def test_security_headers_are_set(tmp_path):
    response = build_app(tmp_path).test_client().get("/login")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_avatars_are_served_from_upload_dir_to_signed_in_users_only(tmp_path):
    app = build_app(tmp_path, SEED_DEMO=True)
    avatar_dir = Path(app.config["AVATAR_DIR"])
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "user_1.png").write_bytes(b"\x89PNG fake")
    assert avatar_dir == tmp_path / "uploads" / "avatars"

    anonymous = app.test_client()
    assert anonymous.get("/profile/avatar/user_1.png").status_code == 302

    client = app.test_client()
    active_session(client, 1)
    ok = client.get("/profile/avatar/user_1.png")
    assert ok.status_code == 200 and ok.data == b"\x89PNG fake"
    assert client.get("/profile/avatar/missing.png").status_code == 404
    assert client.get("/profile/avatar/..%2F..%2Fapp.sqlite3").status_code == 404
