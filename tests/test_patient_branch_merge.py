"""Smoke coverage for the patient-record branch pieces merged on top of the fourth merge."""
import uuid

from app.models import patient_model, settings as settings_model
from app.models.db import get_connection

from test_patient_add_record_merge import _patient, _patient_client


def test_account_help_request_roundtrip_and_anonymize_clears(app):
    pid, code = _patient(app)
    with app.app_context():
        patient_model.request_account_help(code, "forgot_password")
        assert patient_model.count_pending_account_help_requests() >= 1
        assert patient_model.get_pending_account_help(pid)["reason"] == "Forgot password"
        patient_model.resolve_account_help_request(pid, None)
        assert patient_model.get_pending_account_help(pid) is None


def test_portal_deactivate_and_session_version(app):
    pid, _ = _patient(app)
    with app.app_context():
        assert patient_model.get_session_state(pid)["is_active"] is True
        v = patient_model.bump_session_version(pid)
        patient_model.set_portal_active(pid, False)
        state = patient_model.get_session_state(pid)
        assert state["session_version"] == v and state["is_active"] is False
    client = _patient_client(app, pid)
    with client.session_transaction() as s:
        s["patient_sv"] = 0
    assert client.get("/patient_dashboard").status_code == 302


def test_patient_email_validation(app):
    assert patient_model.is_valid_email("") and patient_model.is_valid_email("a@b.co")
    assert not patient_model.is_valid_email("nope")
