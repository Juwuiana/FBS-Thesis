-- 0001_create_barangays.sql
-- Lookup table for the 18 barangays referenced in nurse_intake.html,

CREATE TABLE IF NOT EXISTS barangays (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE
);

INSERT OR IGNORE INTO barangays (name) VALUES
    ('Aplaya'), ('Balibago'), ('Caingin'), ('Dila'), ('Dita'),
    ('Don Jose'), ('Ibaba'), ('Kanluran'), ('Labas'), ('Macabling'),
    ('Malitlit'), ('Malusak'), ('Market Area (Poblacion)'), ('Pooc'),
    ('Pulong Santa Cruz'), ('Santo Domingo'), ('Sinalhan'), ('Tagapo');
