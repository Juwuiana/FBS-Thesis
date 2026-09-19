-- 0010_adapt_model_performance_logs_for_multiclass.sql
-- Adapts model_performance_logs (originally shaped for a binary classifier)
-- for the actual 3-class FBS classifier (Normal / Pre-Diabetic / Diabetic).
--
-- Changes:
--   - Dropped: cm_tn, cm_fp, cm_fn, cm_tp (binary-only 2x2 confusion matrix)
--   - Dropped: diabetic_count, non_diabetic_count (binary-only class counts)
--   - Added:   confusion_matrix (JSON TEXT) -- {"labels": [...], "matrix": [[...]]}
--   - Added:   class_counts (JSON TEXT)     -- {"Normal": n, "Pre-Diabetic": n, "Diabetic": n}
--   - Added:   composite_score (REAL)       -- the project's model-selection score
--   - Added:   cv_accuracy, cv_precision_score, cv_recall_score, cv_f1_score (REAL)
--   - Relaxed NOT NULL on accuracy / precision_score / recall_score / f1_score /
--     roc_auc / test_set_size: only the selected model is evaluated on the
--     held-out test set, so candidate models that lost selection carry CV-level
--     metrics only and would otherwise fail these constraints on insert.
--
-- NOTE: this drops cm_tn/cm_fp/cm_fn/cm_tp and diabetic_count/non_diabetic_count
-- data for any existing rows (e.g. placeholder seed rows). If those need to be
-- preserved for reference, export them before running this migration --
-- scripts/seed_model_performance.py will also need updating to match the new
-- column set, since it's what (re)populates placeholder rows today.

PRAGMA foreign_keys=off;

CREATE TABLE model_performance_logs_new (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,

    model_name                  TEXT NOT NULL,
    is_best                     INTEGER NOT NULL DEFAULT 0,
    is_placeholder              INTEGER NOT NULL DEFAULT 1,

    accuracy                    REAL,
    precision_score             REAL,
    recall_score                REAL,
    f1_score                    REAL,
    roc_auc                     REAL,
    test_set_size                INTEGER,

    confusion_matrix              TEXT,
    roc_curve_points               TEXT,
    feature_importance              TEXT,

    cv_fold_scores                   TEXT,
    cv_mean_auc                       REAL,
    cv_std_auc                         REAL,
    cv_min_auc                          REAL,
    cv_max_auc                           REAL,
    cv_accuracy                           REAL,
    cv_precision_score                     REAL,
    cv_recall_score                         REAL,
    cv_f1_score                              REAL,

    composite_score                           REAL,

    optimization_technique                     TEXT,
    serialized_model_size_kb                    REAL,
    avg_inference_latency_ms                     REAL,
    target_device                                 TEXT,

    training_source                                TEXT,
    total_records                                   INTEGER,
    class_counts                                     TEXT,
    train_split_pct                                   INTEGER,
    test_split_pct                                     INTEGER,
    primary_feature                                     TEXT,

    evaluated_at                                         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO model_performance_logs_new (
    id, model_name, is_best, is_placeholder,
    accuracy, precision_score, recall_score, f1_score, roc_auc, test_set_size,
    roc_curve_points, feature_importance,
    cv_fold_scores, cv_mean_auc, cv_std_auc, cv_min_auc, cv_max_auc,
    optimization_technique, serialized_model_size_kb, avg_inference_latency_ms,
    target_device, training_source, total_records, train_split_pct, test_split_pct,
    primary_feature, evaluated_at
)
SELECT
    id, model_name, is_best, is_placeholder,
    accuracy, precision_score, recall_score, f1_score, roc_auc, test_set_size,
    roc_curve_points, feature_importance,
    cv_fold_scores, cv_mean_auc, cv_std_auc, cv_min_auc, cv_max_auc,
    optimization_technique, serialized_model_size_kb, avg_inference_latency_ms,
    target_device, training_source, total_records, train_split_pct, test_split_pct,
    primary_feature, evaluated_at
FROM model_performance_logs;

DROP TABLE model_performance_logs;
ALTER TABLE model_performance_logs_new RENAME TO model_performance_logs;

CREATE INDEX IF NOT EXISTS idx_model_performance_logs_best ON model_performance_logs(is_best);

PRAGMA foreign_keys=on;