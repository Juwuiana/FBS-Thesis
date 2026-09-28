-- Adds maiden name / married name for female patients. Both nullable text

ALTER TABLE patients ADD COLUMN maiden_name TEXT;
ALTER TABLE patients ADD COLUMN married_name TEXT;
