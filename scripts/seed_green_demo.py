"""Demo data for the Green Computing page, clearly labelled so it can be removed.

    python -m scripts.seed_green_demo            # add demo data
    python -m scripts.seed_green_demo --purge    # remove everything this script added

Demo patients have patient_code 'DEMO-####' (no real names). Demo inference rows have
measurement_method='seeded'. Demo telemetry is tracked by id range in app_settings.
Refuses to add telemetry if real telemetry rows already exist.
"""
import random
import sys
from datetime import datetime, timedelta, timezone

from app import create_app
from app.controllers.metrics_controller import sql_utc
from app.db import get_connection
from app.models import green

RISKS = ["Low", "Moderate", "High"]


def purge(conn):
    conn.execute("DELETE FROM patients WHERE patient_code LIKE 'DEMO-%'")  # cascades visits etc.
    conn.execute("DELETE FROM green_computing_log WHERE measurement_method = 'seeded'")
    conn.execute("DELETE FROM network_event_log WHERE detail LIKE '%(demo)%'")
    row = conn.execute("SELECT value FROM app_settings WHERE key='green_demo_telemetry_ids'").fetchone()
    if row:
        lo, hi = map(int, row["value"].split("-"))
        conn.execute("DELETE FROM system_telemetry_log WHERE id BETWEEN ? AND ?", (lo, hi))
        conn.execute("DELETE FROM app_settings WHERE key='green_demo_telemetry_ids'")
    conn.commit()
    print("Demo data removed.")


def seed(conn, app, days=3):
    rnd = random.Random(7)
    now = datetime.now(timezone.utc)
    factor = app.config["EMISSION_FACTOR_KG_PER_KWH"]

    # patients / visits / lab screenings (offline queue rows point at visits)
    visit_ids = []
    for i in range(1, 13):
        pid = conn.execute(
            "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex, barangay_id)"
            " VALUES (?, 'Demo', ?, '1980-01-01', 'Female', 1)", (f"DEMO-{i:04d}", f"Patient{i}")).lastrowid
        t = now - timedelta(minutes=rnd.randint(5, 360))
        vid = conn.execute(
            "INSERT INTO visits (patient_id, visit_type, assessment_date, status, created_at)"
            " VALUES (?, 'intake', ?, 'submitted', ?)", (pid, t.date().isoformat(), sql_utc(t))).lastrowid
        fbs = rnd.choice([88, 97, 104, 118, 131, 148])
        conn.execute(
            "INSERT INTO lab_screenings (visit_id, fbs_mg_dl, test_datetime, preliminary_risk_level,"
            " model_predicted_risk_level, model_confidence, final_risk_level)"
            " VALUES (?,?,?,?,?,?,?)",
            (vid, fbs, sql_utc(t), rnd.choice(RISKS), "Normal", 0.8, rnd.choice(RISKS)))
        visit_ids.append((vid, t))

    ls_ids = [r[0] for r in conn.execute(
        "SELECT ls.id FROM lab_screenings ls JOIN visits v ON v.id=ls.visit_id "
        "JOIN patients p ON p.id=v.patient_id WHERE p.patient_code LIKE 'DEMO-%'")]

    # inference log rows
    for _ in range(200):
        ts = now - timedelta(minutes=rnd.randint(0, days * 24 * 60))
        lat, power = rnd.uniform(4, 40), rnd.uniform(1.0, 3.0)
        kwh = power * lat / 1000 / 3.6e6
        dbm = rnd.uniform(0.5, 4)
        row = {"lab_screening_id": None, "inference_latency_ms": lat,
               "cpu_utilization_pct": rnd.uniform(5, 60), "ram_utilization_mb": rnd.uniform(80, 200),
               "power_draw_w": power, "energy_consumed_kwh": kwh, "carbon_emissions_kg": kwh * factor,
               "request_ms": lat + dbm + rnd.uniform(2, 12), "db_io_ms": dbm,
               "measurement_method": "seeded"}
        lid = green.insert_log(conn, row)
        conn.execute("UPDATE green_computing_log SET created_at=? WHERE id=?", (sql_utc(ts), lid))
    for lid_row, ls in zip(conn.execute("SELECT id FROM green_computing_log WHERE lab_screening_id IS NULL "
                                        "ORDER BY id DESC LIMIT ?", (len(ls_ids),)).fetchall(), ls_ids):
        green.link_lab_screening(conn, lid_row["id"], ls)

    # one offline gap with a queue behind it, one already synced
    gap = "gap-demo-" + now.strftime("%H%M")
    start = now - timedelta(minutes=45)
    green.log_event(conn, "DISCONNECT", gap, detail="Connection lost (demo)")
    conn.execute("UPDATE network_event_log SET created_at=? WHERE gap_identifier=?", (sql_utc(start), gap))
    for i, (vid, t) in enumerate(visit_ids):
        green.enqueue_visit(conn, vid, sql_utc(max(t, start)), gap)
        if i >= 8:
            green.mark_synced(conn, vid)
    old_gap = "gap-demo-old"
    green.log_event(conn, "DISCONNECT", old_gap, detail="Connection lost (demo)")
    green.log_event(conn, "RECONNECT", old_gap, record_count=4, duration_s=1080, detail="Connection restored (demo)")
    conn.execute("UPDATE network_event_log SET created_at=? WHERE gap_identifier=? AND event_type='DISCONNECT'",
                 (sql_utc(now - timedelta(hours=5)), old_gap))
    conn.execute("UPDATE network_event_log SET created_at=? WHERE gap_identifier=? AND event_type='RECONNECT'",
                 (sql_utc(now - timedelta(hours=5) + timedelta(minutes=18)), old_gap))

    # telemetry (1/min)
    if conn.execute("SELECT 1 FROM system_telemetry_log LIMIT 1").fetchone():
        print("Real telemetry exists - not adding demo telemetry.")
    else:
        rows = []
        for m in range(days * 24 * 60, 0, -1):
            ts = now - timedelta(minutes=m)
            idle = rnd.random() < 0.7
            rows.append((rnd.uniform(40, 100), rnd.uniform(28, 36),
                         rnd.uniform(0.9, 1.3) if idle else rnd.uniform(1.6, 3.0), int(idle),
                         rnd.choice(["BATTERY", "AC_CHARGING", "SOLAR_UPS"]), sql_utc(ts)))
        conn.executemany("INSERT INTO system_telemetry_log (battery_level_pct, battery_temp_c, power_w,"
                         " is_idle, power_source, recorded_at) VALUES (?,?,?,?,?,?)", rows)
        lo, hi = conn.execute("SELECT MIN(id), MAX(id) FROM system_telemetry_log").fetchone()
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('green_demo_telemetry_ids', ?)",
                     (f"{lo}-{hi}",))
    conn.commit()
    print("Demo data added. Remove with: python -m scripts.seed_green_demo --purge")


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        c = get_connection()
        try:
            purge(c) if "--purge" in sys.argv else seed(c, application)
        finally:
            c.close()
