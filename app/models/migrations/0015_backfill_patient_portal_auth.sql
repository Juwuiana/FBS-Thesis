-- 0015_backfill_patient_portal_auth.sql
-- 0014 was recorded as applied while still empty (created before its
-- content was written), so the migration runner will never re-run it.
-- This re-issues the same columns under a new migration number instead
-- of editing 0014, per the "never edit an already-applied migration" rule.

ALTER TABLE patients ADD COLUMN password_hash TEXT;
ALTER TABLE patients ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 1;
ALTER TABLE patients ADD COLUMN portal_activated_at TEXT;
ALTER TABLE patients ADD COLUMN credentials_issued_by_staff_id INTEGER REFERENCES users(id);
ALTER TABLE patients ADD COLUMN credentials_issued_at TEXT;