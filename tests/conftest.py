from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_connection
from app.models import user as user_model
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = type(
        "C",
        (Config,),
        {
            "DATABASE": str(tmp_path / "app.sqlite3"),
            "TESTING": True,
            "REQUIRE_ADMIN_APPROVAL": True,
            "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"),
        },
    )
    return create_app(cfg)


def add_user(app, email, role="medical_officer", password="Password123!"):
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
        conn.close()
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
