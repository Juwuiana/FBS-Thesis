"""
app/models/ml_model.py loads trained pkl
"""
import pickle
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent / "model.pkl"

# ─pag may model na
FEATURE_ORDER = [
    # mg ,pde;
]

# labels ng model
EXPECTED_LABELS = {"Normal", "Pre-Diabetic", "Diabetic"}

_model = None


def _load_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"No model file at {MODEL_PATH}. Place your temporary "
                f".pkl there, or update MODEL_PATH in ml_model.py."
            )
        with open(MODEL_PATH, "rb") as f:
            _model = pickle.load(f)

        actual_labels = set(_model.classes_)
        if actual_labels != EXPECTED_LABELS:
            raise ValueError(
                f"Model's classes_ {actual_labels} don't match the "
                f"expected {EXPECTED_LABELS}. This model can't be used "
                f"as-is -- check you loaded the right .pkl file."
            )
    return _model


def build_feature_vector(visit: dict, patient: dict, conditions: dict) -> list:
    """
    Turns your DB rows into the exact ordered feature list the model
    expects. THIS IS A STUB -- fill in each feature to match
    FEATURE_ORDER exactly. Example shape shown; replace with your real
    ~7 features (BMI, waist, family history, etc. per your thesis
    feature-selection results).
    """
    raise NotImplementedError(
        "build_feature_vector() needs your actual feature list. "
        "Fill in FEATURE_ORDER above and this function together."
    )


def predict_risk(visit: dict, patient: dict, conditions: dict) -> tuple[str, float]:
    """
    Returns (risk_level, confidence) ready to pass straight into
    lab_model.set_model_prediction(visit_id, risk_level, confidence).
    """
    model = _load_model()
    features = build_feature_vector(visit, patient, conditions)

    proba = model.predict_proba([features])[0]
    best_idx = proba.argmax()

    predicted_label = model.classes_[best_idx]
    confidence = float(proba[best_idx])

    return predicted_label, confidence