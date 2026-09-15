CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name     TEXT NOT NULL,
    middle_name    TEXT,
    last_name      TEXT NOT NULL,
    birthday       TEXT NOT NULL,          -- ISO date, YYYY-MM-DD
    sex            TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    email          TEXT NOT NULL UNIQUE,
    phone          TEXT NOT NULL,          -- 10 digits, e.g. 9171234567 (+63 prefix implied)
    role           TEXT NOT NULL CHECK (role IN ('health_worker', 'medical_officer')),
    facility       TEXT NOT NULL,
    barangay       TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Simple key/value store for site-wide settings (e.g. session timeout)
-- configured from the Privacy & Security admin page.
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
