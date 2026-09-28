-- 0025_backfill_santa_rosa_psgc_codes.sql
--
-- Finishes the manual step flagged in 0024_add_psgc_to_barangays.sql:
-- sets barangay_code/city_code/city_name/region_code/region_name on the
-- 18 legacy rows 0001_create_barangays.sql seeded, using the real codes
-- from data/psgc_data.json:
--   City of Santa Rosa (Laguna) = 0403428000
--   Region IV-A (CALABARZON)    = 0400000000
--
-- Matched by exact name, scoped to `barangay_code IS NULL` -- safe only
-- because these 18 rows are the only ones that can still have a NULL
-- code at this point (every row created since 0024 via
-- get_or_create_barangay()/get_or_create_barangay_by_code() always sets
-- one). Names below are copied verbatim from 0001_create_barangays.sql,
-- including the "(Poblacion)" suffix on Market Area -- do not "clean up"
-- to match psgc_data.json's bare "Market Area", or the WHERE clause
-- won't match.

UPDATE barangays SET barangay_code='0403428001', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Aplaya' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428002', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Balibago' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428003', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Caingin' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428004', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Dila' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428005', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Dita' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428006', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Don Jose' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428007', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Ibaba' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428015', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Kanluran' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428008', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Labas' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428009', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Macabling' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428010', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Malitlit' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428011', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Malusak' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428012', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Market Area (Poblacion)' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428016', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Pooc' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428018', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Pulong Santa Cruz' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428020', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Santo Domingo' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428022', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Sinalhan' AND barangay_code IS NULL;
UPDATE barangays SET barangay_code='0403428023', city_code='0403428000', city_name='City of Santa Rosa', region_code='0400000000', region_name='Region IV-A (CALABARZON)' WHERE name='Tagapo' AND barangay_code IS NULL;
