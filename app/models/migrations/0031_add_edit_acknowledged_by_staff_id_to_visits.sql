-- 0031_add_edit_acknowledged_by_staff_id_to_visits.sql
-- Track which staff member acknowledged a patient's pending visit edit.

ALTER TABLE visits ADD COLUMN edit_acknowledged_by_staff_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_visits_pending_edit_acknowledgement
    ON visits(edit_acknowledged_by_staff_id)
    WHERE edit_acknowledged_by_staff_id IS NOT NULL;
