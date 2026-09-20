-- 0011_unify_accounts_on_users.sql
--
-- `users` becomes the single accounts table. Every FK that pointed at
-- staff(id) is repointed at users(id), and `staff` is dropped.
--
-- Why the columns are still called *_staff_id: renaming them would mean
-- editing every INSERT in the nurse-branch models for no schema benefit.
-- Read "staff_id" as "users.id of the staff member who did this".
--
-- Any rows in `staff` are carried into `users` with their id preserved, so
-- existing FK values stay valid. Fields `users` requires that `staff` never
-- had (birthday, sex, phone, barangay) get obvious placeholders, and status
-- is 'pending' so a carried-over account cannot log in until an admin fills
-- the real values in and approves it. If an id or email already exists in
-- `users`, this migration fails loudly rather than guessing -- reconcile the
-- clash by hand and run it again. (As of writing, `staff` is empty on both
-- branches, so this is a safety net, not a data move.)
--
-- SQLite cannot ALTER a foreign key, so each referencing table is rebuilt
-- using the documented create-new / copy / drop-old / rename procedure.

PRAGMA foreign_keys = OFF;

-- 1. Carry any staff rows over to users, keeping their ids. -----------------

INSERT INTO users (
    id, first_name, middle_name, last_name, birthday, sex,
    email, phone, role, facility, barangay, password_hash, status, created_at
)
SELECT
    s.id,
    TRIM(SUBSTR(s.full_name, 1, INSTR(s.full_name || ' ', ' ') - 1)),
    NULL,
    CASE
        WHEN TRIM(SUBSTR(s.full_name, INSTR(s.full_name || ' ', ' '))) = ''
            THEN '(unknown)'
        ELSE TRIM(SUBSTR(s.full_name, INSTR(s.full_name || ' ', ' ')))
    END,
    '1900-01-01',                       -- placeholder, staff had no birthday
    'male',                             -- placeholder, staff had no sex
    s.email,
    '0000000000',                       -- placeholder, staff had no phone
    CASE s.role WHEN 'admin' THEN 'medical_officer' ELSE 'health_worker' END,
    COALESCE(s.facility, 'rhui'),
    'unassigned',                       -- placeholder, staff had no barangay
    s.password_hash,
    'pending',
    s.created_at
FROM staff s;

-- 2. login_events ----------------------------------------------------------

CREATE TABLE login_events_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    event       TEXT NOT NULL CHECK (event IN ('login_success', 'login_failed', 'logout')),
    ip_address  TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO login_events_new (id, staff_id, event, ip_address, created_at)
SELECT id, staff_id, event, ip_address, created_at FROM login_events;

DROP TABLE login_events;
ALTER TABLE login_events_new RENAME TO login_events;

-- 3. audit_log -------------------------------------------------------------

CREATE TABLE audit_log_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    detail      TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO audit_log_new (id, staff_id, action, detail, created_at)
SELECT id, staff_id, action, detail, created_at FROM audit_log;

DROP TABLE audit_log;
ALTER TABLE audit_log_new RENAME TO audit_log;

-- 4. patients (0003 + deleted_at from 0008) --------------------------------

CREATE TABLE patients_new (
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

    created_by_staff_id INTEGER REFERENCES users(id),
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at          TEXT
);

INSERT INTO patients_new (
    id, patient_code, last_name, first_name, middle_name,
    father_last_name, father_first_name, mother_last_name, mother_first_name,
    spouse_last_name, spouse_first_name, contact_number,
    birthdate, sex, civil_status, religion, occupation, education,
    barangay_id, address, phic_membership, phic_type,
    created_by_staff_id, created_at, updated_at, deleted_at
)
SELECT
    id, patient_code, last_name, first_name, middle_name,
    father_last_name, father_first_name, mother_last_name, mother_first_name,
    spouse_last_name, spouse_first_name, contact_number,
    birthdate, sex, civil_status, religion, occupation, education,
    barangay_id, address, phic_membership, phic_type,
    created_by_staff_id, created_at, updated_at, deleted_at
FROM patients;

DROP TABLE patients;
ALTER TABLE patients_new RENAME TO patients;

CREATE INDEX IF NOT EXISTS idx_patients_barangay ON patients(barangay_id);
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_patients_deleted_at ON patients(deleted_at);

-- 5. visits ----------------------------------------------------------------

CREATE TABLE visits_new (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id              INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    visit_type              TEXT NOT NULL CHECK (visit_type IN ('intake','follow_up')),
    assessment_date         TEXT NOT NULL,
    recorded_by_staff_id    INTEGER REFERENCES users(id),

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
    weight_kg               REAL,
    waist_cm                REAL,
    bmi                     REAL,

    obesity_class           TEXT,
    pe_skin                 TEXT,
    pe_heent                TEXT,
    pe_chest                TEXT,
    pe_heart                TEXT,
    pe_abdomen              TEXT,
    pe_extremities          TEXT,

    menarche_age            INTEGER,
    lmp_date                TEXT,
    gravida                 INTEGER,
    para                    INTEGER,

    clinical_notes          TEXT,
    status                  TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted')),
    created_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO visits_new (
    id, patient_id, visit_type, assessment_date, recorded_by_staff_id,
    smoking_status, alcohol_intake, illicit_drug_use, physical_activity,
    past_surgical_history, diabetes_diagnosis,
    bp_systolic, bp_diastolic, heart_rate, respiratory_rate,
    height_cm, weight_kg, waist_cm, bmi,
    obesity_class, pe_skin, pe_heent, pe_chest, pe_heart, pe_abdomen, pe_extremities,
    menarche_age, lmp_date, gravida, para,
    clinical_notes, status, created_at
)
SELECT
    id, patient_id, visit_type, assessment_date, recorded_by_staff_id,
    smoking_status, alcohol_intake, illicit_drug_use, physical_activity,
    past_surgical_history, diabetes_diagnosis,
    bp_systolic, bp_diastolic, heart_rate, respiratory_rate,
    height_cm, weight_kg, waist_cm, bmi,
    obesity_class, pe_skin, pe_heent, pe_chest, pe_heart, pe_abdomen, pe_extremities,
    menarche_age, lmp_date, gravida, para,
    clinical_notes, status, created_at
FROM visits;

DROP TABLE visits;
ALTER TABLE visits_new RENAME TO visits;

CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id, assessment_date);

-- 6. lab_screenings --------------------------------------------------------

CREATE TABLE lab_screenings_new (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id                    INTEGER NOT NULL UNIQUE REFERENCES visits(id) ON DELETE CASCADE,

    fbs_mg_dl                   REAL NOT NULL,
    test_method                 TEXT NOT NULL DEFAULT 'Capillary (Fingerprick)',
    glucometer_id               TEXT,
    test_datetime               TEXT NOT NULL,

    preliminary_risk_level      TEXT CHECK (preliminary_risk_level IN ('Low','Moderate','High')),
    preliminary_score           INTEGER,

    model_predicted_risk_level  TEXT CHECK (model_predicted_risk_level IN
                                    ('Normal','Pre-Diabetic','Diabetic')),
    model_confidence            REAL,

    final_risk_level            TEXT CHECK (final_risk_level IN ('Low','Moderate','High')),
    override_by_staff_id        INTEGER REFERENCES users(id),

    fasted_ge_8h                INTEGER NOT NULL DEFAULT 0,
    identity_verified           INTEGER NOT NULL DEFAULT 0,
    glucometer_calibrated       INTEGER NOT NULL DEFAULT 0,
    capillary_sample_taken      INTEGER NOT NULL DEFAULT 0,
    consent_signed              INTEGER NOT NULL DEFAULT 0,
    result_recorded_within_5min INTEGER NOT NULL DEFAULT 0,

    referral_action             TEXT,
    follow_up_date              TEXT,
    referred_to                 TEXT,

    created_at                  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lab_screenings_new (
    id, visit_id, fbs_mg_dl, test_method, glucometer_id, test_datetime,
    preliminary_risk_level, preliminary_score,
    model_predicted_risk_level, model_confidence,
    final_risk_level, override_by_staff_id,
    fasted_ge_8h, identity_verified, glucometer_calibrated,
    capillary_sample_taken, consent_signed, result_recorded_within_5min,
    referral_action, follow_up_date, referred_to, created_at
)
SELECT
    id, visit_id, fbs_mg_dl, test_method, glucometer_id, test_datetime,
    preliminary_risk_level, preliminary_score,
    model_predicted_risk_level, model_confidence,
    final_risk_level, override_by_staff_id,
    fasted_ge_8h, identity_verified, glucometer_calibrated,
    capillary_sample_taken, consent_signed, result_recorded_within_5min,
    referral_action, follow_up_date, referred_to, created_at
FROM lab_screenings;

DROP TABLE lab_screenings;
ALTER TABLE lab_screenings_new RENAME TO lab_screenings;

CREATE INDEX IF NOT EXISTS idx_lab_screenings_visit ON lab_screenings(visit_id);

-- 7. `staff` has no reason to exist any more. ------------------------------

DROP TABLE staff;
