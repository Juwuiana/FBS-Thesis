-- 0009_create_model_performance_logs.sql
-- Stores per-model evaluation results (Random Forest / XGBoost / LightGBM)
-- for the Model Reliability & Prediction Dashboard.

CREATE TABLE IF NOT EXISTS model_performance_logs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,

    model_name                  TEXT NOT NULL,   -- 'Random Forest' | 'XGBoost' | 'LightGBM'
    is_best                     INTEGER NOT NULL DEFAULT 0,
    is_placeholder              INTEGER NOT NULL DEFAULT 1,  -- 0 once real training results replace this row

    accuracy                    REAL NOT NULL,
    precision_score              REAL NOT NULL,
    recall_score                 REAL NOT NULL,
    f1_score                     REAL NOT NULL,
    roc_auc                      REAL NOT NULL,

    cm_tn                        INTEGER NOT NULL,
    cm_fp                        INTEGER NOT NULL,
    cm_fn                        INTEGER NOT NULL,
    cm_tp                        INTEGER NOT NULL,
    test_set_size                 INTEGER NOT NULL,

    roc_curve_points              TEXT,
    feature_importance            TEXT,

    cv_fold_scores                 TEXT,
    cv_mean_auc                    REAL,
    cv_std_auc                     REAL,
    cv_min_auc                     REAL,
    cv_max_auc                     REAL,

    optimization_technique          TEXT,
    serialized_model_size_kb         REAL,
    avg_inference_latency_ms          REAL,
    target_device                      TEXT,

    training_source                     TEXT,
    total_records                        INTEGER,
    diabetic_count                        INTEGER,
    non_diabetic_count                     INTEGER,
    train_split_pct                         INTEGER,
    test_split_pct                           INTEGER,
    primary_feature                           TEXT,

    evaluated_at                               TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_model_performance_logs_best ON model_performance_logs(is_best);