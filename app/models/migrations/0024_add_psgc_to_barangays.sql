-- 0024_add_psgc_to_barangays.sql
--
-- Why: 0001_create_barangays.sql defined barangays as (id, name UNIQUE)
-- with no city/region column, and only seeded Santa Rosa's 18 barangays.
-- That only worked because barangay NAMES happened to be unique within
-- that one city. nurse_intake.js has since moved to a full region ->
-- city -> barangay PSGC cascade, and barangay names are NOT unique
-- nationwide (e.g. multiple cities each have a "San Isidro" or "Santo
-- Domingo" barangay) -- see the comment at the top of nurse_intake.js.
-- Resolving by name alone across regions will either violate the old
-- UNIQUE(name) constraint or silently attach a patient to the wrong
-- barangay.
--
-- This migration adds barangay_code/city_code/city_name/region_code/
-- region_name columns and makes barangay_code (the PSGC code, which IS
-- globally unique) the identifier instead of name.
--
-- SQLite cannot ALTER/DROP a column constraint in place, so the table is
-- rebuilt. Existing rows' `id` values are preserved exactly so that
-- patients.barangay_id foreign keys are untouched; their new code/city/
-- region columns are left NULL until backfilled (see note below).

PRAGMA foreign_keys=OFF;

CREATE TABLE barangays_new (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    barangay_code TEXT UNIQUE,   -- PSGC code; NULL for legacy/manual-entry rows
    city_code     TEXT,
    city_name     TEXT,
    region_code   TEXT,
    region_name   TEXT
);

INSERT INTO barangays_new (id, name)
SELECT id, name FROM barangays;

DROP TABLE barangays;
ALTER TABLE barangays_new RENAME TO barangays;

PRAGMA foreign_keys=ON;

-- NOTE (manual step, not part of this migration):
-- The 18 rows copied over above still have NULL barangay_code/city_code/
-- region_code. They'll keep working for existing patients (barangay_id
-- is untouched), and get_or_create_barangay_by_name() in lookup_model.py
-- still resolves them by name for the manual-entry fallback. If you want
-- them to also resolve through the new region/city/barangay dropdowns
-- (so a nurse picking "Aplaya" from the Santa Rosa cascade reuses this
-- same row instead of creating a duplicate), run a one-time backfill that
-- matches these 18 names against data/psgc_data.json's Santa Rosa City
-- entry and UPDATEs barangay_code/city_code/city_name/region_code/
-- region_name accordingly.
