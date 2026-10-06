-- 0035_add_patient_email.sql
-- One row per person
ALTER TABLE patients ADD COLUMN email TEXT;
