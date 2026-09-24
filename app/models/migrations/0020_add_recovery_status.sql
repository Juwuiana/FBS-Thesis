-- Widen users.status to support administrator-mediated password recovery.
PRAGMA foreign_keys = OFF;

CREATE TABLE users_new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name     TEXT NOT NULL,
    middle_name    TEXT,
    last_name      TEXT NOT NULL,
    birthday       TEXT NOT NULL,
    sex            TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    email          TEXT NOT NULL UNIQUE,
    phone          TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('health_worker', 'medical_officer')),
    facility       TEXT NOT NULL,
    barangay       TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'approved', 'rejected', 'recovery')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at  TEXT
);

INSERT INTO users_new (
    id, first_name, middle_name, last_name, birthday, sex,
    email, phone, role, facility, barangay, password_hash, status,
    created_at, last_login_at
)
SELECT
    id, first_name, middle_name, last_name, birthday, sex,
    email, phone, role, facility, barangay, password_hash, status,
    created_at, last_login_at
FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

PRAGMA foreign_keys = ON;