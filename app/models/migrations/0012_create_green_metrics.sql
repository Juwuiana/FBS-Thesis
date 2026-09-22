-- 0012_create_green_metrics.sql
--
-- Green-computing tables (Appendix G, adapted to the real schema).
-- Conventions match 0001-0011: INTEGER ids, UTC timestamps stored as
-- 'YYYY-MM-DD HH:MM:SS' (CURRENT_TIMESTAMP). Convert to local time only when displaying.
--
-- The thesis's "Risk_Assessment" is not a separate table here: the model's output lives in
-- lab_screenings.model_predicted_risk_level / model_confidence, so the log points at
-- lab_screenings. The link is nullable and ON DELETE SET NULL because the model runs
-- before the screening is saved, and energy history must survive a record being deleted.
-- None of these tables hold patient data.
--
-- Copy this file to the nurse/patient branch in the same commit (see README).

-- One row per model inference.
CREATE TABLE IF NOT EXISTS green_computing_log (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_screening_id      INTEGER REFERENCES lab_screenings(id) ON DELETE SET NULL,
    inference_latency_ms  REAL NOT NULL,
    cpu_utilization_pct   REAL,
    ram_utilization_mb    REAL,
    power_draw_w          REAL,
    energy_consumed_kwh   REAL NOT NULL,
    carbon_emissions_kg   REAL NOT NULL,
    -- Time spent in the whole request and in database work; used to split energy by
    -- component (power_draw_w x time in each component).
    request_ms            REAL,
    db_io_ms              REAL,
    -- 'battery'   = read from the phone's battery nodes
    -- 'estimated' = CPU-share x TDP fallback (nodes unreadable)
    -- 'seeded'    = demo data from scripts/seed_green_demo.py
    measurement_method    TEXT NOT NULL CHECK (measurement_method IN ('battery','estimated','seeded')),
    created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_green_log_created ON green_computing_log(created_at);
CREATE INDEX IF NOT EXISTS idx_green_log_lab ON green_computing_log(lab_screening_id);

-- Periodic device samples (default every 60 s): idle power, uptime, power source.
CREATE TABLE IF NOT EXISTS system_telemetry_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    battery_level_pct  REAL,
    battery_temp_c     REAL,
    power_w            REAL,
    is_idle            INTEGER NOT NULL DEFAULT 0,
    power_source       TEXT CHECK (power_source IN ('BATTERY','AC_CHARGING','SOLAR_UPS')),
    recorded_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_telemetry_recorded ON system_telemetry_log(recorded_at);

-- Visits waiting to be (or already) synced after an offline gap.
CREATE TABLE IF NOT EXISTS sync_queue_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id            INTEGER NOT NULL UNIQUE REFERENCES visits(id) ON DELETE CASCADE,
    sync_status         TEXT NOT NULL DEFAULT 'QUEUED' CHECK (sync_status IN ('QUEUED','SYNCED','FAILED')),
    offline_created_at  TEXT NOT NULL,
    synced_at           TEXT,
    gap_identifier      TEXT,
    attempts            INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue_log(sync_status);
CREATE INDEX IF NOT EXISTS idx_sync_queue_gap ON sync_queue_log(gap_identifier);

-- Append-only stream behind the Events Log, the connectivity timeline and offline gaps.
-- A gap is a DISCONNECT and the RECONNECT that shares its gap_identifier.
CREATE TABLE IF NOT EXISTS network_event_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL CHECK (event_type IN
                        ('DISCONNECT','RECONNECT','SYNC_START','SYNC_COMPLETE','SYNC_FAILED')),
    gap_identifier  TEXT,
    record_count    INTEGER,
    duration_s      REAL,
    detail          TEXT,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_network_events_created ON network_event_log(created_at);
