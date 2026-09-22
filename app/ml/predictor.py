"""Loads the trained model once at startup. Until the real model file exists it runs a
clearly flagged stub so the pipeline (and the green metrics) can be exercised.

Labels match lab_screenings.model_predicted_risk_level CHECK: Normal / Pre-Diabetic / Diabetic.
"""
import os

LABELS = ("Normal", "Pre-Diabetic", "Diabetic")


class Predictor:
    def __init__(self, path: str):
        self.path = path
        self.model = None
        self.version = "stub-0"
        self.feature_names = None
        if path and os.path.exists(path):
            import joblib  # lazy: keeps startup light when no model is present

            self.model = joblib.load(path)
            self.version = os.path.basename(path)
            self.feature_names = getattr(self.model, "feature_names_in_", None)
            self._warm_up()

    @property
    def is_stub(self) -> bool:
        return self.model is None

    def _warm_up(self):
        if self.feature_names is None:
            return
        try:
            import numpy as np
            self.model.predict(np.zeros((1, len(self.feature_names))))
        except Exception:  # warm-up is best effort
            pass

    def predict(self, features: dict) -> dict:
        if self.is_stub:
            # Placeholder logic only; NOT a clinical model.
            fbs = float(features.get("fbs_mg_dl", features.get("fbs", 90)))
            label = "Diabetic" if fbs >= 126 else "Pre-Diabetic" if fbs >= 100 else "Normal"
            return {"model_predicted_risk_level": label, "model_confidence": 0.5,
                    "model_version": self.version}
        import numpy as np
        names = list(self.feature_names) if self.feature_names is not None else list(features)
        row = np.array([[float(features.get(n, 0.0)) for n in names]])
        out = self.model.predict(row)[0]
        label = out if isinstance(out, str) else LABELS[int(out)]
        conf = None
        if hasattr(self.model, "predict_proba"):
            conf = float(max(self.model.predict_proba(row)[0]))
        return {"model_predicted_risk_level": label, "model_confidence": conf,
                "model_version": self.version}
