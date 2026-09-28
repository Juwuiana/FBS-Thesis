-- 0026_add_barangay_id_to_users.sql
--
-- Staff accounts (signup.html / admin's Add Staff) previously stored
-- users.barangay as a free-text slug ("aplaya", "market_area", ...)
-- validated against the hardcoded app.constants.BARANGAYS whitelist --
-- entirely separate from the barangays table patients use, and unable to
-- represent anything outside the original 18 Santa Rosa barangays.
--
-- This adds barangay_id, mirroring patients.barangay_id, so staff can now
-- resolve through the same PSGC-code-based barangays table (see
-- lookup_model.get_or_create_barangay). The legacy `barangay` text column
-- is left in place (untouched, still readable) rather than dropped --
-- SQLite can't cheaply drop a column without a full table rebuild, and
-- this repo's users table has accumulated many ALTER TABLEs since
-- 0009_create_users.sql that aren't all visible here, so rebuilding it
-- blind is riskier than leaving one unused column behind.

ALTER TABLE users ADD COLUMN barangay_id INTEGER REFERENCES barangays(id);

-- Backfill existing rows from their legacy slug onto the matching
-- (now PSGC-coded, see 0025) barangays row. Slugs below are copied
-- verbatim from signup.html's hardcoded <option value="..."> list.
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Aplaya') WHERE barangay = 'aplaya' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Balibago') WHERE barangay = 'balibago' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Caingin') WHERE barangay = 'caingin' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Dila') WHERE barangay = 'dila' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Dita') WHERE barangay = 'dita' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Don Jose') WHERE barangay = 'don_jose' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Ibaba') WHERE barangay = 'ibaba' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Kanluran') WHERE barangay = 'kanluran' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Labas') WHERE barangay = 'labas' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Macabling') WHERE barangay = 'macabling' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Malitlit') WHERE barangay = 'malitlit' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Malusak') WHERE barangay = 'malusak' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Market Area (Poblacion)') WHERE barangay = 'market_area' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Pooc') WHERE barangay = 'pooc' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Pulong Santa Cruz') WHERE barangay = 'pulong_santa_cruz' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Santo Domingo') WHERE barangay = 'santo_domingo' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Sinalhan') WHERE barangay = 'sinalhan' AND barangay_id IS NULL;
UPDATE users SET barangay_id = (SELECT id FROM barangays WHERE name = 'Tagapo') WHERE barangay = 'tagapo' AND barangay_id IS NULL;
