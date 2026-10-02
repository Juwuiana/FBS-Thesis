CREATE TABLE patient_fbs_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    visit_id INTEGER REFERENCES visits(id),
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
CREATE INDEX idx_pfe_patient ON patient_fbs_entries(patient_id, entered_at DESC);
CREATE INDEX idx_pfe_visit ON patient_fbs_entries(visit_id);