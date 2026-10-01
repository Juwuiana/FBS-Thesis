-- 0025_add_visit_patient_edit_tracking.sql
-- Lets a patient correct vitals on a past visit (HR, RR, weight, height, BP)
-- from the portal, and flags it for nurse review

ALTER TABLE visits ADD COLUMN edited_by_patient_at TEXT;
ALTER TABLE visits ADD COLUMN edited_fields TEXT;              -- JSON array, e.g. ["weight_kg","heart_rate"]
ALTER TABLE visits ADD COLUMN patient_edit_previous_values TEXT; -- JSON {field: old_value}, for the nurse's "before" column
ALTER TABLE visits ADD COLUMN edit_acknowledged_at TEXT;


-- Fast "does this patient have any unacknowledged edits" / nurse bell count
CREATE INDEX IF NOT EXISTS idx_visits_patient_edit_pending
    ON visits(edited_by_patient_at)
    WHERE edited_by_patient_at IS NOT NULL AND edit_acknowledged_at IS NULL;
