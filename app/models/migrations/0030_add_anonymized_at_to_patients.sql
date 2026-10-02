-- 0030_add_anonymized_at_to_patients.sql
ALTER TABLE patients ADD COLUMN anonymized_at TEXT;
