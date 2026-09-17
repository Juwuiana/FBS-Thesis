-- 0010_create_app_settings.sql
-- Key/value store for site-wide settings (currently just the session
-- timeout configured on the Privacy & Security admin page).

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
