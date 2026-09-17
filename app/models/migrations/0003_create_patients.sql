-- 0003_create_patients.sql

CREATE TABLE IF NOT EXISTS patients (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_code        TEXT NOT NULL UNIQUE,   

    last_name           TEXT NOT NULL,
    first_name          TEXT NOT NULL,
    middle_name         TEXT,

    father_last_name    TEXT,
    father_first_name   TEXT,
    mother_last_name    TEXT,
    mother_first_name   TEXT,
    spouse_last_name    TEXT,
    spouse_first_name   TEXT,
    contact_number      TEXT,

    birthdate           TEXT NOT NULL,           -- ISO 'YYYY-MM-DD'
    sex                 TEXT NOT NULL CHECK (sex IN ('Male', 'Female')),
    civil_status        TEXT CHECK (civil_status IN
                            ('Single','Married','Annulled','Widow/Widower','Separated')),
    religion            TEXT,
    occupation          TEXT,
    education           TEXT CHECK (education IN
                            ('No Schooling','Elementary','High School','Vocational',
                             'College degree, post graduate')),
    barangay_id         INTEGER REFERENCES barangays(id),
    address             TEXT,

    phic_membership     TEXT CHECK (phic_membership IN ('Member','Dependent','Non-Member')),
    phic_type           TEXT,

    created_by_staff_id INTEGER REFERENCES staff(id),
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patients_barangay ON patients(barangay_id);
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(last_name, first_name);
