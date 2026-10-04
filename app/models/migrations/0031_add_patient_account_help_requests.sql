-- 0027_add_patient_account_help_requests.sql
-- Lets a locked-out patient flag their own account 
ALTER TABLE patients ADD COLUMN account_help_requested_at TEXT;
ALTER TABLE patients ADD COLUMN account_help_reason TEXT;
ALTER TABLE patients ADD COLUMN account_help_resolved_at TEXT;
ALTER TABLE patients ADD COLUMN account_help_resolved_by_staff_id INTEGER REFERENCES users(id);
