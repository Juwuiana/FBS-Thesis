-- Replace the legacy audit_log from 0002/0011 with the shared audit trail.
ALTER TABLE audit_log RENAME TO audit_log_legacy;

CREATE TABLE audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name    TEXT NOT NULL,
    role         TEXT NOT NULL,
    action       TEXT NOT NULL,
    ip_address   TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'Info'
                   CHECK (severity IN ('Info', 'Warning', 'Success', 'Critical')),
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);

INSERT INTO audit_log (user_id, user_name, role, action, ip_address, severity, created_at)
SELECT NULL, 'unknown', 'Unknown', action, 'unknown', 'Info', created_at
FROM audit_log_legacy;

DROP TABLE audit_log_legacy;