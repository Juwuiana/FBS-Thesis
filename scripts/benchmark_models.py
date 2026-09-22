"""Compare candidate risk-classification models on accuracy AND on-device cost.

This is the evaluation this thesis's Objective 3 calls for: which model gives the best
accuracy/efficiency balance for the phone. It is a standalone script for a training/dev
machine (or the phone itself) -- it does NOT write to the app's database or touch
lab_screenings; it produces a table (and optionally a CSV) to put in the thesis write-up.

For each candidate it repeats a single-row prediction R times, each wrapped in the same
app/ml/green_metrics.measure() the live app uses, so latency/CPU/RAM/power/energy/carbon are
directly comparable to what the Green Computing dashboard reports for real screenings.

Usage:
    python -m scripts.benchmark_models                       # synthetic data, all models, 30 runs each
    python -m scripts.benchmark_models --runs 100 --csv out.csv
    python -m scripts.benchmark_models --models random_forest,lightgbm_optimized
    python -m scripts.benchmark_models --dataset path/to/real_training_data.csv \\
        --features age,bmi,fbs_mg_dl,bp_systolic,bp_diastolic --label risk_level

Each model also has an "_optimized" variant (fewer/shallower trees) so you can see the
accuracy/efficiency trade-off the thesis discusses (pruning-style size reduction), without
requiring a GPU-only quantization toolchain that will not run on the phone anyway.

Real trained model file? Point --predictor-path at a joblib file with the same interface as
app/ml/predictor.Predictor to benchmark it exactly as the live app would run it, alongside
these candidates, for a like-for-like comparison.
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ml.green_metrics import BatteryReader, measure  # noqa: E402
from config import Config  # noqa: E402

FEATURES = ["age", "bmi", "fbs_mg_dl", "bp_systolic", "bp_diastolic"]
LABELS = ["Normal", "Pre-Diabetic", "Diabetic"]


def build_synthetic_dataset(n=2000, seed=42):
    """Stands in for real screening data until the thesis's own dataset/trained model is
    ready (see docs/CONVERSATION_SUMMARY.md). FBS is the dominant signal, matching
    classify_fbs_preliminary(); the rest add noise so models aren't trivially perfect."""
    import numpy as np

    rng = np.random.default_rng(seed)
    age = rng.uniform(30, 75, n)
    bmi = rng.uniform(18, 40, n)
    fbs = rng.normal(105, 25, n).clip(60, 250)
    bp_sys = rng.normal(120, 15, n).clip(90, 200)
    bp_dia = rng.normal(80, 10, n).clip(50, 120)
    label = np.where(fbs >= 126, 2, np.where(fbs >= 100, 1, 0))
    flip = rng.random(n) < 0.05                          # label noise
    label = np.where(flip, rng.integers(0, 3, n), label)
    X = np.column_stack([age, bmi, fbs, bp_sys, bp_dia])
    return X, label


def load_csv_dataset(path, feature_cols, label_col):
    """Plain csv + numpy (no pandas dependency) so this script needs nothing beyond what's
    already installed for training (scikit-learn/lightgbm/xgboost, joblib, numpy)."""
    import csv

    import numpy as np

    rows, labels = [], []
    with open(path, newline="") as fh:
        for record in csv.DictReader(fh):
            rows.append([float(record[c]) for c in feature_cols])
            labels.append(record[label_col])
    label_names = sorted(set(labels))
    label_index = {name: i for i, name in enumerate(label_names)}
    X = np.array(rows, dtype=float)
    y = np.array([label_index[label] for label in labels])
    print(f"Label encoding: {label_index}", file=sys.stderr)
    return X, y


def build_candidates():
    """name -> (sklearn-style estimator, is_optimized). Skips a family if its library isn't
    installed rather than failing the whole run."""
    from sklearn.ensemble import RandomForestClassifier

    candidates = {
        "random_forest": (RandomForestClassifier(n_estimators=200, random_state=0), False),
        "random_forest_optimized": (
            RandomForestClassifier(n_estimators=40, max_depth=6, random_state=0), True),
    }
    try:
        from lightgbm import LGBMClassifier

        candidates["lightgbm"] = (LGBMClassifier(n_estimators=200, verbosity=-1), False)
        candidates["lightgbm_optimized"] = (
            LGBMClassifier(n_estimators=40, max_depth=6, num_leaves=15, verbosity=-1), True)
    except ImportError:
        print("(lightgbm not installed - skipping)", file=sys.stderr)
    try:
        from xgboost import XGBClassifier

        candidates["xgboost"] = (
            XGBClassifier(n_estimators=200, eval_metric="mlogloss"), False)
        candidates["xgboost_optimized"] = (
            XGBClassifier(n_estimators=40, max_depth=4, eval_metric="mlogloss"), True)
    except ImportError:
        print("(xgboost not installed - skipping)", file=sys.stderr)
    return candidates


def model_size_kb(model):
    import io
    import joblib

    buf = io.BytesIO()
    joblib.dump(model, buf)
    return len(buf.getvalue()) / 1024.0


def percentile(values, p):
    values = sorted(values)
    k = (len(values) - 1) * p
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    return values[f] if f == c else values[f] + (values[c] - values[f]) * (k - f)


def benchmark_one(name, model, X_test, y_test, reader, cfg, runs):
    from sklearn.metrics import accuracy_score, f1_score

    preds = model.predict(X_test)
    accuracy = accuracy_score(y_test, preds)
    f1 = f1_score(y_test, preds, average="macro")
    size_kb = model_size_kb(model)

    row = X_test[:1]                      # one screening = one row
    model.predict(row)                    # warm-up, excluded from timing
    measurements = []
    for _ in range(runs):
        with measure(reader, cfg["EMISSION_FACTOR_KG_PER_KWH"], cfg["IDLE_POWER_W"],
                     cfg["ESTIMATED_TDP_W"]) as m:
            model.predict(row)
        measurements.append(m)

    def agg(attr):
        vals = [getattr(m, attr) for m in measurements]
        return {"mean": statistics.mean(vals), "p50": percentile(vals, 0.5),
                "p95": percentile(vals, 0.95), "min": min(vals), "max": max(vals)}

    return {"name": name, "accuracy": accuracy, "f1_macro": f1, "size_kb": size_kb,
            "runs": runs, "measurement_method": measurements[0].method,
            "latency_ms": agg("latency_ms"), "cpu_pct": agg("cpu_pct"), "ram_mb": agg("ram_mb"),
            "power_w": agg("power_w"), "energy_kwh": agg("energy_kwh"),
            "carbon_kg": agg("carbon_kg")}


def print_table(results):
    headers = ["Model", "Acc", "F1(macro)", "Size(KB)", "Latency p50(ms)", "Latency p95(ms)",
               "Energy/run(kWh)", "Source"]
    rows = [[r["name"], f"{r['accuracy']:.3f}", f"{r['f1_macro']:.3f}", f"{r['size_kb']:.1f}",
             f"{r['latency_ms']['p50']:.3f}", f"{r['latency_ms']['p95']:.3f}",
             f"{r['energy_kwh']['mean']:.3e}", r["measurement_method"]] for r in results]
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=30, help="Timed inferences per model (default 30).")
    ap.add_argument("--models", help="Comma-separated subset, e.g. random_forest,lightgbm_optimized.")
    ap.add_argument("--csv", help="Also write full results to this CSV path.")
    ap.add_argument("--json", help="Also write full results (with percentiles) to this JSON path.")
    ap.add_argument("--dataset", help="CSV of real data instead of the synthetic placeholder.")
    ap.add_argument("--features", default=",".join(FEATURES), help="Comma-separated feature columns.")
    ap.add_argument("--label", default="risk_level", help="Label column name (--dataset only).")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.dataset:
        X, y = load_csv_dataset(args.dataset, args.features.split(","), args.label)
    else:
        print("No --dataset given: using a synthetic placeholder (see docstring). "
              "Re-run with --dataset once the real training data / model exists.", file=sys.stderr)
        X, y = build_synthetic_dataset(seed=args.seed)

    from sklearn.model_selection import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=args.seed, stratify=y)

    candidates = build_candidates()
    if args.models:
        wanted = set(args.models.split(","))
        unknown = wanted - candidates.keys()
        if unknown:
            ap.error(f"unknown model(s) {sorted(unknown)}; available: {sorted(candidates)}")
        candidates = {k: v for k, v in candidates.items() if k in wanted}

    cfg = {"EMISSION_FACTOR_KG_PER_KWH": Config.EMISSION_FACTOR_KG_PER_KWH,
           "IDLE_POWER_W": Config.IDLE_POWER_W, "ESTIMATED_TDP_W": Config.ESTIMATED_TDP_W}
    reader = BatteryReader(Config.BATTERY_SYSFS_DIR, Config.CURRENT_NOW_UNIT)
    if not reader.available():
        print("(battery sensor not readable here - results will be labelled 'estimated'; "
              "run this on the phone, unplugged, for real 'battery' numbers)\n", file=sys.stderr)

    results = []
    for name, (model, _optimized) in candidates.items():
        t0 = time.perf_counter()
        model.fit(X_train, y_train)
        train_s = time.perf_counter() - t0
        print(f"[{name}] trained in {train_s:.2f}s, benchmarking {args.runs} inference(s)...",
              file=sys.stderr)
        results.append(benchmark_one(name, model, X_test, y_test, reader, cfg, args.runs))

    results.sort(key=lambda r: r["energy_kwh"]["mean"])
    print()
    print_table(results)

    if args.csv:
        import csv

        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["model", "accuracy", "f1_macro", "size_kb", "runs", "measurement_method",
                       "latency_ms_p50", "latency_ms_p95", "cpu_pct_mean", "ram_mb_mean",
                       "power_w_mean", "energy_kwh_mean", "energy_kwh_total", "carbon_kg_mean"])
            for r in results:
                w.writerow([r["name"], r["accuracy"], r["f1_macro"], r["size_kb"], r["runs"],
                           r["measurement_method"], r["latency_ms"]["p50"], r["latency_ms"]["p95"],
                           r["cpu_pct"]["mean"], r["ram_mb"]["mean"], r["power_w"]["mean"],
                           r["energy_kwh"]["mean"], r["energy_kwh"]["mean"] * r["runs"],
                           r["carbon_kg"]["mean"]])
        print(f"\nWrote {args.csv}", file=sys.stderr)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2)
        print(f"Wrote {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
