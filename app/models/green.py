"""Green-computing queries. Raw parameterized sqlite3, same style as app/models/user.py.

All timestamps are UTC 'YYYY-MM-DD HH:MM:SS'. `start`/`end` arguments use that format;
`offset_s` (seconds) shifts a timestamp to local time for day/hour bucketing.
Needs SQLite >= 3.25 (window functions); Termux ships a newer one.
"""

FAR_FUTURE = "9999-12-31 00:00:00"


def insert_log(db, row: dict) -> int:
    cur = db.execute(
        """INSERT INTO green_computing_log
           (lab_screening_id, inference_latency_ms, cpu_utilization_pct, ram_utilization_mb,
            power_draw_w, energy_consumed_kwh, carbon_emissions_kg, request_ms, db_io_ms,
            measurement_method)
           VALUES (:lab_screening_id, :inference_latency_ms, :cpu_utilization_pct,
                   :ram_utilization_mb, :power_draw_w, :energy_consumed_kwh,
                   :carbon_emissions_kg, :request_ms, :db_io_ms, :measurement_method)""",
        row,
    )
    return cur.lastrowid


def link_lab_screening(db, log_id: int, lab_screening_id: int):
    db.execute("UPDATE green_computing_log SET lab_screening_id = ? WHERE id = ?",
               (lab_screening_id, log_id))


def totals(db, start, end=FAR_FUTURE):
    """Per-inference aggregates (energy attributed to model runs only)."""
    return db.execute(
        """SELECT COUNT(*) AS n,
                  COALESCE(SUM(energy_consumed_kwh),0)  AS energy_kwh,
                  COALESCE(SUM(carbon_emissions_kg),0)  AS carbon_kg,
                  COALESCE(AVG(inference_latency_ms),0) AS avg_latency_ms,
                  COALESCE(SUM(measurement_method='seeded'),0) AS seeded_n,
                  COALESCE(SUM(power_draw_w * inference_latency_ms),0) / 1000.0 / 3.6e6 AS ml_kwh,
                  COALESCE(SUM(power_draw_w * MAX(COALESCE(request_ms,0)
                           - inference_latency_ms - COALESCE(db_io_ms,0), 0)),0)
                           / 1000.0 / 3.6e6 AS web_kwh,
                  COALESCE(SUM(power_draw_w * COALESCE(db_io_ms,0)),0) / 1000.0 / 3.6e6 AS db_kwh
           FROM green_computing_log WHERE created_at >= ? AND created_at < ?""",
        (start, end),
    ).fetchone()


def inference_series(db, start, fmt, offset_s):
    return db.execute(
        f"""SELECT strftime('{fmt}', created_at, '{int(offset_s):+d} seconds') AS bucket,
                   SUM(energy_consumed_kwh) AS energy_kwh, SUM(carbon_emissions_kg) AS carbon_kg
            FROM green_computing_log WHERE created_at >= ? GROUP BY bucket ORDER BY bucket""",
        (start,),
    ).fetchall()


# ---- telemetry -----------------------------------------------------------------------

_GAPS = """WITH t AS (
    SELECT recorded_at, power_w, power_source, is_idle,
           (julianday(recorded_at) - julianday(LAG(recorded_at) OVER (ORDER BY recorded_at))) * 86400.0 AS dt
    FROM system_telemetry_log WHERE recorded_at >= ? AND recorded_at < ?)"""


def has_telemetry(db, start, end=FAR_FUTURE) -> bool:
    """True when there are power readings (rows taken while charging store NULL power)."""
    return db.execute("SELECT 1 FROM system_telemetry_log WHERE recorded_at >= ? AND recorded_at < ?"
                      " AND power_w IS NOT NULL LIMIT 1", (start, end)).fetchone() is not None


def device_energy_kwh(db, start, end, cap_s):
    """Integrates sampled device power over time. Gaps longer than cap_s (app was down) are
    counted as cap_s, not as a long stretch at the last reading."""
    r = db.execute(_GAPS + " SELECT COALESCE(SUM(power_w * MIN(dt, ?)),0) / 3.6e6 AS kwh FROM t"
                   " WHERE dt IS NOT NULL AND power_w IS NOT NULL", (start, end, cap_s)).fetchone()
    return r["kwh"]


def device_series(db, start, fmt, offset_s, cap_s):
    return db.execute(
        _GAPS + f""" SELECT strftime('{fmt}', recorded_at, '{int(offset_s):+d} seconds') AS bucket,
                      SUM(power_w * MIN(dt, ?)) / 3.6e6 AS energy_kwh
               FROM t WHERE dt IS NOT NULL AND power_w IS NOT NULL GROUP BY bucket ORDER BY bucket""",
        (start, FAR_FUTURE, cap_s),
    ).fetchall()


def uptime_seconds(db, start, end, cap_s):
    r = db.execute(_GAPS + " SELECT COALESCE(SUM(MIN(dt, ?)),0) AS s FROM t WHERE dt IS NOT NULL",
                   (start, end, cap_s)).fetchone()
    return r["s"]


def idle_and_source(db, start, end=FAR_FUTURE):
    return db.execute(
        """SELECT AVG(CASE WHEN is_idle = 1 THEN power_w END) AS idle_w,
                  COUNT(*) AS n,
                  COALESCE(SUM(power_source = 'SOLAR_UPS'), 0) AS solar_n
           FROM system_telemetry_log WHERE recorded_at >= ? AND recorded_at < ?""",
        (start, end),
    ).fetchone()


# ---- connectivity / sync ---------------------------------------------------------------

def events_since(db, start):
    return db.execute(
        """SELECT event_type, gap_identifier, record_count, duration_s, created_at
           FROM network_event_log WHERE created_at >= ? ORDER BY created_at, id""", (start,)
    ).fetchall()


def last_connectivity_event(db):
    return db.execute(
        """SELECT event_type FROM network_event_log
           WHERE event_type IN ('DISCONNECT','RECONNECT') ORDER BY created_at DESC, id DESC LIMIT 1"""
    ).fetchone()


def events(db, limit, offset):
    return db.execute(
        """SELECT id, event_type, gap_identifier, record_count, duration_s, detail, created_at
           FROM network_event_log ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()


def pending_sync(db, limit, offset):
    """Queued visits, shaped for the 'Embedded Screening Display' table."""
    return db.execute(
        """SELECT p.patient_code,
                  ls.fbs_mg_dl,
                  COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk,
                  q.sync_status, q.offline_created_at, q.gap_identifier
           FROM sync_queue_log q
           JOIN visits v ON v.id = q.visit_id
           JOIN patients p ON p.id = v.patient_id AND p.deleted_at IS NULL AND p.anonymized_at IS NULL
           LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
           WHERE q.sync_status IN ('QUEUED','FAILED')
           ORDER BY q.offline_created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()


def recent_sync_rows(db, limit):
    """Mixed queued + recently synced rows for the table (newest first)."""
    return db.execute(
        """SELECT p.patient_code, ls.fbs_mg_dl,
                  COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk,
                  q.sync_status, q.offline_created_at
           FROM sync_queue_log q
           JOIN visits v ON v.id = q.visit_id
           JOIN patients p ON p.id = v.patient_id AND p.deleted_at IS NULL AND p.anonymized_at IS NULL
           LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
           ORDER BY q.offline_created_at DESC LIMIT ?""", (limit,)
    ).fetchall()


def pending_counts(db):
    r = db.execute(
        """SELECT COUNT(*) AS screenings,
                  COUNT(DISTINCT v.patient_id) AS patients,
                  COUNT(ls.id) AS assessments
           FROM sync_queue_log q
           JOIN visits v ON v.id = q.visit_id
           JOIN patients p ON p.id = v.patient_id AND p.deleted_at IS NULL AND p.anonymized_at IS NULL
           LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
           WHERE q.sync_status IN ('QUEUED','FAILED')"""
    ).fetchone()
    return r


def sync_summary(db):
    return db.execute(
        """SELECT COALESCE(SUM(sync_status='QUEUED'),0) AS queued,
                  COALESCE(SUM(sync_status='SYNCED'),0) AS synced,
                  COALESCE(SUM(sync_status='FAILED'),0) AS failed,
                  MAX(synced_at) AS last_synced_at
           FROM sync_queue_log"""
    ).fetchone()


def enqueue_visit(db, visit_id, offline_created_at, gap_identifier=None):
    db.execute(
        """INSERT OR IGNORE INTO sync_queue_log (visit_id, offline_created_at, gap_identifier)
           VALUES (?,?,?)""", (visit_id, offline_created_at, gap_identifier))


def mark_synced(db, visit_id):
    db.execute("""UPDATE sync_queue_log SET sync_status='SYNCED', synced_at=CURRENT_TIMESTAMP,
                  attempts = attempts + 1, last_error = NULL WHERE visit_id = ?""", (visit_id,))


def mark_failed(db, visit_id, error):
    db.execute("""UPDATE sync_queue_log SET sync_status='FAILED', attempts = attempts + 1,
                  last_error = ? WHERE visit_id = ?""", (str(error)[:300], visit_id))


def log_event(db, event_type, gap_identifier=None, record_count=None, duration_s=None,
              detail=None, created_at=None):
    """Append one row to the event stream. `created_at` (UTC 'YYYY-MM-DD HH:MM:SS') lets the
    monitor back-date a transition to the first failed/successful probe."""
    cols = ["event_type", "gap_identifier", "record_count", "duration_s", "detail"]
    vals = [event_type, gap_identifier, record_count, duration_s, detail]
    if created_at:
        cols.append("created_at")
        vals.append(created_at)
    db.execute(f"INSERT INTO network_event_log ({', '.join(cols)}) "
               f"VALUES ({', '.join('?' * len(cols))})", vals)


def gap_record_count(db, gap_identifier):
    return db.execute("SELECT COUNT(*) FROM sync_queue_log WHERE gap_identifier = ?",
                      (gap_identifier,)).fetchone()[0]


def recent_inferences(db, limit):
    return db.execute(
        """SELECT created_at, inference_latency_ms, cpu_utilization_pct, ram_utilization_mb,
                  power_draw_w, energy_consumed_kwh, carbon_emissions_kg, measurement_method
           FROM green_computing_log ORDER BY created_at DESC, id DESC LIMIT ?""", (limit,)
    ).fetchall()


# ---- key/value helpers for service state (app_settings) ------------------------------------

def get_kv(db, key, default=None):
    row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_kv(db, key, value):
    db.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


# ---- paginated "View all" queries ----------------------------------------------------------------

EVENT_TYPES = ("DISCONNECT", "RECONNECT", "SYNC_START", "SYNC_COMPLETE", "SYNC_FAILED")
SYNC_FILTERS = {"pending": "q.sync_status IN ('QUEUED','FAILED')",
                "synced": "q.sync_status = 'SYNCED'",
                "all": "1 = 1"}


def events_page(db, limit, offset, event_type=None):
    where, params = ("WHERE event_type = ?", (event_type,)) if event_type else ("", ())
    total = db.execute(f"SELECT COUNT(*) FROM network_event_log {where}", params).fetchone()[0]
    rows = db.execute(
        f"""SELECT id, event_type, gap_identifier, record_count, duration_s, detail, created_at
            FROM network_event_log {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
        params + (limit, offset)).fetchall()
    return rows, total


def sync_rows_page(db, status, limit, offset):
    """Queue rows joined to patient/screening data. `status` is a key of SYNC_FILTERS."""
    cond = SYNC_FILTERS[status]
    base = f"""FROM sync_queue_log q
               JOIN visits v ON v.id = q.visit_id
               JOIN patients p ON p.id = v.patient_id AND p.deleted_at IS NULL AND p.anonymized_at IS NULL
               LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
               WHERE {cond}"""
    total = db.execute(f"SELECT COUNT(*) {base}").fetchone()[0]
    rows = db.execute(
        f"""SELECT p.patient_code, ls.fbs_mg_dl,
                   COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk,
                   q.sync_status, q.offline_created_at, q.synced_at, q.gap_identifier,
                   q.attempts, q.last_error
            {base} ORDER BY q.offline_created_at DESC, q.id DESC LIMIT ? OFFSET ?""",
        (limit, offset)).fetchall()
    return rows, total


def queued_for_flush(db, limit, gap_identifier=None):
    """Oldest-first batch of records still waiting to be handed to the sync transport."""
    cond, params = "sync_status IN ('QUEUED','FAILED')", []
    if gap_identifier:
        cond += " AND gap_identifier = ?"
        params.append(gap_identifier)
    return db.execute(
        f"""SELECT visit_id, offline_created_at, gap_identifier, attempts FROM sync_queue_log
            WHERE {cond} ORDER BY offline_created_at, id LIMIT ?""", (*params, limit)).fetchall()
