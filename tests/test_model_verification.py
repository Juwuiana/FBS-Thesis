"""Verification tests for Test Cases 1.4, 2.1, 2.2 and 2.3.
Run from the project root:  python -m pytest tests/test_model_verification.py -v
"""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.ml.predictor import LABELS, Predictor  # noqa: E402

ARTIFACTS = os.path.join(ROOT, "app", "ml", "artifacts")

VALID = {"age": 55, "bmi": 28.0, "waist_cm": 95.0, "systolic_bp": 140, "diastolic_bp": 90,
         "sex": "male", "smoking_status": "never", "alcohol_status": "never"}


@pytest.fixture(scope="module")
def predictor():
    p = Predictor(os.path.join(ARTIFACTS, "model.joblib"))
    assert not p.is_stub, "model files not found: the stub is running"
    return p


def ada_label(fbs):
    import pandas as pd
    out = pd.cut(pd.Series([fbs], dtype=float), [0, 100, 126, 1e9],
                 labels=["Normal", "Pre-Diabetic", "Diabetic"], right=False)
    return None if out.isna().iloc[0] else str(out.iloc[0])


@pytest.mark.parametrize("fbs,expected", [(99, "Normal"), (100, "Pre-Diabetic"),
                                          (125, "Pre-Diabetic"), (126, "Diabetic")])
def test_1_4_ada_boundaries(fbs, expected):
    assert ada_label(fbs) == expected


def test_1_4_missing_fbs_gets_no_label():
    assert ada_label(float("nan")) is None


def test_2_1_load_and_predict(predictor):
    out = predictor.predict(VALID)
    assert out["model_predicted_risk_level"] in LABELS
    probs = out["probabilities"]
    assert set(probs) == set(LABELS)
    assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-3)
    assert 0.0 <= out["model_confidence"] <= 1.0
    assert out["model_version"] == "xgboost-v6"


BAD = {
    "missing age": {k: v for k, v in VALID.items() if k != "age"},
    "missing sex": {k: v for k, v in VALID.items() if k != "sex"},
    "negative bmi": {**VALID, "bmi": -5},
    "negative age": {**VALID, "age": -1},
    "age out of range": {**VALID, "age": 150},
    "systolic out of range": {**VALID, "systolic_bp": 900},
    "wrong type": {**VALID, "age": "abc"},
    "unknown sex value": {**VALID, "sex": "unknown"},
}


@pytest.mark.parametrize("name", list(BAD))
def test_2_2_invalid_input_rejected(predictor, name):
    with pytest.raises(ValueError) as err:
        predictor.predict(BAD[name])
    assert str(err.value).strip()


def test_2_3_same_input_same_output_20_times(predictor):
    first = predictor.predict(VALID)
    for _ in range(19):
        assert predictor.predict(VALID) == first