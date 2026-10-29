"""
scripts/import_v6_results.py

Loads the verified v6 results (merged SRCHO + ENNS, XGBoost / LightGBM / Random Forest) into
model_performance_logs for the Model Reliability page. Replaces whatever rows are there.

Numbers come from the "13 Single-Panel Figures" Colab notebook (E1 cross-validation and E1 test
tables, Phase 3 split counts) and were re-checked by scoring the deployed XGBoost model on the
held-out rows (n=14,979): accuracy 0.6419, macro AUC 0.7208.

Usage (from the project root):
    python scripts/import_v6_results.py
On Render, run the same command in the service Shell so it updates the production database.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models.model_performance_model import replace_all_models  # noqa: E402

ARTIFACTS = ROOT / "app" / "ml" / "artifacts"
CLASS_ORDER = ["Normal", "Pre-Diabetic", "Diabetic"]   # model class index 0, 1, 2

# ---- Held-out test set (20% stratified split, never used for training / SMOTE / tuning) ------
TEST_N = 14979
TRAIN_SPLIT_PCT, TEST_SPLIT_PCT = 80, 20
TOTAL_RECORDS = 74893                                   # ENNS 74,525 + SRCHO 368
CLASS_COUNTS = {"Normal": 48999, "Pre-Diabetic": 19829, "Diabetic": 6065}
TRAINING_SOURCE = "SRCHO + DOST-FNRI ENNS merged (ENNS 74,525 | SRCHO 368)"
PRIMARY_FEATURE = "age"                                 # also #1 by permutation importance
BEST_MODEL = "XGBoost"                                  # highest composite score S in 10-fold CV

# model -> (test metrics, 10-fold CV metrics). All CV runs put SMOTE inside each fold.
TEST = {
    "XGBoost":      dict(accuracy=0.6419, precision=0.4521, recall=0.4280, f1=0.4306, auc=0.7208),
    "LightGBM":     dict(accuracy=0.6513, precision=0.4565, recall=0.4148, f1=0.4180, auc=0.7202),
    "RandomForest": dict(accuracy=0.6411, precision=0.4442, recall=0.4177, f1=0.4222, auc=0.7086),
}
CV = {
    "XGBoost":      dict(auc=0.7207, std=0.0058, accuracy=0.6439, precision=0.4566, recall=0.4309, f1=0.4340, S=0.5605),
    "LightGBM":     dict(auc=0.7202, std=0.0048, accuracy=0.6497, precision=0.4565, recall=0.4148, f1=0.4177, S=0.5533),
    "RandomForest": dict(auc=0.7098, std=0.0067, accuracy=0.6395, precision=0.4499, recall=0.4200, f1=0.4256, S=0.5507),
}
# Deployed XGBoost on the test set, rows = actual, columns = predicted, order Normal / Pre / Diabetic
CONFUSION_MATRIX = [[8397, 1003, 400], [2560, 1008, 398], [634, 369, 210]]

OPTIMIZATION = "SMOTE inside the pipeline; shallow trees (depth 4, learning rate 0.05, 300 trees)"
DISPLAY_NAMES = {"age": "Age", "bmi": "BMI", "waist_cm": "Waist (cm)", "systolic_bp": "Systolic BP",
                 "diastolic_bp": "Diastolic BP", "sex": "Sex", "smoking_status": "Smoking status",
                 "alcohol_status": "Alcohol status"}
TARGET_DEVICE = "Render web service (Android/Termux not yet measured)"


# Permutation importance on the held-out test set (n=14,979): drop in macro one-vs-rest AUC when
# one input is shuffled (mean of 3 shuffles, baseline AUC 0.7208). Used instead of XGBoost "gain",
# which over-credits the binary smoking/alcohol/sex dummies.
PERMUTATION_IMPORTANCE = {
    "age": 0.0904, "waist_cm": 0.0421, "systolic_bp": 0.0209, "bmi": 0.0079,
    "sex": 0.0046, "alcohol_status": 0.0036, "diastolic_bp": 0.0021, "smoking_status": 0.0,
}


def feature_importance():
    """[{name, importance}] -- the shape reliability.js reads."""
    return [{"name": DISPLAY_NAMES.get(k, k), "importance": round(v / sum(PERMUTATION_IMPORTANCE.values()), 4)}
            for k, v in sorted(PERMUTATION_IMPORTANCE.items(), key=lambda kv: kv[1], reverse=True)]


def deployed_artifact_stats():
    size_kb = None
    latency_ms = None
    booster = ARTIFACTS / "xgb_booster.json"
    if booster.exists():
        size_kb = round(booster.stat().st_size / 1024, 1)
        try:
            from app.ml.predictor import Predictor

            p = Predictor(str(ARTIFACTS / "model.joblib"))
            if not p.is_stub:
                row = {"age": 50, "bmi": 25, "waist_cm": 85, "systolic_bp": 120,
                       "diastolic_bp": 80, "sex": "female"}
                p.predict(row)
                t0 = time.perf_counter()
                for _ in range(200):
                    p.predict(row)
                latency_ms = round((time.perf_counter() - t0) / 200 * 1000, 2)
        except Exception as exc:
            print("  (latency skipped:", exc, ")")
    return size_kb, latency_ms


def build_records():
    size_kb, latency_ms = deployed_artifact_stats()
    importance = feature_importance()
    records = []
    for name in TEST:
        t, c = TEST[name], CV[name]
        is_best = name == BEST_MODEL
        rec = {
            "model_name": name, "is_best": is_best, "is_placeholder": False,
            "accuracy": t["accuracy"], "precision_score": t["precision"],
            "recall_score": t["recall"], "f1_score": t["f1"], "roc_auc": t["auc"],
            "test_set_size": TEST_N,
            "cv_mean_auc": c["auc"], "cv_std_auc": c["std"], "cv_accuracy": c["accuracy"],
            "cv_precision_score": c["precision"], "cv_recall_score": c["recall"],
            "cv_f1_score": c["f1"], "composite_score": c["S"],
            "training_source": TRAINING_SOURCE, "total_records": TOTAL_RECORDS,
            "class_counts": CLASS_COUNTS, "train_split_pct": TRAIN_SPLIT_PCT,
            "test_split_pct": TEST_SPLIT_PCT, "primary_feature": PRIMARY_FEATURE,
            # not recorded per fold / not exported by the notebook
            "roc_curve_points": None, "cv_fold_scores": None, "cv_min_auc": None, "cv_max_auc": None,
        }
        if is_best:
            rec.update({
                "confusion_matrix": CONFUSION_MATRIX, "feature_importance": importance,
                "optimization_technique": OPTIMIZATION, "serialized_model_size_kb": size_kb,
                "avg_inference_latency_ms": latency_ms, "target_device": TARGET_DEVICE,
            })
        records.append(rec)
    return records


def main():
    records = build_records()
    print(f"Importing {len(records)} model record(s):")
    for r in records:
        flag = " (BEST)" if r["is_best"] else ""
        print(f"  - {r['model_name']}{flag}: test acc={r['accuracy']}, test AUC={r['roc_auc']}, "
              f"CV AUC={r['cv_mean_auc']}")
    replace_all_models(records)
    print("Done.")


if __name__ == "__main__":
    main()
