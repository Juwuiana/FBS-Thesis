-- 0032_patient_fbs_entries.sql
-- Patient self-reported FBS readings. ON DELETE CASCADE so the retention
-- 'delete' action and recycle-bin purge (DELETE FROM patients) don't hit FK errors.
CREATE TABLE IF NOT EXISTS patient_fbs_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    visit_id INTEGER REFERENCES visits(id) ON DELETE CASCADE,
    fbs_mg_dl REAL NOT NULL,
    entered_value REAL NOT NULL,
    entered_unit TEXT NOT NULL CHECK (entered_unit IN ('mg_dl','mmol_l')),
    fasted TEXT NOT NULL CHECK (fasted IN ('yes','no','unsure')),
    review_status TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (review_status IN ('unreviewed','reviewed','flagged')),
    reviewed_by_staff_id INTEGER,
    reviewed_at TEXT,
    entered_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_pfe_patient ON patient_fbs_entries(patient_id, entered_at DESC);
CREATE INDEX IF NOT EXISTS idx_pfe_visit ON patient_fbs_entries(visit_id);
