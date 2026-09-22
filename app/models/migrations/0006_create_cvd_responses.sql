-- 0006_create_cvd_responses.sql


CREATE TABLE IF NOT EXISTS cvd_responses (
    visit_id                    INTEGER PRIMARY KEY REFERENCES visits(id) ON DELETE CASCADE,
    q1_chest_discomfort         INTEGER NOT NULL DEFAULT 0,   
    q2_pain_center_left_arm     INTEGER NOT NULL DEFAULT 0,
    q3_occurs_uphill_hurrying   INTEGER NOT NULL DEFAULT 0,
    q4_slows_down_if_occurs     INTEGER NOT NULL DEFAULT 0,
    q5_relieved_by_rest_tablet  INTEGER NOT NULL DEFAULT 0,
    q6_relieved_under_10min     INTEGER NOT NULL DEFAULT 0,
    q7_severe_pain_30min_plus   INTEGER NOT NULL DEFAULT 0,
    q8_tia_stroke_symptoms      INTEGER NOT NULL DEFAULT 0    
);
