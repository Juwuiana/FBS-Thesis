import json
from app.models.db import get_connection

_JSON_FIELDS = ("roc_curve_points", "feature_importance", "cv_fold_scores")

def _row_to_dict(row):
    d = dict(row)
    for field in _JSON_FIELDS:
        if d.get(field):
            d[field] = json.loads(d[field])
        else:
            d[field] = []
    d["is_best"] = bool(d["is_best"])
    d["is_placeholder"] = bool(d["is_placeholder"])
    return d

def list_models():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM model_performance_logs ORDER BY roc_auc DESC"
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
                "SELECT * FROM model_performance_logs ORDER BY roc_auc DESC LIMIT 1"
            ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()

def replace_all_models(records):
    """records: list of dicts matching column names (used by seed_model_performance.py)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM model_performance_logs")
        for r in records:
            conn.execute(
                """
                INSERT INTO model_performance_logs (
                    model_name, is_best, is_placeholder,
                    accuracy, precision_score, recall_score, f1_score, roc_auc,
                    cm_tn, cm_fp, cm_fn, cm_tp, test_set_size,
                    roc_curve_points, feature_importance,
                    cv_fold_scores, cv_mean_auc, cv_std_auc, cv_min_auc, cv_max_auc,
                    optimization_technique, serialized_model_size_kb,
                    avg_inference_latency_ms, target_device,
                    training_source, total_records, diabetic_count, non_diabetic_count,
                    train_split_pct, test_split_pct, primary_feature
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["model_name"], int(r["is_best"]), int(r["is_placeholder"]),
                    r["accuracy"], r["precision_score"], r["recall_score"], r["f1_score"], r["roc_auc"],
                    r["cm_tn"], r["cm_fp"], r["cm_fn"], r["cm_tp"], r["test_set_size"],
                    json.dumps(r.get("roc_curve_points") or []),
                    json.dumps(r.get("feature_importance") or []),
                    json.dumps(r.get("cv_fold_scores") or []),
                    r.get("cv_mean_auc"), r.get("cv_std_auc"), r.get("cv_min_auc"), r.get("cv_max_auc"),
                    r.get("optimization_technique"), r.get("serialized_model_size_kb"),
                    r.get("avg_inference_latency_ms"), r.get("target_device"),
                    r.get("training_source"), r.get("total_records"), r.get("diabetic_count"),
                    r.get("non_diabetic_count"), r.get("train_split_pct"), r.get("test_split_pct"),
                    r.get("primary_feature"),
                ),
            )
        conn.commit()
    finally:
        conn.close()