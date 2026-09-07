from app import db
from datetime import datetime

class ModelPerformanceLog(db.Model):
    __tablename__ = 'model_performance_logs'

    id = db.Column(db.Integer, primary_key=True)

    # Identity
    model_name = db.Column(db.String(50), nullable=False)   # 'Random Forest' | 'XGBoost' | 'LightGBM'
    is_best = db.Column(db.Boolean, nullable=False, default=False)
    is_placeholder = db.Column(db.Boolean, nullable=False, default=True)  # False once real training results replace this row

    # Core metrics
    accuracy = db.Column(db.Float, nullable=False)
    precision = db.Column(db.Float, nullable=False)
    recall = db.Column(db.Float, nullable=False)
    f1_score = db.Column(db.Float, nullable=False)
    roc_auc = db.Column(db.Float, nullable=False)

    # Confusion matrix (test set)
    cm_tn = db.Column(db.Integer, nullable=False)
    cm_fp = db.Column(db.Integer, nullable=False)
    cm_fn = db.Column(db.Integer, nullable=False)
    cm_tp = db.Column(db.Integer, nullable=False)
    test_set_size = db.Column(db.Integer, nullable=False)

    # ROC curve — list of {"fpr": .., "tpr": ..}
    roc_curve_points = db.Column(db.JSON, nullable=True)

    # Feature importance — list of {"name": .., "importance": ..}
    feature_importance = db.Column(db.JSON, nullable=True)

    # Cross-validation (k-fold)
    cv_fold_scores = db.Column(db.JSON, nullable=True)
    cv_mean_auc = db.Column(db.Float, nullable=True)
    cv_std_auc = db.Column(db.Float, nullable=True)
    cv_min_auc = db.Column(db.Float, nullable=True)
    cv_max_auc = db.Column(db.Float, nullable=True)

    # Optimization details — reframed for tree-based models (no TinyML/quantization)
    optimization_technique = db.Column(db.String(150), nullable=True)      # e.g. "GridSearchCV, 5-fold"
    serialized_model_size_kb = db.Column(db.Float, nullable=True)          # joblib file size
    avg_inference_latency_ms = db.Column(db.Float, nullable=True)          # CodeCarbon-logged
    target_device = db.Column(db.String(100), nullable=True)

    # Training set metadata
    training_source = db.Column(db.String(150), nullable=True)
    total_records = db.Column(db.Integer, nullable=True)
    diabetic_count = db.Column(db.Integer, nullable=True)
    non_diabetic_count = db.Column(db.Integer, nullable=True)
    train_split_pct = db.Column(db.Integer, nullable=True)
    test_split_pct = db.Column(db.Integer, nullable=True)
    primary_feature = db.Column(db.String(100), nullable=True)

    evaluated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ModelPerformanceLog {self.model_name} acc={self.accuracy} placeholder={self.is_placeholder}>'