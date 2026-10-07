from datetime import datetime, timezone

from conftest import issue_token
import pytest

from app import create_app
from app.db import get_connection
from config import Config


@pytest.fixture
def app(tmp_path):
    cfg = type("TestConfig", (Config,), {
        "DATABASE": str(tmp_path / "t.sqlite3"),
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "REQUIRE_ADMIN_APPROVAL": False,
        "BATTERY_SYSFS_DIR": str(tmp_path / "missing-battery"),
    })
    return create_app(cfg)


def _login(client):
    with client.session_transaction() as s:
        s["session_token"] = issue_token(client, 1)
        s["user_id"] = 1
        s["user_role"] = "health_worker"
        s["security_version"] = 1
        s["last_active"] = datetime.now(timezone.utc).isoformat()


def test_nurse_screening_submit_creates_and_links_green_log(app):
    with app.app_context():
        conn = get_connection()
        patient_id = conn.execute(
            """INSERT INTO patients
               (patient_code, last_name, first_name, birthdate, sex)
               VALUES ('GREEN-TEST', 'Test', 'Green', '1990-01-01', 'Male')"""
        ).lastrowid
        visit_id = conn.execute(
            """INSERT INTO visits (patient_id, visit_type, assessment_date)
               VALUES (?, 'intake', '2026-09-23')""",
            (patient_id,),
        ).lastrowid
        conn.commit()
        conn.close()

    client = app.test_client()
    _login(client)

    response = client.post(
        f"/nurse/screening/GREEN-TEST/{visit_id}/submit",
        data={
            "fbs_mg_dl": "131",
            "clinical_notes": "None", 
            "test_method": "Capillary (Fingerprick)",
            "test_datetime": "2026-09-23 01:00:00",
            "final_risk_level": "High",
            "fasted_ge_8h": "on",
            "identity_verified": "on",
            "glucometer_calibrated": "on",
            "capillary_sample_taken": "on",
            "consent_signed": "on",
            "result_recorded_within_5min": "on",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        conn = get_connection()
        log = conn.execute(
            """SELECT lab_screening_id, inference_latency_ms, energy_consumed_kwh,
                      carbon_emissions_kg, measurement_method
               FROM green_computing_log"""
        ).fetchone()
        screening = conn.execute(
            """SELECT id, model_predicted_risk_level, model_confidence
               FROM lab_screenings WHERE visit_id = ?""",
            (visit_id,),
        ).fetchone()
        assert log is not None
        assert log["lab_screening_id"] == screening["id"]
        assert log["inference_latency_ms"] >= 0
        assert log["energy_consumed_kwh"] >= 0
        assert log["carbon_emissions_kg"] >= 0
        assert log["measurement_method"] == "estimated"
        assert screening["model_predicted_risk_level"] == "Diabetic"
        assert screening["model_confidence"] == pytest.approx(0.5)
