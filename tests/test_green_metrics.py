import os
import sys
from datetime import datetime, timedelta, timezone

from conftest import issue_token
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # noqa: E402
from app.controllers.metrics_controller import sql_utc  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.ml.green_metrics import BatteryReader, measure  # noqa: E402
from app.models.health_analytics_model import get_risk_status_distribution  # noqa: E402
from config import Config  # noqa: E402


def _battery(tmp_path, voltage, current, **extra):
    vals = {"voltage_now": voltage, "current_now": current, "temp": "315", "capacity": "80",
            "status": "Discharging", **extra}
    for name, val in vals.items():
        (tmp_path / name).write_text(str(val))
    return BatteryReader(str(tmp_path))


# ---- measurement ------------------------------------------------------------------------

def test_unit_detection_uA_and_mA(tmp_path):
    assert _battery(tmp_path, 3_800_000, -500_000).sample()["power_w"] == pytest.approx(1.9)
    assert _battery(tmp_path, 3_800_000, 500).sample()["power_w"] == pytest.approx(1.9)


def test_temperature_and_charging(tmp_path):
    s = _battery(tmp_path, 3_800_000, 500_000, status="Charging").sample()
    assert s["temp_c"] == 31.5 and s["charging"] is True


def test_measure_battery_and_fallback(tmp_path):
    with measure(_battery(tmp_path, 4_000_000, 1_000_000), 0.6) as m:
        sum(range(200_000))
    assert m.method == "battery" and m.power_w == pytest.approx(4.0)
    assert m.energy_kwh == pytest.approx(4.0 * m.latency_ms / 1000 / 3.6e6)
    with measure(BatteryReader(str(tmp_path / "missing")), 0.6, tdp_w=5) as m2:
        sum(range(100_000))
    assert m2.method == "estimated"


def test_charging_readings_are_not_used_as_consumption(tmp_path):
    r = _battery(tmp_path, 4_000_000, 1_000_000, status="Charging")
    with measure(r, 0.6, tdp_w=5) as m:
        sum(range(100_000))
    assert m.method == "estimated"


def test_telemetry_stores_null_power_while_charging(app):
    from app.ml.telemetry import record_sample
    d = os.path.join(os.path.dirname(app.config["DATABASE"]), "bat")
    os.makedirs(d, exist_ok=True)
    for name, val in {"voltage_now": 4_000_000, "current_now": 900_000, "temp": 300,
                      "capacity": 90, "status": "Charging"}.items():
        open(os.path.join(d, name), "w").write(str(val))
    with app.app_context():
        conn = get_connection()
        assert record_sample(conn, BatteryReader(d), "grid") is True
        row = conn.execute("SELECT power_w, power_source FROM system_telemetry_log").fetchone()
        assert row["power_w"] is None and row["power_source"] == "AC_CHARGING"


# ---- app fixtures -----------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    cfg = type("TestConfig", (Config,), {
        "DATABASE": str(tmp_path / "t.sqlite3"), "TESTING": True, "WTF_CSRF_ENABLED": False,
        "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery"), "REQUIRE_ADMIN_APPROVAL": False})
    return create_app(cfg)


def _login(client, role):
    with client.session_transaction() as s:
        s["session_token"] = issue_token(client, 1)
        s["user_id"], s["user_role"] = 1, role
        s["security_version"] = 1
        s["last_active"] = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def admin(app):
    c = app.test_client()
    _login(c, "medical_officer")
    return c


def _db(app):
    with app.app_context():
        return get_connection()


def test_migration_0012_applies_cleanly(app):
    with app.app_context():
        conn = get_connection()
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"green_computing_log", "system_telemetry_log", "sync_queue_log",
                "network_event_log"} <= names
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


# ---- access control ------------------------------------------------------------------------

def test_api_requires_medical_officer(app):
    c = app.test_client()
    assert c.get("/api/v1/green/score").status_code == 401
    _login(c, "health_worker")
    assert c.get("/api/v1/green/score").status_code == 403
    assert c.get("/admin/green-computing").status_code == 403
    _login(c, "medical_officer")
    assert c.get("/api/v1/green/score").status_code == 200


# ---- data flow -----------------------------------------------------------------------------------

def _seed_rows(app):
    with app.app_context():
        conn = get_connection()
        now = datetime.now(timezone.utc)
        pid = conn.execute("INSERT INTO patients (patient_code,last_name,first_name,birthdate,sex)"
                           " VALUES ('CAB-1','X','Y','1980-01-01','Male')").lastrowid
        vid = conn.execute("INSERT INTO visits (patient_id,visit_type,assessment_date)"
                           " VALUES (?, 'intake','2026-01-01')", (pid,)).lastrowid
        conn.execute("INSERT INTO lab_screenings (visit_id,fbs_mg_dl,test_datetime,final_risk_level)"
                     " VALUES (?,131,'2026-01-01 08:00:00','High')", (vid,))
        conn.execute("INSERT INTO sync_queue_log (visit_id, offline_created_at, gap_identifier)"
                     " VALUES (?,?, 'g1')", (vid, sql_utc(now)))
        conn.commit()
        return pid, vid


def test_predict_writes_log_and_dashboard_reads_it(app, admin):
    r = admin.post("/api/v1/predict", json={"features": {"fbs_mg_dl": 131}})
    assert r.status_code == 200 and r.json["is_stub_model"] is True
    assert r.json["model_predicted_risk_level"] == "Diabetic" and r.json["green_log_id"]
    assert admin.post("/api/v1/predict", json={}).status_code == 400
    assert admin.get("/api/v1/green/score").json["inferences"] == 1
    assert admin.get("/api/v1/green/stats/today").json["inferences"] == 1
    page = admin.get("/admin/green-computing")
    assert page.status_code == 200 and b"gc-stat-card" in page.data


def test_pending_queue_and_soft_delete(app, admin):
    pid, _ = _seed_rows(app)
    rows = admin.get("/api/v1/green/sync/pending").json["records"]
    assert rows[0]["patient_code"] == "CAB-1" and rows[0]["fbs_mg_dl"] == 131 and rows[0]["risk"] == "High"
    summ = admin.get("/api/v1/green/sync/summary").json
    assert summ["queued"] == 1 and summ["queue"] == {"screenings": 1, "patients": 1, "assessments": 1}
    with app.app_context():
        conn = get_connection()
        conn.execute("UPDATE patients SET deleted_at = CURRENT_TIMESTAMP WHERE id=?", (pid,))
        conn.commit()
    assert admin.get("/api/v1/green/sync/pending").json["records"] == []   # recycle-bin patients hidden


def test_risk_status_distribution_groups_by_risk_not_visit_status(app):
    with app.app_context():
        conn = get_connection()
        for index, risk in enumerate(("Low", "Moderate", "High"), start=1):
            patient_id = conn.execute(
                "INSERT INTO patients (patient_code,last_name,first_name,birthdate,sex) "
                "VALUES (?, 'Risk', ?, '1980-01-01', 'Male')",
                (f"RISK-{index}", risk),
            ).lastrowid
            visit_id = conn.execute(
                "INSERT INTO visits (patient_id,visit_type,assessment_date,status) "
                "VALUES (?, 'intake', '2026-01-01', 'submitted')",
                (patient_id,),
            ).lastrowid
            conn.execute(
                "INSERT INTO lab_screenings (visit_id,fbs_mg_dl,test_datetime,preliminary_risk_level) "
                "VALUES (?, 110, '2026-01-01 08:00:00', ?)",
                (visit_id, risk),
            )
        conn.commit()
        assert get_risk_status_distribution() == {"Low": 1, "Moderate": 1, "High": 1}


def test_telemetry_energy_and_uptime(app, admin):
    with app.app_context():
        conn = get_connection()
        now = datetime.now(timezone.utc)
        for m in range(10, -1, -1):                       # 11 samples, 60 s apart, 2 W
            conn.execute("INSERT INTO system_telemetry_log (power_w, is_idle, power_source, recorded_at)"
                         " VALUES (2.0, 1, 'SOLAR_UPS', ?)", (sql_utc(now - timedelta(minutes=m)),))
        conn.commit()
        from app.models import green
        start, end = sql_utc(now - timedelta(hours=1)), sql_utc(now + timedelta(seconds=1))
        assert green.device_energy_kwh(conn, start, end, 180) == pytest.approx(2.0 * 600 / 3.6e6)
        assert green.uptime_seconds(conn, start, end, 180) == pytest.approx(600, abs=1)
        conn.execute("INSERT INTO system_telemetry_log (power_w, recorded_at) VALUES (2.0, ?)",
                     (sql_utc(now + timedelta(hours=1)),))   # long silence: capped, not integrated
        conn.commit()
        assert green.uptime_seconds(conn, start, sql_utc(now + timedelta(hours=2)), 180) == pytest.approx(780, abs=1)
    body = admin.get("/api/v1/green/charts/realtime?range=24h").json
    assert body["basis"] == "device_telemetry" and len(body["labels"]) == 24
    comp = admin.get("/api/v1/green/charts/component-breakdown").json
    assert any(c["label"] == "Idle & Other" for c in comp["components"])
    assert admin.get("/api/v1/green/charts/realtime?range=bad").status_code == 400


def test_offline_gap_pairing_and_state(app, admin):
    with app.app_context():
        conn = get_connection()
        now = datetime.now(timezone.utc)
        rows = [("DISCONNECT", "g1", None, now - timedelta(minutes=50)),
                ("RECONNECT", "g1", 5, now - timedelta(minutes=30)),
                ("DISCONNECT", "g2", None, now - timedelta(minutes=5))]
        for typ, gid, rec, ts in rows:
            conn.execute("INSERT INTO network_event_log (event_type, gap_identifier, record_count, created_at)"
                         " VALUES (?,?,?,?)", (typ, gid, rec, sql_utc(ts)))
        conn.commit()
    from app.controllers import metrics_controller as mc
    with app.app_context():
        conn = get_connection()
        c = mc.connectivity(conn)
    assert c["is_offline"] is True                       # g2 still open
    assert sum(1 for s in c["timeline"] if not s["online"]) == 2
    assert len(admin.get("/api/v1/green/logs/events").json["events"]) == 3


def test_empty_database_renders(app, admin):
    page = admin.get("/admin/green-computing")
    assert page.status_code == 200
    assert admin.get("/api/v1/green/score").json["score"] is None
    assert admin.get("/health").json["model_loaded"] is False


# ---- demo mode ------------------------------------------------------------------------------

@pytest.fixture
def demo_app(tmp_path):
    cfg = type("DemoConfig", (Config,), {
        "DATABASE": str(tmp_path / "d.sqlite3"), "TESTING": True, "WTF_CSRF_ENABLED": False, "DEMO_MODE": True,
        "BATTERY_SYSFS_DIR": str(tmp_path / "nobattery")})
    return create_app(cfg)


def test_demo_routes_are_off_by_default(admin):
    assert admin.post("/api/v1/green/demo/screening").status_code == 404
    assert admin.post("/api/v1/green/sync/retry").status_code == 501


def test_demo_offline_queue_and_restore_flow(demo_app):
    c = demo_app.test_client()
    _login(c, "medical_officer")
    assert c.post("/api/v1/green/demo/screening", json={"count": 2}).json["queued"] is False
    assert c.get("/api/v1/green/sync/summary").json["queued"] == 0
    c.post("/api/v1/green/demo/disconnect")
    assert c.post("/api/v1/green/demo/screening", json={"count": 3}).json["queued"] is True
    summ = c.get("/api/v1/green/sync/summary").json
    assert summ["queued"] == 3 and summ["queue"]["screenings"] == 3
    page = c.get("/admin/green-computing")                 # open gap shows its queued records
    assert page.status_code == 200 and b"3 records queued" in page.data
    assert "still offline" in c.post("/api/v1/green/sync/retry").json["message"].lower()
    c.post("/api/v1/green/demo/reconnect")
    summ = c.get("/api/v1/green/sync/summary").json
    assert summ["queued"] == 0 and summ["synced"] == 3
    types = [e["event_type"] for e in c.get("/api/v1/green/logs/events").json["events"]]
    assert {"DISCONNECT", "RECONNECT", "SYNC_START", "SYNC_COMPLETE"} <= set(types)
    assert c.get("/api/v1/green/score").json["inferences"] == 5


def test_demo_seed_and_clear(demo_app):
    c = demo_app.test_client()
    _login(c, "medical_officer")
    assert c.post("/api/v1/green/demo/seed").status_code == 200
    assert c.get("/api/v1/green/stats/today").json["includes_seeded_demo_data"] is True
    c.post("/api/v1/green/demo/seed")                      # re-seeding must not collide
    c.post("/api/v1/green/demo/clear")
    assert c.get("/api/v1/green/score").json["inferences"] == 0
