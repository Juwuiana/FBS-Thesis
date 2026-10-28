"""Loads the trained model once at startup. Until the real model files exist it runs a
clearly flagged stub so the pipeline (and the green metrics) can be exercised.

Model: XGBoost pipeline from the v6 notebook, exported to xgb_booster.json + preprocess.json
(no pickle, so it does not depend on the scikit-learn version). Needs only numpy + xgboost.

Labels match lab_screenings.model_predicted_risk_level CHECK: Normal / Pre-Diabetic / Diabetic.
"""
import json
import os

# Index = integer class the model was trained on (v6 notebook: CLASSES = Normal, Pre-Diabetic,
# Diabetic). NOTE: this is NOT the alphabetical order the old 7-feature RandomForest used.
LABELS = ("Normal", "Pre-Diabetic", "Diabetic")

# Screening rule: flag a patient when risk_score = 1 - P(Normal) >= RISK_THRESHOLD.
# On the held-out test set (n=14,979) this catches ~77% of at-risk and ~87% of diabetic patients,
# versus only 17% of diabetic patients when taking the single most likely class.
RISK_THRESHOLD = 0.40   # Low  < 0.40
HIGH_THRESHOLD = 0.70   # Moderate 0.40-0.69, High >= 0.70

BOOSTER_FILE = "xgb_booster.json"
META_FILE = "preprocess.json"


def _blank(v):
    if v is None:
        return True
    if isinstance(v, float) and v != v:  # NaN
        return True
    return str(v).strip() == ""


class Predictor:
    def __init__(self, path: str):
        self.path = path
        self.model = None          # xgboost Booster
        self.meta = None
        self.version = "stub-0"
        self.feature_names = None
        # `path` may be the old model.joblib location (or a folder): the new files sit beside it.
        folder = path if path and os.path.isdir(path) else os.path.dirname(path or "")
        booster_path = os.path.join(folder, BOOSTER_FILE)
        meta_path = os.path.join(folder, META_FILE)
        if folder and os.path.exists(booster_path) and os.path.exists(meta_path):
            import xgboost as xgb  # lazy: keeps startup light when no model is present

            with open(meta_path, encoding="utf-8") as f:
                self.meta = json.load(f)
            self.model = xgb.Booster()
            self.model.load_model(booster_path)
            self.version = "xgboost-v6"
            self.feature_names = self.meta["numeric_columns"] + self.meta["categorical_columns"]
            self._warm_up()

    @property
    def is_stub(self) -> bool:
        return self.model is None

    def _warm_up(self):
        try:
            self._proba({})
        except Exception:  # warm-up is best effort
            pass

    # ---- feature handling -------------------------------------------------------------
    def _encode(self, features: dict):
        f = dict(features)
        # Backwards compatibility with callers that still send the old 0/1 flags.
        if _blank(f.get("sex")) and not _blank(f.get("sex_male")):
            f["sex"] = "male" if float(f["sex_male"]) >= 0.5 else "female"
        if _blank(f.get("alcohol_status")) and _blank(f.get("alcohol_status_never")) is False:
            if float(f["alcohol_status_never"]) >= 0.5:
                f["alcohol_status"] = "never"   # a 0 can't tell former from current -> left blank

        m = self.meta
        x = []
        for col, med in zip(m["numeric_columns"], m["numeric_medians"]):
            v = f.get(col)
            x.append(med if _blank(v) else float(v))
        for col, fill, levels in zip(m["categorical_columns"], m["categorical_fill"],
                                     m["categorical_levels"]):
            v = f.get(col)
            v = fill if _blank(v) else str(v).strip().lower()
            x.extend(1.0 if v == lvl else 0.0 for lvl in levels)  # unseen value -> all zeros
        return x

    def _proba(self, features: dict):
        import numpy as np
        import xgboost as xgb

        X = np.asarray([self._encode(features)], dtype=np.float32)
        return self.model.predict(xgb.DMatrix(X))[0]

    # ---- prediction ---------------------------------------------------------------------
    def predict(self, features: dict) -> dict:
        if self.is_stub:
            # Placeholder logic only; NOT a clinical model.
            fbs = float(features.get("fbs_mg_dl", features.get("fbs", 90)))
            label = "Diabetic" if fbs >= 126 else "Pre-Diabetic" if fbs >= 100 else "Normal"
            return {"model_predicted_risk_level": label, "model_confidence": 0.5,
                    "model_version": self.version}

        p = self._proba(features)
        risk = 1.0 - float(p[0])
        if risk < RISK_THRESHOLD:
            label = "Normal"
        else:
            label = "Diabetic" if p[2] >= p[1] else "Pre-Diabetic"
        tier = "Low" if risk < RISK_THRESHOLD else "Moderate" if risk < HIGH_THRESHOLD else "High"
        return {
            "model_predicted_risk_level": label,
            "model_confidence": float(max(p)),
            "model_version": self.version,
            # extra fields for the dashboards (callers that ignore them are unaffected)
            "risk_score": round(risk, 4),
            "risk_tier": tier,
            "probabilities": {l: round(float(v), 4) for l, v in zip(LABELS, p)},
        }
