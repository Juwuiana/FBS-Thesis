-- 0014_add_patient_portal_auth.sql

ALTER TABLE patients ADD COLUMN password_hash TEXT;
ALTER TABLE patients ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 1;
ALTER TABLE patients ADD COLUMN portal_activated_at TEXT;
ALTER TABLE patients ADD COLUMN credentials_issued_by_staff_id INTEGER REFERENCES users(id);
ALTER TABLE patients ADD COLUMN credentials_issued_at TEXT;