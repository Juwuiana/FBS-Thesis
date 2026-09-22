-- 0005_create_condition_catalog.sql


CREATE TABLE IF NOT EXISTS condition_catalog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL CHECK (category IN
                    ('pmh','family_history','diet','immunization','dm_symptom')),
    code        TEXT NOT NULL,
    UNIQUE (category, code)
);

CREATE TABLE IF NOT EXISTS visit_conditions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id        INTEGER NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
    condition_id    INTEGER NOT NULL REFERENCES condition_catalog(id),
    UNIQUE (visit_id, condition_id)
);

CREATE INDEX IF NOT EXISTS idx_visit_conditions_visit ON visit_conditions(visit_id);
CREATE INDEX IF NOT EXISTS idx_visit_conditions_condition ON visit_conditions(condition_id);

-- past med history 
INSERT OR IGNORE INTO condition_catalog (category, code) VALUES
('pmh','Allergy'), ('pmh','Asthma'), ('pmh','Cancer'),
('pmh','Cerebrovascular Disease'), ('pmh','Coronary Artery Disease'),
('pmh','Diabetes Mellitus'), ('pmh','Emphysema'), ('pmh','Epilepsy/Seizure Disease'),
('pmh','Hepatitis'), ('pmh','Hyperlipidemia'), ('pmh','Hypertension'),
('pmh','Peptic Ulcer Disease'), ('pmh','Pneumonia'), ('pmh','Thyroid Disease'),
('pmh','Tuberculosis'), ('pmh','Urinary Tract Infection');

-- fam history
INSERT OR IGNORE INTO condition_catalog (category, code) VALUES
('family_history','Hypertension'), ('family_history','Stroke/Cerebrovascular Disease'),
('family_history','Coronary Artery Disease'), ('family_history','Diabetes Mellitus'),
('family_history','Asthma'), ('family_history','Cancer'), ('family_history','Kidney Disease');

-- diet
INSERT OR IGNORE INTO condition_catalog (category, code) VALUES
('diet','High Fat/Salt'), ('diet','3+ servings vegetables daily'),
('diet','2-3 servings fruits daily');

-- immunization
INSERT OR IGNORE INTO condition_catalog (category, code) VALUES
('immunization','BCG'), ('immunization','OPV/IPV Series'), ('immunization','DPT Series'),
('immunization','Measles'), ('immunization','Hepatitis A/B Series'), ('immunization','HPV'),
('immunization','MMR'), ('immunization','Tetanus Toxoid'),
('immunization','Pneumococcal Vaccine'), ('immunization','Flu Vaccine');

-- symptoms
INSERT OR IGNORE INTO condition_catalog (category, code) VALUES
('dm_symptom','Polyphagia'), ('dm_symptom','Polydipsia'), ('dm_symptom','Polyuria');
