"""
evaluate_models.py — Trains/evaluates Random Forest, XGBoost, and LightGBM,
computes real performance metrics, and saves them to model_performance_logs,
replacing the placeholder rows from scripts/seed_model_performance.py.

STATUS: STUB. Sections marked "TODO" need your actual training pipeline
plugged in. Everything else (metric computation, DB writing, best-model
selection) is ready to run as-is once the TODOs are filled in.

Run from the project root once training is ready:
    python scripts/evaluate_models.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import joblib
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, roc_curve, confusion_matrix,
)
# from sklearn.model_selection import StratifiedKFold, cross_val_score, GridSearchCV
# from imblearn.over_sampling import SMOTE
# from sklearn.feature_selection import RFE

from app import create_app
from app.models.model_performance_model import replace_all_models

app = create_app()

MODEL_DIR = "models"  # TODO: confirm this is where you're saving trained .joblib files
os.makedirs(MODEL_DIR, exist_ok=True)

MODEL_PATHS = {
    "Random Forest": os.path.join(MODEL_DIR, "random_forest.joblib"),
    "XGBoost":        os.path.join(MODEL_DIR, "xgboost.joblib"),
    "LightGBM":       os.path.join(MODEL_DIR, "lightgbm.joblib"),
}

TARGET_DEVICE = "Android edge device (Termux)"


def load_test_set():
    """
    TODO: Load your actual held-out test set (X_test, y_test) here.
    This should be the SAME test split used when you originally trained
    and evaluated the models — not a fresh random split — so the metrics
    reported here match what you'll write in Chapter 4.

    Example (adjust to your actual data pipeline):
        import pandas as pd
        df = pd.read_csv("data/processed/test_set.csv")
        X_test = df.drop(columns=["target"])
        y_test = df["target"]
        return X_test, y_test
    """
    raise NotImplementedError("Fill in load_test_set() with your actual test data loading.")


def get_cv_scores(model, X_train, y_train, k=10):
    """
    TODO: Run k-fold cross-validation on the TRAINING set (not test set)
    and return the fold AUC scores. Example:

        from sklearn.model_selection import StratifiedKFold, cross_val_score
        skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
        scores = cross_val_score(model, X_train, y_train, cv=skf, scoring='roc_auc')
        return scores.tolist()
    """
    raise NotImplementedError("Fill in get_cv_scores() once your training pipeline is ready.")


def get_feature_importance(model, feature_names):
    """
    TODO: Extract feature importances from the trained model.
    Random Forest / XGBoost / LightGBM all expose `.feature_importances_`.

    Example:
        importances = model.feature_importances_
        pairs = sorted(zip(feature_names, importances), key=lambda x: -x[1])
        return [{"name": n, "importance": float(v)} for n, v in pairs]
    """
    raise NotImplementedError("Fill in get_feature_importance() once your training pipeline is ready.")


def measure_inference_latency(model, X_sample, n_runs=100):
    """
    Measures average per-prediction latency in milliseconds.
    NOTE: This is a rough local timing measurement, useful for a sanity
    check — but for the thesis's official green computing numbers, use
    your actual CodeCarbon-logged latency from on-device inference
    (per your architecture: CodeCarbon Monitor triggered per prediction),
    not this local measurement.
    """
    sample = X_sample[:1] if hasattr(X_sample, "__getitem__") else X_sample.iloc[:1]
    start = time.perf_counter()
    for _ in range(n_runs):
        model.predict(sample)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms / n_runs


def evaluate_one(name, path, X_test, y_test, X_train=None, y_train=None, feature_names=None):
    model = joblib.load(path)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    fpr, tpr, _ = roc_curve(y_test, y_proba)

    precision_val = float(precision_score(y_test, y_pred))
    recall_val = float(recall_score(y_test, y_pred))

    result = dict(
        model_name=name,
        is_best=False,           # decided after comparing all three, below
        is_placeholder=False,
        accuracy=float(accuracy_score(y_test, y_pred)),
        precision_score=precision_val,
        recall_score=recall_val,
        f1_score=float(f1_score(y_test, y_pred)),
        roc_auc=float(roc_auc_score(y_test, y_proba)),
        cm_tn=int(tn), cm_fp=int(fp), cm_fn=int(fn), cm_tp=int(tp),
        test_set_size=len(y_test),
        roc_curve_points=[{"fpr": float(f), "tpr": float(t)} for f, t in zip(fpr, tpr)],
        serialized_model_size_kb=os.path.getsize(path) / 1024,
        avg_inference_latency_ms=measure_inference_latency(model, X_test),
        target_device=TARGET_DEVICE,
        optimization_technique="TODO: e.g. 'GridSearchCV (5-fold), RFE feature selection'",
        # TODO: training_source, total_records, diabetic_count, non_diabetic_count,
        # train_split_pct, test_split_pct, primary_feature — fill in from your
        # actual dataset stats (same for all 3 models, since they share a train/test split)
    )

    # TODO: uncomment once get_feature_importance() and get_cv_scores() are implemented
    # result["feature_importance"] = get_feature_importance(model, feature_names)
    # cv_scores = get_cv_scores(model, X_train, y_train)
    # result["cv_fold_scores"] = cv_scores
    # result["cv_mean_auc"] = float(np.mean(cv_scores))
    # result["cv_std_auc"] = float(np.std(cv_scores))
    # result["cv_min_auc"] = float(np.min(cv_scores))
    # result["cv_max_auc"] = float(np.max(cv_scores))

    return result


def weighted_composite_score(result, weights=None):
    """
    TODO: Replace this with your project's actual formalized weighted
    composite scoring formula (per Chapter 4 methodology — AUC-ROC as
    primary criterion, combined with other metrics). Placeholder below
    just uses AUC-ROC alone so the script runs end-to-end; swap in the
    real formula when you have it defined.
    """
    return result["roc_auc"]


def main():
    with app.app_context():
        X_test, y_test = load_test_set()
        # X_train, y_train = load_train_set()  # TODO if needed for CV step
        # feature_names = X_test.columns.tolist()  # TODO, adjust to your data format

        results = []
        for name, path in MODEL_PATHS.items():
            if not os.path.exists(path):
                print(f"Skipping {name}: no trained model found at {path}")
                continue
            print(f"Evaluating {name}...")
            results.append(evaluate_one(name, path, X_test, y_test))

        if not results:
            print("No trained models found — nothing to save. Train and save "
                  f".joblib files to {MODEL_DIR}/ first.")
            return

        best = max(results, key=weighted_composite_score)
        best["is_best"] = True

        replace_all_models(results)

        print(f"Saved {len(results)} real evaluation results. "
              f"Best model: {best['model_name']} (AUC={best['roc_auc']:.3f})")


if __name__ == "__main__":
    main()