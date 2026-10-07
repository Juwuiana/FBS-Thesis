from datetime import datetime, timedelta, timezone

import pytest

from app.db import get_db
from app.models import health_analytics_model, patient_auth_model, patient_model, patient_portal_model, settings as settings_model, visit_model
from app.models import green as green_model
from werkzeug.security import generate_password_hash


def _seed_patient(
    app,
    *,
    patient_code,
    created_days_ago=400,
    last_visit_days_ago=400,
    deleted_at=None,
    anonymized_at=None,
    consent_research=1,
    password_hash=None,
    with_related=True,
):
    with app.app_context():
        db = get_db()
        barangay_id = db.execute("SELECT id FROM barangays ORDER BY id LIMIT 1").fetchone()[0]
        created_at = (datetime.now(timezone.utc) - timedelta(days=created_days_ago)).strftime("%Y-%m-%d %H:%M:%S")
        patient_id = db.execute(
            """
            INSERT INTO patients (
                patient_code, last_name, first_name, middle_name,
                father_last_name, father_first_name, mother_last_name, mother_first_name,
                spouse_last_name, spouse_first_name, maiden_name, married_name,
                contact_number, birthdate, sex, civil_status, religion, occupation, education,
                barangay_id, address, phic_membership, phic_type, password_hash,
                portal_activated_at, credentials_issued_at, consent_research,
                created_at, deleted_at, anonymized_at
            ) VALUES (
                ?, 'Patient', 'Test', 'Middle', 'Father', 'First', 'Mother', 'First',
                'Spouse', 'First', 'Maiden', 'Married', '09171234567', '1990-05-14',
                'Male', 'Single', 'Test religion', 'Test occupation', 'College degree, post graduate',
                ?, '123 Test Street', 'Member', 'Member', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                ?, ?, ?, ?
            )
            """,
            (patient_code, barangay_id, password_hash, consent_research, created_at, deleted_at, anonymized_at),
        ).lastrowid
        if last_visit_days_ago is not None and with_related:
            assessed = (datetime.now(timezone.utc) - timedelta(days=last_visit_days_ago)).strftime("%Y-%m-%d")
            visit_id = db.execute(
                """
                INSERT INTO visits (
                    patient_id, visit_type, assessment_date, clinical_notes,
                    past_surgical_history, pe_skin, pe_heent, pe_chest, pe_heart,
                    pe_abdomen, pe_extremities, edited_by_patient_at, edited_fields,
                    patient_edit_previous_values
                ) VALUES (?, 'intake', ?, 'Patient name: Alice Example', 'Family history text',
                          'Skin note', 'HEENT note', 'Chest note', 'Heart note',
                          'Abdomen note', 'Extremities note', CURRENT_TIMESTAMP,
                          '["contact_number"]', '{"contact_number":"09171234567"}')
                """,
                (patient_id, assessed),
            ).lastrowid
            db.execute(
                """
                INSERT INTO lab_screenings (
                    visit_id, fbs_mg_dl, test_datetime, final_risk_level,
                    glucometer_id, referral_action, referred_to
                ) VALUES (?, 140, CURRENT_TIMESTAMP, 'High', 'GLUCO-IDENTIFIER',
                          'Referred; patient Alice Example', 'Example District Hospital')
                """,
                (visit_id,),
            )
            db.execute(
                "INSERT INTO cvd_responses (visit_id, q7_severe_pain_30min_plus) VALUES (?, 1)",
                (visit_id,),
            )
            db.execute(
                "INSERT INTO patient_login_events (patient_id, user_agent, ip_address) VALUES (?, 'Test Agent', '192.0.2.1')",
                (patient_id,),
            )
            db.execute(
                "INSERT INTO sync_queue_log (visit_id, offline_created_at, last_error) VALUES (?, CURRENT_TIMESTAMP, 'Sensitive error detail')",
                (visit_id,),
            )
        db.commit()
        return patient_id


def _admin_client(app, role="medical_officer"):
    client = app.test_client()
    with client.session_transaction() as session:
        session.update({
            "user_id": 1,
            "user_role": role,
            "user_name": "Test Admin",
            "security_version": 1,
            "patient_retention_selection_hash": "retention-page-token",
        })
    return client


def _page_selection_token(client):
    with client.session_transaction() as session:
        return session.get("patient_retention_selection_hash")


def _download_archive(client, patient_ids):
    return client.post(
        "/admin/privacy-security/patient-retention/action",
        data={
            "action": "export",
            "patient_ids": patient_ids,
            "selection_hash": _page_selection_token(client),
        },
    )


def _apply_retention(client, patient_ids, action="anonymize", **overrides):
    data = {
        "action": action,
        "patient_ids": patient_ids,
        "selection_hash": _page_selection_token(client),
        "confirmation_count": str(len(patient_ids)),
        "confirm_irreversible": "1",
    }
    data.update(overrides)
    return client.post("/admin/privacy-security/patient-retention/action", data=data, follow_redirects=True)


def _critical_retention_audits(app):
    with app.app_context():
        return get_db().execute(
            "SELECT action, severity FROM audit_log WHERE severity = 'Critical' AND action LIKE 'Patient retention %'"
        ).fetchall()


def test_patient_retention_setting_defaults_and_rejects_invalid_values(app):
    with app.app_context():
        assert settings_model.get_patient_retention_days() is None
        settings_model.set_patient_retention_days(365)
        assert settings_model.get_patient_retention_days() == 365
        with pytest.raises(ValueError):
            settings_model.set_patient_retention_days(90)


def test_due_query_uses_last_visit_or_created_at_and_respects_off(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        _seed_patient(app, patient_code="RET-OLD", last_visit_days_ago=400)
        _seed_patient(app, patient_code="RET-RECENT", last_visit_days_ago=30)
        _seed_patient(app, patient_code="RET-NO-VISITS", created_days_ago=500, last_visit_days_ago=None)
        _seed_patient(app, patient_code="RET-DELETED", last_visit_days_ago=500, deleted_at="2024-01-01 00:00:00")
        _seed_patient(app, patient_code="RET-ANON", last_visit_days_ago=500, anonymized_at="2024-01-01 00:00:00")

        assert patient_model.count_patients_due_for_retention() == 2
        assert {row["patient_code"] for row in patient_model.list_patients_due_for_retention(50, 0)} >= {"RET-OLD", "RET-NO-VISITS"}

        settings_model.set_patient_retention_days(None)
        assert patient_model.count_patients_due_for_retention() == 0


def test_export_archive_requires_session_hash_and_valid_selection(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        pid = _seed_patient(app, patient_code="RET-ARCHIVE", last_visit_days_ago=500)
        admin = app.test_client()
        with admin.session_transaction() as session:
            session["user_id"] = 1
            session["user_role"] = "medical_officer"
            session["user_name"] = "Admin"

        ids = [pid]
        response = admin.post(
            "/admin/privacy-security/patient-retention/action",
            data={"action": "export", "patient_ids": ids, "selection_hash": "bad-hash"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        row = get_db().execute("SELECT anonymized_at FROM patients WHERE id = ?", (pid,)).fetchone()
        assert row["anonymized_at"] is None

        assert patient_model.anonymize_patients_for_retention(ids) == 1
        row = get_db().execute("SELECT anonymized_at FROM patients WHERE id = ?", (pid,)).fetchone()
        assert row["anonymized_at"] is not None


def test_anonymize_scrubs_identity_and_free_text_but_keeps_screening_results(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        password_hash = generate_password_hash("PortalPassword123!")
        patient_id = _seed_patient(
            app, patient_code="RET-ANONYMIZE", last_visit_days_ago=500,
            password_hash=password_hash,
        )

    client = _admin_client(app)
    assert _download_archive(client, [patient_id]).status_code == 200
    response = _apply_retention(client, [patient_id], action="anonymize")
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        patient = db.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        assert patient["anonymized_at"] is not None
        assert patient["patient_code"] == f"ANON-{patient_id:010d}"
        assert db.execute(
            "SELECT COUNT(*) FROM patients WHERE patient_code = ?", (patient["patient_code"],)
        ).fetchone()[0] == 1
        for field in (
            "middle_name", "father_last_name", "father_first_name", "mother_last_name",
            "mother_first_name", "spouse_last_name", "spouse_first_name", "maiden_name",
            "married_name", "contact_number", "address", "religion", "occupation",
            "password_hash", "portal_activated_at", "credentials_issued_by_staff_id", "credentials_issued_at",
        ):
            assert patient[field] is None, field
        assert patient["last_name"] == patient["first_name"] == "ANONYMIZED"
        assert patient["birthdate"] == "1990-01-01"
        assert patient["sex"] == "Male"
        assert patient["civil_status"] == "Single"
        assert patient["education"] == "College degree, post graduate"
        assert patient["consent_research"] == 1

        visit = db.execute("SELECT * FROM visits WHERE patient_id = ?", (patient_id,)).fetchone()
        assert visit is not None
        for field in (
            "clinical_notes", "past_surgical_history", "pe_skin", "pe_heent", "pe_chest",
            "pe_heart", "pe_abdomen", "pe_extremities", "edited_fields", "patient_edit_previous_values",
        ):
            assert visit[field] is None, field
        lab = db.execute("SELECT * FROM lab_screenings WHERE visit_id = ?", (visit["id"],)).fetchone()
        assert lab is not None
        assert lab["fbs_mg_dl"] == 140
        assert lab["final_risk_level"] == "High"
        for field in ("glucometer_id", "referral_action", "referred_to"):
            assert lab[field] is None, field
        assert db.execute("SELECT COUNT(*) FROM cvd_responses WHERE visit_id = ?", (visit["id"],)).fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM patient_login_events WHERE patient_id = ?", (patient_id,)).fetchone()[0] == 0
        assert db.execute("SELECT last_error FROM sync_queue_log WHERE visit_id = ?", (visit["id"],)).fetchone()[0] is None
        assert patient_auth_model.authenticate_patient("RET-ANONYMIZE", "PortalPassword123!")[0] is None

        audits = _critical_retention_audits(app)
        assert len(audits) == 1
        assert "anonymize" in audits[0]["action"]
        assert "records=1" in audits[0]["action"]
        assert "RET-ANONYMIZE" in audits[0]["action"]


def test_anonymize_forces_delete_without_research_consent(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        patient_id = _seed_patient(app, patient_code="RET-NO-CONSENT", consent_research=0)

    client = _admin_client(app)
    assert _download_archive(client, [patient_id]).status_code == 200
    _apply_retention(client, [patient_id], action="anonymize")

    with app.app_context():
        assert get_db().execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is None
    audits = _critical_retention_audits(app)
    assert len(audits) == 1
    assert "anonymize" in audits[0]["action"]
    assert "deleted=1" in audits[0]["action"]
    assert "consent_forced_deletes=1" in audits[0]["action"]
    assert "RET-NO-CONSENT" in audits[0]["action"]


def test_anonymize_refuses_existing_generated_code_collision(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        patient_id = _seed_patient(app, patient_code="RET-CODE-COLLISION")
        colliding_id = _seed_patient(
            app, patient_code=f"ANON-{patient_id:010d}", last_visit_days_ago=30,
        )
    client = _admin_client(app)
    assert _download_archive(client, [patient_id]).status_code == 200

    _apply_retention(client, [patient_id], action="anonymize")

    with app.app_context():
        db = get_db()
        patient = db.execute("SELECT patient_code, anonymized_at FROM patients WHERE id = ?", (patient_id,)).fetchone()
        collision = db.execute("SELECT patient_code FROM patients WHERE id = ?", (colliding_id,)).fetchone()
        assert patient["patient_code"] == "RET-CODE-COLLISION"
        assert patient["anonymized_at"] is None
        assert collision["patient_code"] == f"ANON-{patient_id:010d}"
    assert _critical_retention_audits(app) == []


def test_delete_permanently_cascades_related_records_and_audits_once(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        patient_id = _seed_patient(app, patient_code="RET-DELETE")
        visit_id = get_db().execute(
            "SELECT id FROM visits WHERE patient_id = ?", (patient_id,)
        ).fetchone()["id"]

    client = _admin_client(app)
    assert _download_archive(client, [patient_id]).status_code == 200
    response = _apply_retention(client, [patient_id], action="delete")
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "patient_retention_archive_hash" not in session

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is None
        for table, column in (
            ("visits", "patient_id"),
            ("patient_login_events", "patient_id"),
        ):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (patient_id,)).fetchone()[0] == 0
        for table in ("lab_screenings", "cvd_responses", "sync_queue_log"):
            assert db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE visit_id = ?",
                (visit_id,),
            ).fetchone()[0] == 0
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

    audits = _critical_retention_audits(app)
    assert len(audits) == 1
    assert "delete" in audits[0]["action"]
    assert "records=1" in audits[0]["action"]
    assert "deleted=1" in audits[0]["action"]
    assert "RET-DELETE" in audits[0]["action"]


@pytest.mark.parametrize(
    ("mode", "trigger_sql"),
    [
        ("anonymize", "CREATE TRIGGER fail_retention BEFORE UPDATE OF anonymized_at ON patients WHEN OLD.id = {id} BEGIN SELECT RAISE(ABORT, 'forced failure'); END"),
        ("delete", "CREATE TRIGGER fail_retention BEFORE DELETE ON patients WHEN OLD.id = {id} BEGIN SELECT RAISE(ABORT, 'forced failure'); END"),
    ],
)
def test_retention_batch_rolls_back_every_record_and_skips_audit_on_failure(app, mode, trigger_sql):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        first_id = _seed_patient(app, patient_code=f"RET-ROLLBACK-{mode}-1")
        second_id = _seed_patient(app, patient_code=f"RET-ROLLBACK-{mode}-2")
        db = get_db()
        db.execute(trigger_sql.format(id=second_id))
        db.commit()

    client = _admin_client(app)
    ids = [first_id, second_id]
    assert _download_archive(client, ids).status_code == 200
    _apply_retention(client, ids, action=mode)

    with app.app_context():
        db = get_db()
        rows = db.execute(
            "SELECT id, patient_code, anonymized_at FROM patients WHERE id IN (?, ?) ORDER BY id",
            ids,
        ).fetchall()
        assert len(rows) == 2
        assert all(row["anonymized_at"] is None for row in rows)
        assert rows[0]["patient_code"] == f"RET-ROLLBACK-{mode}-1"
        assert db.execute("SELECT COUNT(*) FROM visits WHERE patient_id IN (?, ?)", ids).fetchone()[0] == 2
        db.execute("DROP TRIGGER fail_retention")
        db.commit()
    assert _critical_retention_audits(app) == []


@pytest.mark.parametrize(
    ("action", "overrides"),
    [
        ("anonymize", {"confirmation_count": "9"}),
        ("anonymize", {"confirm_irreversible": ""}),
        ("invalid", {}),
    ],
)
def test_retention_confirmation_and_action_are_enforced(app, action, overrides):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        patient_id = _seed_patient(app, patient_code="RET-INVALID-FORM")
    client = _admin_client(app)
    assert _download_archive(client, [patient_id]).status_code == 200

    _apply_retention(client, [patient_id], action=action, **overrides)
    with app.app_context():
        row = get_db().execute("SELECT anonymized_at FROM patients WHERE id = ?", (patient_id,)).fetchone()
        assert row["anonymized_at"] is None
    assert _critical_retention_audits(app) == []


def test_retention_apply_requires_download_for_exact_selection(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        first_id = _seed_patient(app, patient_code="RET-ARCHIVE-FIRST")
        second_id = _seed_patient(app, patient_code="RET-ARCHIVE-OTHER")
    client = _admin_client(app)
    _apply_retention(client, [first_id], action="anonymize")
    with app.app_context():
        row = get_db().execute("SELECT anonymized_at FROM patients WHERE id = ?", (first_id,)).fetchone()
        assert row["anonymized_at"] is None

    assert _download_archive(client, [first_id]).status_code == 200

    _apply_retention(client, [second_id], action="anonymize")
    with app.app_context():
        rows = get_db().execute(
            "SELECT anonymized_at FROM patients WHERE id IN (?, ?) ORDER BY id",
            (first_id, second_id),
        ).fetchall()
        assert all(row["anonymized_at"] is None for row in rows)
    assert _critical_retention_audits(app) == []


def test_retention_apply_refuses_non_admin_off_policy_not_due_and_over_500(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        patient_id = _seed_patient(app, patient_code="RET-REFUSAL")

    non_admin = _admin_client(app, role="health_worker")
    assert _download_archive(non_admin, [patient_id]).status_code == 403
    response = _apply_retention(non_admin, [patient_id])
    assert response.status_code == 403

    client = _admin_client(app)
    assert _download_archive(client, [patient_id]).status_code == 200
    too_many = [str(patient_id)] * 501
    response = client.post(
        "/admin/privacy-security/patient-retention/action",
        data={
            "action": "anonymize", "patient_ids": too_many,
            "selection_hash": _page_selection_token(client), "confirmation_count": "501",
            "confirm_irreversible": "1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    recent_id = _seed_patient(app, patient_code="RET-NOT-DUE", last_visit_days_ago=30)
    _download_archive(client, [recent_id])
    _apply_retention(client, [recent_id])

    with app.app_context():
        settings_model.set_patient_retention_days(None)
    _apply_retention(client, [patient_id])

    with app.app_context():
        rows = get_db().execute(
            "SELECT anonymized_at FROM patients WHERE id IN (?, ?) ORDER BY id",
            (patient_id, recent_id),
        ).fetchall()
        assert all(row["anonymized_at"] is None for row in rows)
    assert _critical_retention_audits(app) == []


def test_anonymized_patients_are_hidden_from_workflows_but_kept_in_analytics(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        patient_id = _seed_patient(app, patient_code="RET-VISIBILITY")
    client = _admin_client(app)
    _download_archive(client, [patient_id])
    _apply_retention(client, [patient_id], action="anonymize")

    with app.app_context():
        assert patient_model.get_patient_by_id(patient_id) is None
        assert patient_model.get_patient_by_code(f"ANON-{patient_id:010d}") is None
        assert patient_model.list_patients() == []
        assert patient_model.list_patients_with_latest_screening() == []
        assert "ANON-" not in patient_model.export_patients_csv()
        assert visit_model.list_pending_patient_edits() == []
        assert health_analytics_model.get_recent_registries() == []
        assert health_analytics_model.get_followup_summary() == {
            "no_action": 0, "overdue": 0, "awaiting_lab": 0,
        }
        assert health_analytics_model.get_followup_worklist() == []
        assert health_analytics_model.get_red_flags() == []
        assert health_analytics_model.get_fbs_distribution()["Diabetic (>=126)"] == 1
        assert health_analytics_model.get_risk_status_distribution()["High"] == 1
        assert health_analytics_model.get_age_distribution()["30-39"] == 1
        assert health_analytics_model.get_sex_distribution()["Male"] == 1
        assert health_analytics_model.get_hypertension_history_distribution()["No"] == 1
        assert len(health_analytics_model._screening_records()) == 1
        assert patient_portal_model.get_patient_dashboard_data(patient_id) == {"has_data": False, "visits": []}
        assert patient_portal_model.get_full_screening_history(patient_id) == []
        assert green_model.pending_sync(get_db(), 20, 0) == []
        assert green_model.recent_sync_rows(get_db(), 20) == []
        assert green_model.pending_counts(get_db())["patients"] == 0
        assert green_model.sync_rows_page(get_db(), "all", 20, 0)[1] == 0


def test_retention_review_page_has_delete_and_confirmation_controls(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        _seed_patient(app, patient_code="RET-PAGE")
    client = _admin_client(app)
    response = client.get("/admin/privacy-security")

    assert response.status_code == 200
    assert b"Anonymize (recommended)" in response.data
    assert b"Delete permanently" in response.data
    assert b"confirmation_count" in response.data
    assert b"I understand this cannot be undone" in response.data
    assert b"confirm_irreversible" in response.data
    assert b"Download archive copy" in response.data
    assert b"Review records" in response.data
    assert b'href="#patient-retention-review"' in response.data
    assert b"Oldest last screening among due" in response.data
    assert b"Cutoff date" in response.data


def test_successful_multi_record_batch_writes_one_audit_with_original_codes(app):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
        first_id = _seed_patient(app, patient_code="RET-AUDIT-ONE")
        second_id = _seed_patient(app, patient_code="RET-AUDIT-TWO")
    client = _admin_client(app)
    ids = [first_id, second_id]
    assert _download_archive(client, ids).status_code == 200
    _apply_retention(client, ids, action="anonymize")

    audits = _critical_retention_audits(app)
    assert len(audits) == 1
    action = audits[0]["action"]
    assert "anonymize" in action
    assert "records=2" in action
    assert "anonymized=2" in action
    assert "deleted=0" in action
    assert "retention_days=365" in action
    assert "cutoff_date=" in action
    assert "RET-AUDIT-ONE" in action
    assert "RET-AUDIT-TWO" in action


def _seed_due_patients(app, count):
    with app.app_context():
        settings_model.set_patient_retention_days(365)
    for index in range(count):
        _seed_patient(
            app,
            patient_code=f"RP-{index:03d}",
            created_days_ago=1000 - index,
            with_related=False,
        )


def test_retention_review_paginates_due_records(app):
    _seed_due_patients(app, 30)
    client = _admin_client(app)

    first = client.get("/admin/privacy-security")
    assert first.status_code == 200
    assert b"Showing 1&ndash;25 of 30" in first.data
    assert b"RP-000" in first.data and b"RP-024" in first.data
    assert b"RP-025" not in first.data
    assert b"Page 1 of 2" in first.data

    second = client.get("/admin/privacy-security?page=2")
    assert b"Showing 26&ndash;30 of 30" in second.data
    assert b"RP-025" in second.data and b"RP-029" in second.data
    assert b"RP-024" not in second.data
    assert b"Page 2 of 2" in second.data


def test_retention_review_invalid_pagination_inputs_are_clamped(app):
    _seed_due_patients(app, 30)
    client = _admin_client(app)

    bad_size = client.get("/admin/privacy-security?per_page=7")
    assert b"Showing 1&ndash;25 of 30" in bad_size.data
    junk = client.get("/admin/privacy-security?page=abc&per_page=xyz")
    assert b"Showing 1&ndash;25 of 30" in junk.data
    low = client.get("/admin/privacy-security?page=-4")
    assert b"Page 1 of 2" in low.data
    high = client.get("/admin/privacy-security?page=99&per_page=10")
    assert b"Showing 21&ndash;30 of 30" in high.data
    assert b"Page 3 of 3" in high.data
    assert b"RP-029" in high.data and b"RP-019" not in high.data


def test_retention_selection_and_archive_work_for_second_page(app):
    _seed_due_patients(app, 12)
    client = _admin_client(app)
    page = client.get("/admin/privacy-security?page=2&per_page=10")
    assert b"Showing 11&ndash;12 of 12" in page.data
    with app.app_context():
        ids = [
            row["id"]
            for row in patient_model.list_patients_due_for_retention(limit=10, offset=10)
        ]
    assert len(ids) == 2

    response = _download_archive(client, [str(i) for i in ids])
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
