"""Presentation helpers for the Green Computing page (FBS_DEMO_MODE=1 only).

They drive the *real* code paths - measured inference, `sync_queue.on_visit_saved`,
`sync_queue.flush_pending`, the event log - so the page can be demonstrated without unplugging
a router. Demo patients have patient_code 'DEMO-XXXXXX' and are removed by "Clear demo data".
The simulate/restore buttons write the same events as the real monitor, so do not use them while
`flask connectivity-monitor` is running. "Run screening" is safe either way: during a real outage
it queues records through the real `on_visit_saved()`.
"""
import random
import uuid
from datetime import datetime, timezone

from app.controllers import metrics_controller as mc
from app.models import green
from app.services import sync_queue

RISK_MAP = {"Normal": "Low", "Pre-Diabetic": "Moderate", "Diabetic": "High"}


def run_screenings(db, predictor, reader, count=1):
    queued_any = False
    for _ in range(count):
        fbs = random.choices([88, 95, 104, 112, 126, 138, 152], weights=[3, 3, 3, 2, 2, 2, 1])[0]
        features = {"fbs_mg_dl": fbs, "age": random.randint(40, 70), "bmi": round(random.uniform(21, 33), 1)}
        code = "DEMO-" + uuid.uuid4().hex[:6].upper()
        pid = db.execute(
            "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex, barangay_id)"
            " VALUES (?, 'Demo', 'Patient', '1980-01-01', 'Female', 1)", (code,)).lastrowid
        vid = db.execute(
            "INSERT INTO visits (patient_id, visit_type, assessment_date, status)"
            " VALUES (?, 'intake', date('now'), 'submitted')", (pid,)).lastrowid
        r = mc.run_measured_prediction(db, predictor, reader, features)   # commits
        risk = RISK_MAP.get(r["model_predicted_risk_level"], "Low")
        ls = db.execute(
            "INSERT INTO lab_screenings (visit_id, fbs_mg_dl, test_datetime, preliminary_risk_level,"
            " model_predicted_risk_level, model_confidence, final_risk_level)"
            " VALUES (?,?,datetime('now'),?,?,?,?)",
            (vid, fbs, risk, r["model_predicted_risk_level"], r["model_confidence"], risk)).lastrowid
        green.link_lab_screening(db, r["green_log_id"], ls)
        # The exact call the nurse branch makes, in the same transaction as the save:
        queued_any = bool(sync_queue.on_visit_saved(db, vid)) or queued_any
        db.commit()
    return {"message": f"{count} screening(s) run" + (" while offline (queued)" if queued_any else ""),
            "queued": queued_any}


def disconnect(db):
    if sync_queue.open_gap(db):
        return {"message": "Already offline"}
    gid = "gap-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    green.log_event(db, "DISCONNECT", gid, detail="Connection lost (demo)")
    db.commit()
    return {"message": "Connection loss simulated - new screenings will queue"}


def reconnect(db):
    gap = sync_queue.open_gap(db)
    if not gap:
        return {"message": "Already online"}
    gid, started = gap
    n = green.gap_record_count(db, gid)
    dur = (datetime.now(timezone.utc) - mc._parse(started)).total_seconds()
    green.log_event(db, "RECONNECT", gid, record_count=n, duration_s=dur, detail="Connection restored (demo)")
    db.commit()
    res = sync_queue.flush_pending(db, sync_queue.DemoTransport())
    return {"message": f"Connection restored - {res.sent} queued record(s) synced"}


def retry_sync(db):
    if sync_queue.open_gap(db):
        return {"message": "Still offline - nothing to sync yet", "ok": False}
    res = sync_queue.flush_pending(db, sync_queue.DemoTransport())
    return {"message": f"{res.sent} record(s) synced" if res.sent else "Nothing pending", "ok": True}


def seed_history(app):
    from app.db import get_connection
    from scripts import seed_green_demo
    conn = get_connection()
    try:
        seed_green_demo.purge(conn)          # avoid duplicate DEMO patient codes
        seed_green_demo.seed(conn, app)
    finally:
        conn.close()
    return {"message": "Demo history loaded (3 days)"}


def clear_demo(app):
    from app.db import get_connection
    from scripts import seed_green_demo
    conn = get_connection()
    try:
        seed_green_demo.purge(conn)
        conn.execute("DELETE FROM network_event_log WHERE detail LIKE '%(demo)%'")
        conn.commit()
    finally:
        conn.close()
    return {"message": "Demo data cleared"}
