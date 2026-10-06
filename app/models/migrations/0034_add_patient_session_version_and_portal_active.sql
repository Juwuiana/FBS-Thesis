-- 0034_add_patient_session_version_and_portal_active.sql
ALTER TABLE patients ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE patients ADD COLUMN portal_active INTEGER NOT NULL DEFAULT 1;
