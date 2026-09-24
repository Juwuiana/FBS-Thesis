"""
scripts/import_phase4_results.py

Loads a Phase 4 (CRISP-DM Evaluation) summary JSON into model_performance_logs,
against the schema after migration 0010 (multiclass-adapted).

Usage:
    python scripts/import_phase4_results.py path/to/phase4_summary.json
"""

import json
import sys
from pathlib import Path

# Ensure the project root (parent of scripts/) is importable regardless of
# where this is invoked from -- running `python scripts/x.py` puts scripts/
# itself on sys.path, not the project root, so `app` wouldn't resolve without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.model_performance_model import replace_all_models

# Fixed for this project -- Android edge device via Termux (see system architecture doc)
TARGET_DEVICE = "Android (Termux)"
TRAINING_SOURCE = "enns_only_phase5_summary.json (ENNS-only, unrestricted-attribute pipeline)"
AUC_BENCHMARK = 0.80

# Fields we know we can't populate from phase4_summary.json today -- kept
# explicit rather than just omitted, so it's obvious what's still owed to
# this table instead of accidentally forgotten.
UNAVAILABLE_FIELDS = {
    "test_set_size": None,          # not logged by the pipeline yet
    "roc_curve_points": None,       # no raw ROC points exported
    "cv_fold_scores": None,         # cv_results is per-model mean, not per-fold
    "cv_std_auc": None,
    "cv_min_auc": None,
    "cv_max_auc": None,
    "optimization_technique": None, # GridSearchCV/RFE used per project decisions,
                                     # but not recorded per-run in this JSON
    "class_counts": None,           # per-class record counts not in this JSON
    "total_records": None,
    "train_split_pct": None,
    "test_split_pct": None,
    "primary_feature": None,
}


def build_records(summary: dict) -> list[dict]:
    selected_model = summary["selected_model"]
    cv_results = summary["cv_results"]
    composite_scores = summary["composite_scores"]
    test_metrics = summary["test_metrics"]
    edge = summary["edge_readiness"]
    confusion_matrix = summary.get("confusion_matrix")
    feature_importance = summary.get("feature_importance")

    records = []
    for model_name, cv in cv_results.items():
        is_best = model_name == selected_model

        record = {
            "model_name": model_name,
            "is_best": is_best,
            "is_placeholder": False,  # real pipeline output, even for non-selected candidates

            # Test-set metrics: only available for the model actually evaluated
            # on the held-out set (the selected model).
            "accuracy": test_metrics["accuracy"] if is_best else None,
            "precision_score": test_metrics["precision"] if is_best else None,
            "recall_score": test_metrics["recall"] if is_best else None,
            "f1_score": test_metrics["f1"] if is_best else None,
            "roc_auc": test_metrics["auc"] if is_best else None,

            # CV-level metrics: available for every candidate model
            "cv_mean_auc": cv["auc"],
            "cv_accuracy": cv["accuracy"],
            "cv_precision_score": cv["precision"],
            "cv_recall_score": cv["recall"],
            "cv_f1_score": cv["f1"],

            # Selection mechanism
            "composite_score": composite_scores[model_name],

            # Edge deployment stats: measured only for the selected/deployed model
            "serialized_model_size_kb": round(edge["size_mb"] * 1024, 2) if is_best else None,
            "avg_inference_latency_ms": round(edge["latency_s"] * 1000, 3) if is_best else None,
            "target_device": TARGET_DEVICE if is_best else None,
            "confusion_matrix": confusion_matrix if is_best else None,
            "feature_importance": feature_importance if is_best else None,
            "training_source": TRAINING_SOURCE,
        }
        record.update(UNAVAILABLE_FIELDS)
        records.append(record)

    return records


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_phase4_results.py path/to/enns_only_phase5_summary.json")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    summary = json.loads(json_path.read_text(encoding="utf-8"))

    records = build_records(summary)

    print(f"Importing {len(records)} model record(s):")
    for r in records:
        flag = " (BEST)" if r["is_best"] else ""
        below = ""
        if r["roc_auc"] is not None and r["roc_auc"] < AUC_BENCHMARK:
            below = f"  [below {AUC_BENCHMARK} AUC benchmark]"
        print(f"  - {r['model_name']}{flag}: cv_auc={r['cv_mean_auc']:.4f}, "
              f"test_auc={r['roc_auc']}{below}")

    replace_all_models(records)
    print("Done.")


if __name__ == "__main__":
    main()