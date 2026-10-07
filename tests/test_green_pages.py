"""'View all' pages, dashboard warnings and the connectivity CLI."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # noqa: E402
from app.controllers.metrics_controller import paginate, sql_utc  # noqa: E402
from app.db import get_connection  # noqa: E402
from config import Config  # noqa: E402


@pytest.fixture
def app(tmp_path):
    cfg = type("C", (Config,), {"DATABASE": str(tmp_path / "p.sqlite3"), "TESTING": True, "WTF_CSRF_ENABLED": False,
                                "BATTERY_SYSFS_DIR": str(tmp_path / "nobat"),
                                "PROBE_TARGETS": "127.0.0.1:1", "PROBE_TIMEOUT_S": 0.5})
    return create_app(cfg)


def login(client, role="medical_officer"):
    with client.session_transaction() as s:
        s["user_id"], s["user_role"] = 1, role
        s["security_version"] = 1
        s["last_active"] = datetime.now(timezone.utc).isoformat()
    return client


@pytest.fixture
def admin(app):
    return login(app.test_client())


def test_dashboard_barangay_patients_endpoint_filters_and_handles_empty_query(app, admin):
    with app.app_context():
        conn = get_connection()
        barangay = conn.execute("SELECT id, name FROM barangays ORDER BY name LIMIT 1").fetchone()
        patient_id = conn.execute(
            "INSERT INTO patients (patient_code,last_name,first_name,birthdate,sex,barangay_id) "
            "VALUES ('BARANGAY-TEST','Test','Barangay','1990-01-01','Female',?)",
            (barangay["id"],),
        ).lastrowid
        conn.commit()

    assert admin.get("/nurse/dashboard/barangay-patients").json == {"patients": []}
    response = admin.get(
        "/nurse/dashboard/barangay-patients",
        query_string={"barangay": barangay["name"]},
    )
    assert response.status_code == 200
    patients = response.json["patients"]
    assert len(patients) == 1
    assert patients[0]["patient_code"] == "BARANGAY-TEST"
    assert patients[0]["barangay"] == barangay["name"]
    assert patients[0]["first_name"] == "Barangay"
    assert patients[0]["last_name"] == "Test"


def add_events(app, n):
    with app.app_context():
        conn = get_connection()
        base = datetime.now(timezone.utc) - timedelta(hours=1)
        for i in range(n):
            typ = "DISCONNECT" if i % 2 == 0 else "RECONNECT"
            conn.execute("INSERT INTO network_event_log (event_type, gap_identifier, record_count, duration_s,"
                         " detail, created_at) VALUES (?,?,?,?,?,?)",
                         (typ, f"gap-{i // 2}", i, 60.0 * i, f"event {i}", sql_utc(base + timedelta(minutes=i))))
        conn.commit()


def add_queue(app, statuses):
    with app.app_context():
        conn = get_connection()
        for i, st in enumerate(statuses):
            pid = conn.execute("INSERT INTO patients (patient_code,last_name,first_name,birthdate,sex)"
                               " VALUES (?, 'A','B','1980-01-01','Male')", (f"Q-{i:03d}",)).lastrowid
            vid = conn.execute("INSERT INTO visits (patient_id,visit_type,assessment_date)"
                               " VALUES (?, 'intake','2026-09-21')", (pid,)).lastrowid
            conn.execute("INSERT INTO sync_queue_log (visit_id, sync_status, offline_created_at, gap_identifier,"
                         " last_error) VALUES (?,?,?,?,?)",
                         (vid, st, sql_utc(datetime.now(timezone.utc) - timedelta(minutes=i)), "gap-9",
                          "rejected by server" if st == "FAILED" else None))
        conn.commit()


def test_paginate_math():
    p = paginate(0, 1)
    assert (p["pages"], p["start"], p["end"], p["prev_url"], p["next_url"]) == (1, 0, 0, None, None)
    p = paginate(60, 3, {"type": "RECONNECT", "empty": ""})
    assert (p["pages"], p["start"], p["end"], p["offset"]) == (3, 51, 60, 50)
    assert p["prev_url"] == "?type=RECONNECT&page=2" and p["next_url"] is None
    assert paginate(60, 99)["page"] == 3 and paginate(60, -4)["page"] == 1     # clamped


def test_events_page_paginates_and_filters(app, admin):
    add_events(app, 30)
    r = admin.get("/admin/green-computing/events")
    assert r.status_code == 200 and r.data.count(b"ev-pill") == 25 and b"Showing 1" in r.data
    r2 = admin.get("/admin/green-computing/events?page=2")
    assert r2.data.count(b"ev-pill") == 5
    only = admin.get("/admin/green-computing/events?type=RECONNECT").data.split(b"<tbody>")[1]
    assert only.count(b"Connection restored") == 15 and b"Connection lost" not in only
    ignored = admin.get("/admin/green-computing/events?type=DROP TABLE&page=abc")
    assert ignored.status_code == 200                                   # invalid input is ignored, not an error


def test_events_page_empty_state(admin):
    assert b"No events recorded" in admin.get("/admin/green-computing/events").data


def test_pending_page_filters_and_hides_deleted(app, admin):
    add_queue(app, ["QUEUED", "QUEUED", "FAILED", "SYNCED"])
    with app.app_context():
        conn = get_connection()
        conn.execute("UPDATE patients SET deleted_at = CURRENT_TIMESTAMP WHERE patient_code = 'Q-000'")
        conn.commit()
    pending = admin.get("/admin/green-computing/pending").data
    assert b"Q-001" in pending and b"Q-002" in pending and b"rejected by server" in pending
    assert b"Q-000" not in pending and b"Q-003" not in pending           # deleted patient / synced row hidden
    assert b"Q-003" in admin.get("/admin/green-computing/pending?status=synced").data
    assert admin.get("/admin/green-computing/pending?status=all").data.count(b"Q-0") == 3
    assert admin.get("/admin/green-computing/pending?status=bogus").status_code == 200


def test_view_all_pages_require_medical_officer(app):
    c = app.test_client()
    assert c.get("/admin/green-computing/events").status_code == 302     # to login
    login(c, "health_worker")
    assert c.get("/admin/green-computing/events").status_code == 403
    assert c.get("/admin/green-computing/pending").status_code == 403


def test_dashboard_links_and_monitor_warning(app, admin):
    page = admin.get("/admin/green-computing").data
    assert b"/admin/green-computing/pending" in page and b"/admin/green-computing/events" in page
    assert b"has never run" in page                                        # no monitor heartbeat yet
    with app.app_context():
        from app.services.connectivity import KEY_LAST_PROBE
        conn = get_connection()
        from app.models import green
        green.set_kv(conn, KEY_LAST_PROBE, sql_utc(datetime.now(timezone.utc)))
        conn.commit()
    assert b"Connectivity monitor" not in admin.get("/admin/green-computing").data


def test_health_reports_monitor_and_link(admin):
    body = admin.get("/health").json
    assert body["connectivity_monitor"] == "never" and body["link_state"] == "up"


def test_connectivity_status_cli(app):
    out = app.test_cli_runner().invoke(args=["connectivity-status"])
    assert out.exit_code == 0
    assert "UNREACHABLE" in out.output and "never" in out.output and "Detection delay" in out.output
