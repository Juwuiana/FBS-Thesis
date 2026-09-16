-- 0004_create_visits.sql


CREATE TABLE IF NOT EXISTS visits (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id              INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    visit_type              TEXT NOT NULL CHECK (visit_type IN ('intake','follow_up')),
    assessment_date         TEXT NOT NULL,       
    recorded_by_staff_id    INTEGER REFERENCES staff(id),

    smoking_status          TEXT CHECK (smoking_status IN
                                ('Never smoked','Stopped > 1 year','Current Smoker',
                                 'Stopped < 1 year','Passive Smoker')),
    alcohol_intake          TEXT CHECK (alcohol_intake IN
                                ('Never Consumed','Yes',
                                 'Yes (Binge: 5+ drinks in one occasion past month)')),
    illicit_drug_use        TEXT CHECK (illicit_drug_use IN ('No','Yes')),
    physical_activity       TEXT CHECK (physical_activity IN
                                ('Does NOT meet 2.5 hours/week',
                                 'Meets at least 2.5 hours/week moderate activity')),

    past_surgical_history   TEXT,
    diabetes_diagnosis      TEXT CHECK (diabetes_diagnosis IN
                                ('No / Do not know','Yes (with medications)',
                                 'Yes (without medications)')),

    bp_systolic             INTEGER,
    bp_diastolic            INTEGER,
    heart_rate              INTEGER,
    respiratory_rate        INTEGER,
    height_cm               REAL,
    weight_kg                REAL,
    waist_cm                REAL,
    bmi                     REAL,      
       
    obesity_class           TEXT,
    pe_skin                 TEXT,
    pe_heent                TEXT,
    pe_chest                TEXT,
    pe_heart                TEXT,
    pe_abdomen               TEXT,
    pe_extremities           TEXT,

    menarche_age            INTEGER,
    lmp_date                TEXT,
    gravida                 INTEGER,
    para                    INTEGER,

    clinical_notes           TEXT,
    status                   TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted')),
    created_at                TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id, assessment_date);
