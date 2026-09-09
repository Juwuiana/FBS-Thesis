-- 0007_create_lab_screenings.sql


CREATE TABLE IF NOT EXISTS lab_screenings (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id                    INTEGER NOT NULL UNIQUE REFERENCES visits(id) ON DELETE CASCADE,

    fbs_mg_dl                   REAL NOT NULL,
    test_method                 TEXT NOT NULL DEFAULT 'Capillary (Fingerprick)',
    glucometer_id                TEXT,
    test_datetime                TEXT NOT NULL,

    preliminary_risk_level       TEXT CHECK (preliminary_risk_level IN ('Low','Moderate','High')),
    preliminary_score            INTEGER,

    model_predicted_risk_level   TEXT CHECK (model_predicted_risk_level IN
                                    ('Normal','Pre-Diabetic','Diabetic')),
    model_confidence              REAL,

    final_risk_level              TEXT CHECK (final_risk_level IN ('Low','Moderate','High')),
    override_by_staff_id          INTEGER REFERENCES staff(id),

    -- pre screening checklist
    fasted_ge_8h                  INTEGER NOT NULL DEFAULT 0,
    identity_verified             INTEGER NOT NULL DEFAULT 0,
    glucometer_calibrated         INTEGER NOT NULL DEFAULT 0,
    capillary_sample_taken        INTEGER NOT NULL DEFAULT 0,
    consent_signed                 INTEGER NOT NULL DEFAULT 0,
    result_recorded_within_5min    INTEGER NOT NULL DEFAULT 0,

    referral_action                 TEXT,
    follow_up_date                  TEXT,
    referred_to                     TEXT,

    created_at                       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lab_screenings_visit ON lab_screenings(visit_id);
