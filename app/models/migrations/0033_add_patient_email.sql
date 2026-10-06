-- 0033: add an optional email address to patients.
-- One row per person
ALTER TABLE patients ADD COLUMN email TEXT;
