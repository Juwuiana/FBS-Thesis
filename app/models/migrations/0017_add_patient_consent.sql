-- 0017_add_patient_consent.sql
-- data-sharing consent, patient-controlled from the portal

ALTER TABLE patients ADD COLUMN consent_research INTEGER NOT NULL DEFAULT 1;