"""scripts/benchmark_models.py: covers what doesn't need real ML libraries installed to check
(percentile math, CSV loading, table formatting) plus a real end-to-end run when scikit-learn is
available, since that is the whole point of the script."""
import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.benchmark_models import (  # noqa: E402
    build_synthetic_dataset, load_csv_dataset, percentile, print_table,
)

sklearn = pytest.importorskip("sklearn", reason="benchmark script needs scikit-learn to train models")


def test_percentile_matches_known_values():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([10], 0.95) == 10
    assert percentile([1, 2], 0.5) == 1.5


def test_synthetic_dataset_is_reproducible_and_labeled():
    X1, y1 = build_synthetic_dataset(n=200, seed=1)
    X2, y2 = build_synthetic_dataset(n=200, seed=1)
    assert (X1 == X2).all() and (y1 == y2).all()          # same seed -> same data
    assert set(y1.tolist()) <= {0, 1, 2}
    assert X1.shape == (200, 5)


def test_load_csv_dataset(tmp_path):
    p = tmp_path / "data.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["age", "bmi", "risk_level"])
        w.writerow([40, 25.0, "Normal"])
        w.writerow([60, 31.0, "Diabetic"])
        w.writerow([50, 28.0, "Pre-Diabetic"])
    X, y = load_csv_dataset(str(p), ["age", "bmi"], "risk_level")
    assert X.shape == (3, 2) and X[0].tolist() == [40.0, 25.0]
    assert sorted(set(y.tolist())) == [0, 1, 2]            # 3 distinct labels, encoded


def test_print_table_runs_without_error(capsys):
    fake = [{"name": "m", "accuracy": 0.9, "f1_macro": 0.9, "size_kb": 1.0,
             "measurement_method": "estimated",
             "latency_ms": {"p50": 1.0, "p95": 2.0}, "energy_kwh": {"mean": 1e-9}}]
    print_table(fake)
    assert "m" in capsys.readouterr().out


def test_benchmark_one_end_to_end(tmp_path):
    from sklearn.tree import DecisionTreeClassifier

    from app.ml.green_metrics import BatteryReader
    from scripts.benchmark_models import benchmark_one

    X, y = build_synthetic_dataset(n=100, seed=0)
    model = DecisionTreeClassifier(max_depth=3, random_state=0).fit(X[:80], y[:80])
    reader = BatteryReader(str(tmp_path / "no-battery"))
    cfg = {"EMISSION_FACTOR_KG_PER_KWH": 0.6, "IDLE_POWER_W": 0.0, "ESTIMATED_TDP_W": 5.0}

    result = benchmark_one("tree", model, X[80:], y[80:], reader, cfg, runs=5)

    assert result["runs"] == 5 and result["measurement_method"] == "estimated"
    assert 0.0 <= result["accuracy"] <= 1.0
    assert result["latency_ms"]["p50"] > 0 and result["energy_kwh"]["mean"] >= 0
    assert result["size_kb"] > 0
