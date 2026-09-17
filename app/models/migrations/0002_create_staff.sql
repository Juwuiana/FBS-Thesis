-- 0002_create_staff.sql


CREATE TABLE IF NOT EXISTS staff (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    username        TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('nurse', 'admin')),
    facility        TEXT DEFAULT 'Santa Rosa City Health Office',
    avatar_path     TEXT,               -- replaces the localStorage-only
                                         -- avatar in nurse_base.html
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id    INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    event       TEXT NOT NULL CHECK (event IN ('login_success', 'login_failed', 'logout')),
    ip_address  TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Recent Account Activity
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id    INTEGER REFERENCES staff(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,      -- e.g. "Downloaded clinical summary PDF"
    detail      TEXT,               -- e.g. "Barangay Risk Statistics"
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
