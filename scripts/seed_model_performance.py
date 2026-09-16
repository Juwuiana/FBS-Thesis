"""
Seed script: populates model_performance_logs with PLACEHOLDER rows so the
Model Reliability dashboard has something to render before real model
training/evaluation is complete.

Every row here has is_placeholder=True. When your actual training
pipeline (Random Forest / XGBoost / LightGBM, evaluated via AUC-ROC +
weighted composite scoring) produces real results, replace these rows
(don't just add more) and flip is_placeholder=False.

Run from the project root:
    python scripts/seed_model_performance.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.model_performance_model import replace_all_models

app = create_app()

PLACEHOLDER_ROWS = [
    dict(
        model_name="Random Forest",
        is_best=True,
        is_placeholder=True,
        accuracy=0.883, precision_score=0.871, recall_score=0.856, f1_score=0.863, roc_auc=0.889,
        cm_tn=512, cm_fp=48, cm_fn=65, cm_tp=175, test_set_size=800,
        roc_curve_points=[
            {"fpr": 0.00, "tpr": 0.00}, {"fpr": 0.05, "tpr": 0.55},
            {"fpr": 0.10, "tpr": 0.72}, {"fpr": 0.20, "tpr": 0.85},
            {"fpr": 0.50, "tpr": 0.96}, {"fpr": 1.00, "tpr": 1.00},
        ],
        feature_importance=[
            {"name": "FBS (mg/dL)", "importance": 0.5821},
            {"name": "Age", "importance": 0.1342},
            {"name": "BMI", "importance": 0.0987},
        ],
        cv_fold_scores=[0.881, 0.893, 0.876, 0.901, 0.885, 0.879, 0.897, 0.868, 0.891, 0.883],
        cv_mean_auc=0.885, cv_std_auc=0.009, cv_min_auc=0.868, cv_max_auc=0.901,
        optimization_technique="GridSearchCV (5-fold), RFE feature selection — PLACEHOLDER",
        serialized_model_size_kb=None,
        avg_inference_latency_ms=None,
        target_device="Android edge device (Termux)",
        training_source="1 LHU — Santa Rosa City (placeholder)",
        total_records=4820, diabetic_count=1644, non_diabetic_count=3176,
        train_split_pct=70, test_split_pct=30, primary_feature="FBS (mg/dL)",
    ),
    dict(
        model_name="XGBoost",
        is_best=False,
        is_placeholder=True,
        accuracy=0.871, precision_score=0.858, recall_score=0.843, f1_score=0.850, roc_auc=0.878,
        cm_tn=505, cm_fp=55, cm_fn=68, cm_tp=172, test_set_size=800,
        roc_curve_points=None, feature_importance=None,
        cv_fold_scores=None, cv_mean_auc=None, cv_std_auc=None, cv_min_auc=None, cv_max_auc=None,
        optimization_technique="GridSearchCV (5-fold) — PLACEHOLDER",
        serialized_model_size_kb=None, avg_inference_latency_ms=None,
        target_device="Android edge device (Termux)",
        training_source="1 LHU — Santa Rosa City (placeholder)",
        total_records=4820, diabetic_count=1644, non_diabetic_count=3176,
        train_split_pct=70, test_split_pct=30, primary_feature="FBS (mg/dL)",
    ),
    dict(
        model_name="LightGBM",
        is_best=False,
        is_placeholder=True,
        accuracy=0.865, precision_score=0.851, recall_score=0.837, f1_score=0.844, roc_auc=0.872,
        cm_tn=500, cm_fp=60, cm_fn=70, cm_tp=170, test_set_size=800,
        roc_curve_points=None, feature_importance=None,
        cv_fold_scores=None, cv_mean_auc=None, cv_std_auc=None, cv_min_auc=None, cv_max_auc=None,
        optimization_technique="GridSearchCV (5-fold) — PLACEHOLDER",
        serialized_model_size_kb=None, avg_inference_latency_ms=None,
        target_device="Android edge device (Termux)",
        training_source="1 LHU — Santa Rosa City (placeholder)",
        total_records=4820, diabetic_count=1644, non_diabetic_count=3176,
        train_split_pct=70, test_split_pct=30, primary_feature="FBS (mg/dL)",
    ),
]

with app.app_context():
    replace_all_models(PLACEHOLDER_ROWS)
    print(f"Seeded {len(PLACEHOLDER_ROWS)} placeholder model_performance_logs rows.")