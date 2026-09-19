import json
from app.models.db import get_connection

_JSON_LIST_FIELDS = ("roc_curve_points", "feature_importance", "cv_fold_scores")
_JSON_DICT_FIELDS = ("confusion_matrix", "class_counts")

# Column order for INSERT -- single source of truth, so adding a column later
# only means editing this tuple, not recounting "?" placeholders by hand.
_COLUMNS = (
    "model_name", "is_best", "is_placeholder",
    "accuracy", "precision_score", "recall_score", "f1_score", "roc_auc", "test_set_size",
    "confusion_matrix", "roc_curve_points", "feature_importance",
    "cv_fold_scores", "cv_mean_auc", "cv_std_auc", "cv_min_auc", "cv_max_auc",
    "cv_accuracy", "cv_precision_score", "cv_recall_score", "cv_f1_score",
    "composite_score",
    "optimization_technique", "serialized_model_size_kb",
    "avg_inference_latency_ms", "target_device",
    "training_source", "total_records", "class_counts",
    "train_split_pct", "test_split_pct", "primary_feature",
)


def _row_to_dict(row):
    d = dict(row)
    for field in _JSON_LIST_FIELDS:
        d[field] = json.loads(d[field]) if d.get(field) else []
    for field in _JSON_DICT_FIELDS:
        d[field] = json.loads(d[field]) if d.get(field) else {}
    d["is_best"] = bool(d["is_best"])
    d["is_placeholder"] = bool(d["is_placeholder"])
    return d


def _record_to_value(record, column):
    """Pull one column's value out of a record dict, serializing JSON fields."""
    if column == "is_best":
        return int(record["is_best"])
    if column == "is_placeholder":
        return int(record["is_placeholder"])
    if column in _JSON_LIST_FIELDS:
        return json.dumps(record.get(column) or [])
    if column in _JSON_DICT_FIELDS:
        value = record.get(column)
        return json.dumps(value) if value else None
    return record.get(column)


def list_models():
    conn = get_connection()
    try:
        # COALESCE so candidate models with no test-set roc_auc yet still sort
        # sensibly by their CV AUC, instead of always dropping to the bottom.
        rows = conn.execute(
            "SELECT * FROM model_performance_logs "
            "ORDER BY COALESCE(roc_auc, cv_mean_auc) DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_best_model():
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM model_performance_logs WHERE is_best = 1 LIMIT 1"
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM model_performance_logs "
                "ORDER BY COALESCE(roc_auc, cv_mean_auc) DESC LIMIT 1"
            ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def replace_all_models(records):
    """records: list of dicts matching column names (used by
    scripts/seed_model_performance.py and scripts/import_phase4_results.py).
    Every dict must have model_name, is_best, is_placeholder; everything
    else may be omitted and is stored as NULL.
    """
    conn = get_connection()
    try:
        conn.execute("DELETE FROM model_performance_logs")
        placeholders = ", ".join("?" for _ in _COLUMNS)
        column_list = ", ".join(_COLUMNS)
        sql = f"INSERT INTO model_performance_logs ({column_list}) VALUES ({placeholders})"
        for r in records:
            values = tuple(_record_to_value(r, col) for col in _COLUMNS)
            conn.execute(sql, values)
        conn.commit()
    finally:
        conn.close()