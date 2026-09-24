-- 0016_create_patient_login_events.sql
-- Login history for the patient portal (patients table)

CREATE TABLE IF NOT EXISTS patient_login_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    user_agent  TEXT,
    ip_address  TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patient_login_events_patient ON patient_login_events(patient_id, created_at DESC);