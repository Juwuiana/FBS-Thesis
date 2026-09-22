-- recycle bin

ALTER TABLE patients ADD COLUMN deleted_at TEXT;

CREATE INDEX IF NOT EXISTS idx_patients_deleted_at ON patients(deleted_at);