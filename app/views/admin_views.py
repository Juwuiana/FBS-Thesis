from flask import Blueprint, jsonify, make_response, render_template, request, redirect, url_for, abort, flash, session
import hashlib
import hmac
import sqlite3
import csv
import io
from datetime import datetime, timedelta, timezone
from app.models.patient_model import _compute_age
from werkzeug.security import generate_password_hash

from app.controllers import auth_controller, metrics_controller
from app.constants import CSV_IMPORT_COLUMNS, ROLE_MAP, STATION_MAP
from app.db import get_db
from app.models import audit_model
from app.models.model_performance_model import list_models, get_best_model
from app.views.auth_views import login_required, require_role_for_blueprint, role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# The whole Admin section is medical_officer-only (the nurse/patient portals are separate
# blueprints for the other roles). Applied once here instead of on every view.
require_role_for_blueprint(admin_bp, "medical_officer")

STAFF_ROLES = list(ROLE_MAP)
STATIONS = list(STATION_MAP)
MAX_IMPORT_BYTES = 1_048_576
MAX_IMPORT_ROWS = 500
_ROLE_BY_LABEL = {label.casefold(): value for label, value in ROLE_MAP.items()}
_STATION_BY_LABEL = {**{label.casefold(): value for label, value in STATION_MAP.items()}, "rhu i": "lhui", "rhu ii": "lhuii"}

def _csv_value(value): return (value or "").strip()
def _normalize_csv_header(header): return "_".join((header or "").strip().lower().split())
def _csv_row_form(row):
    # barangay_name is passed through as-is (no more mapping against the
    # 18-entry BARANGAYS whitelist) -- validate_profile_fields resolves it
    # via lookup_model.get_or_create_barangay_by_name, which creates the
    # row instead of silently blanking anything outside Santa Rosa. This
    # is still name-only (the CSV template has no code column), so it's
    # ambiguous nationwide -- fine for now since staff imports are small
    # and manually reviewed, but worth revisiting if that stops being true.
    return {"first_name":_csv_value(row.get("first_name")),"middle_name":_csv_value(row.get("middle_name")),"last_name":_csv_value(row.get("last_name")),"birthday":auth_controller.normalize_import_birthday(_csv_value(row.get("birthday"))),"sex":_csv_value(row.get("sex")).lower(),"email":_csv_value(row.get("email")),"phone":_csv_value(row.get("phone")),"role":_ROLE_BY_LABEL.get(_csv_value(row.get("role")).casefold(),""),"facility":_STATION_BY_LABEL.get(_csv_value(row.get("station")).casefold(),""),"barangay_name":_csv_value(row.get("barangay")),"password":row.get("temporary_password") or "","confirm_password":row.get("temporary_password") or ""}
def _import_error(errors,row_number,message): errors.append({"row":row_number,"message":message})
STAFF_STATUSES = ["Approved", "Rejected", "Pending"]

def _audit_event(action, severity="Info"):
    audit_model.log_event(
        get_db(), user_id=session.get("user_id"), user_name=session.get("user_name", "unknown"),
        role=session.get("user_role", "Unknown"), action=action,
        ip_address=request.remote_addr, severity=severity,
    )


def _validate_staff_details(form):
    from app.models import lookup_model

    errors = []
    role_label = (form.get("role") or "").strip()
    station_label = (form.get("station") or "").strip()
    phone = auth_controller.normalize_phone(form.get("contact"))
    facility = STATION_MAP.get(station_label)

    if role_label not in STAFF_ROLES:
        errors.append("Please select a valid role.")
    if not auth_controller.PH_MOBILE_RE.match(phone):
        errors.append("Enter a valid 10-digit mobile number starting with 9.")
    if station_label not in STATIONS or not facility:
        errors.append("Please select a valid station.")

    barangay_code = (form.get("barangay_code") or "").strip()
    barangay_name = (form.get("barangay_name") or "").strip()
    barangay_id = None
    if not barangay_code and not barangay_name:
        errors.append("Please select an assigned barangay.")
    elif not errors:
        if barangay_code:
            barangay_id = lookup_model.get_or_create_barangay(
                barangay_code,
                barangay_name,
                (form.get("city_code") or "").strip(),
                (form.get("city_name") or "").strip(),
                (form.get("region_code") or "").strip(),
                (form.get("region_name") or "").strip(),
            )
        else:
            barangay_id = lookup_model.get_or_create_barangay_by_name(barangay_name)
        if barangay_id is None:
            errors.append("Please select an assigned barangay.")

    return errors, {
        "role": role_label,
        "facility": facility,
        "phone": phone,
        "barangay_id": barangay_id,
    }


def _mask_staff_phone(phone):
    value = phone or ""
    return f"{value[:3]}****{value[-3:]}" if len(value) == 10 else "****"


def _coerce_retention_ids(raw_ids):
    if raw_ids is None:
        return []
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    cleaned = []
    for value in raw_ids:
        text = str(value or "").strip()
        try:
            patient_id = int(text)
        except ValueError as exc:
            raise ValueError("Select valid patient records.") from exc
        if patient_id <= 0 or patient_id in cleaned:
            raise ValueError("Select valid patient records.")
        cleaned.append(patient_id)
    if len(cleaned) > 500:
        raise ValueError("You can process up to 500 patient records at a time.")
    return cleaned


RETENTION_PAGE_SIZES = (10, 25, 50, 100)
RETENTION_DEFAULT_PAGE_SIZE = 25


def _retention_page_args(total):
    try:
        per_page = int(request.args.get("per_page", RETENTION_DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        per_page = RETENTION_DEFAULT_PAGE_SIZE
    if per_page not in RETENTION_PAGE_SIZES:
        per_page = RETENTION_DEFAULT_PAGE_SIZE
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    total_pages = max(1, -(-total // per_page))
    page = min(max(page, 1), total_pages)
    return page, per_page, total_pages


def _retention_session_hash():
    user_id = session.get("user_id") or "guest"
    security_version = session.get("security_version") or 0
    payload = f"patient-retention:{user_id}:{security_version}:{datetime.utcnow().isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _retention_ids_hash(patient_ids):
    payload = ",".join(str(patient_id) for patient_id in sorted(patient_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _retention_selection(patient_model):
    raw_ids = request.form.getlist("patient_ids")
    if len(raw_ids) > 500:
        raise ValueError("You can process up to 500 patient records at a time.")
    patient_ids = _coerce_retention_ids(raw_ids)
    if not patient_ids:
        raise ValueError("Select at least one patient record.")

    submitted_hash = request.form.get("selection_hash")
    expected_hash = session.get("patient_retention_selection_hash")
    if not expected_hash or not submitted_hash or not hmac.compare_digest(expected_hash, submitted_hash):
        raise ValueError("This retention review selection is no longer valid. Please refresh the page and try again.")

    from app.models import settings as settings_model

    retention_days = settings_model.get_patient_retention_days()
    if retention_days is None:
        raise ValueError("Patient record retention is turned off.")
    due_rows = patient_model.get_patients_for_retention_ids(patient_ids)
    if len(due_rows) != len(patient_ids):
        raise ValueError("Every selected patient must still be due for review.")
    return patient_ids, retention_days


def _download_retention_archive(patient_model):
    try:
        patient_ids, _ = _retention_selection(patient_model)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.privacy_security"))

    csv_data = patient_model.export_patients_csv_for_ids(patient_ids)
    session["patient_retention_archive_hash"] = _retention_ids_hash(patient_ids)
    _audit_event(f"Exported {len(patient_ids)} patient record(s) for retention review", "Info")
    response = make_response(csv_data)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="patient_retention_archive.csv"'
    return response


@admin_bp.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()

    # "Current" stats (Total Screened, At Risk, High Risk, Avg FBS, Risk
    # Distribution) reflect each PATIENT's most recent screening only, so a
    # patient tested 5 times counts once, using their latest result. This
    # matches the nurse dashboard's patient-based count. The Barangay list,
    # Timeline, and Recent Screenings table intentionally stay as full
    # event logs -- they're about screening activity, not current status.
    latest_rows = conn.execute(
        """
        WITH latest_ids AS (
            SELECT ls.id AS screening_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY v.patient_id
                       ORDER BY ls.test_datetime DESC, ls.id DESC
                   ) AS rn
            FROM lab_screenings ls
            JOIN visits v ON v.id = ls.visit_id
        )
        SELECT ls.fbs_mg_dl, COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS final_risk_level
        FROM lab_screenings ls
        JOIN latest_ids li ON li.screening_id = ls.id
        WHERE li.rn = 1
        """
    ).fetchall()

    total_screened = len(latest_rows)
    at_risk_count = sum(1 for r in latest_rows if r["final_risk_level"] in ("Moderate", "High"))
    high_risk_count = sum(1 for r in latest_rows if r["final_risk_level"] == "High")
    at_risk_pct = round(100 * at_risk_count / total_screened, 1) if total_screened else 0
    high_risk_pct = round(100 * high_risk_count / total_screened, 1) if total_screened else 0

    fbs_values = [r["fbs_mg_dl"] for r in latest_rows if r["fbs_mg_dl"] is not None]
    avg_fbs = round(sum(fbs_values) / len(fbs_values), 1) if fbs_values else 0

    metrics = {
        "total_screened": total_screened,
        "at_risk": at_risk_count, "at_risk_pct": at_risk_pct,
        "high_risk": high_risk_count, "high_risk_pct": high_risk_pct,
        "avg_fbs": avg_fbs,
        "model_accuracy": None,
    }

    low_count = sum(1 for r in latest_rows if r["final_risk_level"] == "Low")
    moderate_count = sum(1 for r in latest_rows if r["final_risk_level"] == "Moderate")
    high_count = high_risk_count
    risk_distribution = {
        "low":      {"count": low_count,      "pct": round(100*low_count/total_screened,1) if total_screened else 0},
        "moderate": {"count": moderate_count, "pct": round(100*moderate_count/total_screened,1) if total_screened else 0},
        "high":     {"count": high_count,     "pct": round(100*high_count/total_screened,1) if total_screened else 0},
    }

    barangay_rows = conn.execute(
        """
        SELECT b.name, COUNT(ls.id) AS cnt
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        LEFT JOIN barangays b ON b.id = p.barangay_id
        GROUP BY b.name
        ORDER BY cnt DESC
        LIMIT 5
        """
        ).fetchall()
    barangay_list = [{"name": row[0] or "Unknown", "count": row[1]} for row in barangay_rows]

    period_rows = conn.execute(
        "SELECT test_datetime, COALESCE(final_risk_level, preliminary_risk_level) AS final_risk_level "
        "FROM lab_screenings WHERE test_datetime IS NOT NULL"
    ).fetchall()

    day_totals, day_at_risk = {}, {}
    for row in period_rows:
        try:
            d = datetime.fromisoformat(row["test_datetime"]).date()
        except (TypeError, ValueError):
            continue
        day_totals[d] = day_totals.get(d, 0) + 1
        if row["final_risk_level"] in ("Moderate", "High"):
            day_at_risk[d] = day_at_risk.get(d, 0) + 1

    recent_days = sorted(day_totals.keys(), reverse=True)[:14]
    recent_days.reverse()  # chronological order for the chart

    timeline_labels, timeline_total, timeline_at_risk = [], [], []
    for d in recent_days:
        timeline_labels.append(d.strftime("%b %d"))
        timeline_total.append(day_totals.get(d, 0))
        timeline_at_risk.append(day_at_risk.get(d, 0))
    timeline = {"labels": timeline_labels, "totalScreened": timeline_total, "atRisk": timeline_at_risk}

    recent_rows = conn.execute(
        """
        SELECT ls.id, p.first_name, p.middle_name, p.last_name, p.birthdate, p.sex,
               ls.fbs_mg_dl, ls.model_predicted_risk_level,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS final_risk_level,
               ls.test_datetime
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        ORDER BY ls.test_datetime DESC
        LIMIT 10
        """
    ).fetchall()
    recent_screenings = []
    for row in recent_rows:
        full_name = " ".join(
            part for part in [row["first_name"], row["middle_name"], row["last_name"]] if part
        )
        age = _compute_age(row["birthdate"]) if row["birthdate"] else None
        try:
            date_display = datetime.fromisoformat(row["test_datetime"]).strftime("%b %d, %Y")
        except (TypeError, ValueError):
            date_display = row["test_datetime"]
        recent_screenings.append({
            "id": f"SCR-{row['id']:05d}",
            "name": full_name,
            "age_sex": f"{age if age is not None else '—'}/{row['sex'] or '—'}",
            "fbs": row["fbs_mg_dl"],
            "category": row["model_predicted_risk_level"],
            "risk": row["final_risk_level"],
            "date": date_display,
        })

    model_performance = {
        "accuracy": 89.3, "precision": 0.87, "recall": 0.88,
        "f1_score": 0.87, "roc_auc": 0.93,
    }

    # From feature/model-reliability: once real evaluation results exist in
    # model_performance_logs, use the actual best model's numbers instead of
    # the placeholder figures above. Falls back to the placeholders (and thus
    # never breaks the dashboard) when the table is empty or unmigrated.
    try:
        best = get_best_model()
    except sqlite3.Error:
        best = None
    if best:
        if best.get("accuracy") is not None:
            metrics["model_accuracy"] = round(best["accuracy"] * 100, 1)
        model_performance = {
            "accuracy": round(best["accuracy"] * 100, 1) if best.get("accuracy") is not None else model_performance["accuracy"],
            "precision": best.get("precision_score") if best.get("precision_score") is not None else model_performance["precision"],
            "recall": best.get("recall_score") if best.get("recall_score") is not None else model_performance["recall"],
            "f1_score": best.get("f1_score") if best.get("f1_score") is not None else model_performance["f1_score"],
            "roc_auc": best.get("roc_auc") if best.get("roc_auc") is not None else model_performance["roc_auc"],
        }

    return render_template(
        "dashboard/index.html",
        metrics=metrics,
        risk_distribution=risk_distribution,
        barangay_list=barangay_list,
        recent_screenings=recent_screenings,
        model_performance=model_performance,
        timeline=timeline,
    )


# ── Demo/placeholder fallback for the Model Reliability page ───────────────
# Shown only when model_performance_logs has no rows yet (fresh DB, migrations
# applied but scripts/seed_model_performance.py hasn't been run). Keeps the
# page usable out of the box instead of 404ing; real data from
# app.models.model_performance_model always takes priority when present.
_DEMO_BENCHMARKS = [
    {"name": "Random Forest", "accuracy": 0.883, "precision": 0.871,
     "recall": 0.856, "f1": 0.863, "auc": 0.889, "cv_auc": 0.885,
     "composite_score": 0.885, "best": True},
    {"name": "XGBoost", "accuracy": 0.871, "precision": 0.858,
     "recall": 0.843, "f1": 0.850, "auc": 0.878, "cv_auc": 0.874,
     "composite_score": 0.874, "best": False},
    {"name": "LightGBM", "accuracy": 0.865, "precision": 0.851,
     "recall": 0.837, "f1": 0.844, "auc": 0.872, "cv_auc": 0.869,
     "composite_score": 0.869, "best": False},
]
_DEMO_BEST_MODEL = {
    "name": "Random Forest", "accuracy": 0.883, "precision": 0.871,
    "recall": 0.856, "f1": 0.863, "auc": 0.889, "test_n": 800,
    "confusion_matrix": [[420, 30, 8], [26, 210, 18], [6, 15, 267]],
}
_DEMO_OPTIMIZATION = {
    "technique": "Post-Training Quantization",
    "serialized_size_kb": 182,
    "inference_time_ms": 0.4,
    "target_device": "Android edge device (Termux)",
}
_DEMO_TRAINING_SET = {
    "source": "1 LHU \u2013 Santa Rosa City (placeholder)",
    "total_records": 4820,
    "class_breakdown": [
        {"label": "Normal", "count": 2456, "pct": 51.0},
        {"label": "Pre-Diabetic", "count": 1420, "pct": 29.5},
        {"label": "Diabetic", "count": 944, "pct": 19.5},
    ],
    "train_split": 70,
    "test_split": 30,
    "primary_feature": "FBS (mg/dL)",
}
_DEMO_FEATURE_IMPORTANCE = [
    {"name": "FBS (mg/dL)", "importance": 0.5821},
    {"name": "Age", "importance": 0.1342},
    {"name": "BMI", "importance": 0.0987},
    {"name": "Systolic BP", "importance": 0.0765},
    {"name": "Diastolic BP", "importance": 0.0534},
    {"name": "Sex", "importance": 0.0312},
    {"name": "Waist Circum.", "importance": 0.0239},
]
_DEMO_CV = {
    "fold_scores": [0.881, 0.893, 0.876, 0.901, 0.885,
                    0.879, 0.897, 0.868, 0.891, 0.883],
    "mean_auc": 0.885, "std_auc": 0.009, "min_auc": 0.868, "max_auc": 0.901,
    "accuracy": 0.878, "precision": 0.865, "recall": 0.851, "f1": 0.858,
}
_DEMO_ROC_POINTS = [
    {"fpr": 0.00, "tpr": 0.00}, {"fpr": 0.02, "tpr": 0.32},
    {"fpr": 0.05, "tpr": 0.55}, {"fpr": 0.10, "tpr": 0.72},
    {"fpr": 0.15, "tpr": 0.80}, {"fpr": 0.20, "tpr": 0.85},
    {"fpr": 0.30, "tpr": 0.91}, {"fpr": 0.40, "tpr": 0.94},
    {"fpr": 0.50, "tpr": 0.96}, {"fpr": 0.70, "tpr": 0.98},
    {"fpr": 1.00, "tpr": 1.00},
]


@admin_bp.route("/reliability")
@login_required
def reliability():
    try:
        logs = list_models()
    except sqlite3.Error:
        logs = []

    if not logs:
        # No evaluation results yet -- render the page with placeholder data
        # (flagged as such) instead of a dead 404, so the page is always
        # demoable. Run scripts/seed_model_performance.py or
        # scripts/evaluate_models.py to replace this with real data.
        return render_template(
            "model/reliability.html",
            benchmarks=_DEMO_BENCHMARKS,
            best_model=_DEMO_BEST_MODEL,
            optimization=_DEMO_OPTIMIZATION,
            training_set=_DEMO_TRAINING_SET,
            feature_importance=_DEMO_FEATURE_IMPORTANCE,
            cv=_DEMO_CV,
            roc_points=_DEMO_ROC_POINTS,
            is_placeholder=True,
        )

    benchmarks = [
        {
            "name": log["model_name"],
            "accuracy": log["accuracy"],
            "precision": log["precision_score"],
            "recall": log["recall_score"],
            "f1": log["f1_score"],
            "auc": log["roc_auc"],
            "cv_auc": log["cv_mean_auc"],
            "composite_score": log["composite_score"],
            "best": log["is_best"],
        }
        for log in logs
    ]

    best = get_best_model() or logs[0]

    best_model = {
        "name": best["model_name"],
        "accuracy": best["accuracy"],
        "precision": best["precision_score"],
        "recall": best["recall_score"],
        "f1": best["f1_score"],
        "auc": best["roc_auc"],
        "test_n": best["test_set_size"],
        # {} until a raw NxN export exists; template treats an empty
        # value as "not available yet" rather than assuming a fixed shape.
        "confusion_matrix": best["confusion_matrix"],
    }

    optimization = {
        "technique": best["optimization_technique"],
        "serialized_size_kb": best["serialized_model_size_kb"],
        "inference_time_ms": best["avg_inference_latency_ms"],
        "target_device": best["target_device"],
    }

    total = best["total_records"] or 0
    class_counts = best["class_counts"]  # {} until known
    class_breakdown = [
        {
            "label": label,
            "count": count,
            "pct": round(100 * count / total, 1) if total else None,
        }
        for label, count in class_counts.items()
    ]
    training_set = {
        "source": best["training_source"],
        "total_records": total,
        "class_breakdown": class_breakdown,  # list of {label, count, pct} -- N classes, not 2
        "train_split": best["train_split_pct"],
        "test_split": best["test_split_pct"],
        "primary_feature": best["primary_feature"],
    }

    cv = {
        "fold_scores": best["cv_fold_scores"],
        "mean_auc": best["cv_mean_auc"],
        "std_auc": best["cv_std_auc"],
        "min_auc": best["cv_min_auc"],
        "max_auc": best["cv_max_auc"],
        "accuracy": best["cv_accuracy"],
        "precision": best["cv_precision_score"],
        "recall": best["cv_recall_score"],
        "f1": best["cv_f1_score"],
    }

    return render_template(
        "model/reliability.html",
        benchmarks=benchmarks,
        best_model=best_model,
        optimization=optimization,
        training_set=training_set,
        feature_importance=best["feature_importance"],
        cv=cv,
        roc_points=best["roc_curve_points"],
        is_placeholder=best["is_placeholder"],
    )

@admin_bp.route("/data-management")
@login_required
def data_management():
    from app.models import user as user_model
    employees = user_model.get_staff_records()
    return render_template("dashboard/records.html", employees=employees)


@admin_bp.route("/data-management/import-template")
@login_required
def staff_import_template():
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(CSV_IMPORT_COLUMNS)
    writer.writerow([
        "Fake",
        "Example",
        "Employee",
        "1990-01-01",
        "female",
        "fake.employee@example.invalid",
        "9170000000",
        "LHU Nurse",
        "LHU I",
        "Aplaya",
        "NotARealPassword123",
    ])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=employee_import_template.csv"
    return response


@admin_bp.route("/data-management/export-audit", methods=["POST"])
@login_required
def staff_export_audit():
    _audit_event("Exported CSV: staff records", "Warning")
    return jsonify({"ok": True})


@admin_bp.route("/data-management/import", methods=["POST"])
@login_required
def staff_import():
    from app.models import user as user_model

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"ok": False, "imported": 0, "errors": [{"row": 1, "message": "Please choose a CSV file."}]}), 400
    if not uploaded.filename.lower().endswith(".csv"):
        return jsonify({"ok": False, "imported": 0, "errors": [{"row": 1, "message": "Only .csv files are accepted."}]}), 400

    content = uploaded.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        return jsonify({"ok": False, "imported": 0, "errors": [{"row": 1, "message": "The CSV file must be 1 MB or smaller."}]}), 400
    try:
        text = content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text), strict=True)
        headers = next(reader, None)
    except (UnicodeDecodeError, csv.Error, StopIteration):
        return jsonify({"ok": False, "imported": 0, "errors": [{"row": 1, "message": "The CSV file is not valid UTF-8 CSV."}]}), 400

    if not headers:
        return jsonify({"ok": False, "imported": 0, "errors": [{"row": 1, "message": "The CSV file must include a header row."}]}), 400
    normalized_headers = [_normalize_csv_header(header) for header in headers]
    missing = [column for column in CSV_IMPORT_COLUMNS if column not in normalized_headers]
    if missing:
        return jsonify({
            "ok": False,
            "imported": 0,
            "errors": [{"row": 1, "message": "Missing required column(s): " + ", ".join(missing)}],
        }), 400

    rows = []
    errors = []
    seen_emails = set()
    try:
        for values in reader:
            row_number = reader.line_num
            if not any(_csv_value(value) for value in values):
                continue
            row = {
                header: values[index] if index < len(values) else ""
                for index, header in enumerate(normalized_headers)
                if header in CSV_IMPORT_COLUMNS
            }
            if len(rows) >= MAX_IMPORT_ROWS:
                _import_error(errors, row_number, "The CSV file cannot contain more than 500 data rows.")
                break

            form = _csv_row_form(row)
            email = form["email"].casefold()
            if email in seen_emails:
                _import_error(errors, row_number, "email already exists in this file")
            else:
                seen_emails.add(email)

            validation_errors, cleaned, password = auth_controller.validate_profile_fields(
                form, normalize_phone_input=True
            )
            for message in validation_errors:
                _import_error(errors, row_number, message)
            if not validation_errors:
                cleaned["role"] = form["role"]
                cleaned["facility"] = form["facility"]
                cleaned["password_hash"] = generate_password_hash(password)
                rows.append(cleaned)
    except csv.Error:
        _import_error(errors, reader.line_num or 1, "The CSV file contains invalid CSV data.")

    if errors:
        return jsonify({"ok": False, "imported": 0, "errors": errors}), 400

    try:
        user_model.create_users_bulk(rows)
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "imported": 0, "errors": [{"row": 2, "message": "email already exists"}]}), 400
    _audit_event(f"Bulk staff import: {len(rows)} employees", "Warning")
    return jsonify({"ok": True, "imported": len(rows), "errors": []})



@admin_bp.route("/data-management/add", methods=["GET", "POST"])
@login_required
def add_staff():
    from app.models import user as user_model
    from app.constants import ROLE_MAP, STATION_MAP

    if request.method == "POST":
        role_label = request.form.get("role", "").strip()
        station_label = request.form.get("station", "").strip()

        profile_form = {
            "first_name": request.form.get("first_name", ""),
            "middle_name": request.form.get("middle_name", ""),
            "last_name": request.form.get("last_name", ""),
            "birthday": request.form.get("birthday", ""),
            "sex": request.form.get("sex", ""),
            "email": request.form.get("email", ""),
            "phone": request.form.get("contact", ""),
            "role": ROLE_MAP.get(role_label, ""),
            "facility": STATION_MAP.get(station_label, ""),
            "barangay_code": request.form.get("barangay_code", ""),
            "barangay_name": request.form.get("barangay_name", ""),
            "city_code": request.form.get("city_code", ""),
            "city_name": request.form.get("city_name", ""),
            "region_code": request.form.get("region_code", ""),
            "region_name": request.form.get("region_name", ""),
            "password": request.form.get("password", ""),
            "confirm_password": request.form.get("confirm_password", ""),
        }

        # barangay resolution (code-first, PSGC-based) now happens inside
        # validate_profile_fields via lookup_model -- no separate whitelist
        # check needed here anymore.
        errors, cleaned, password = auth_controller.validate_profile_fields(
            profile_form, normalize_phone_input=True
        )
        if role_label not in STAFF_ROLES:
            errors.append("Please select a valid role.")
        if station_label not in STATIONS:
            errors.append("Please select a valid station.")

        form_data = {
            "first_name": request.form.get("first_name", "").strip(),
            "middle_name": request.form.get("middle_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "birthday": request.form.get("birthday", "").strip(),
            "sex": request.form.get("sex", "").strip(),
            "email": request.form.get("email", "").strip(),
            "contact": request.form.get("contact", "").strip(),
            "role": role_label,
            "station": station_label,
            "region_code": request.form.get("region_code", "").strip(),
            "city_code": request.form.get("city_code", "").strip(),
            "barangay_code": request.form.get("barangay_code", "").strip(),
            "barangay_name": request.form.get("barangay_name", "").strip(),
        }

        if errors:
            return render_template(
                "admin/add_staff.html",
                roles=STAFF_ROLES, stations=STATIONS,
                today=datetime.utcnow().date().isoformat(),
                errors=errors, form_data=form_data,
            ), 400

        cleaned["role"] = ROLE_MAP[role_label]
        cleaned["facility"] = STATION_MAP[station_label]

        try:
            user_id = user_model.create_user(
                cleaned, generate_password_hash(password), status="approved"
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper() and "EMAIL" in str(exc).upper():
                errors.append("An account with this email already exists.")
                return render_template(
                    "admin/add_staff.html",
                    roles=STAFF_ROLES, stations=STATIONS,
                    today=datetime.utcnow().date().isoformat(),
                    errors=errors, form_data=form_data,
                ), 400
            raise

        _audit_event(f"Employee account created: {cleaned['email']}", "Success")
        flash("Employee account created successfully.", "success")
        return redirect(url_for("admin.staff_detail", employee_id=f"EMP-{user_id:05d}"))

    return render_template(
        "admin/add_staff.html",
        roles=STAFF_ROLES, stations=STATIONS,
        today=datetime.utcnow().date().isoformat(),
        errors=[], form_data={},
    )


# Shows full staff info (read-only) with selected editable fields.
@admin_bp.route("/data-management/<employee_id>/view")
@login_required
def staff_view(employee_id):
    from app.models import user as user_model

    employee = user_model.get_employee_by_id(employee_id)
    if employee is None:
        abort(404)

    try:
        birthday = datetime.strptime(employee["birthday"], "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
    except (KeyError, TypeError, ValueError):
        age = None

    phone = employee.get("contact") or ""
    formatted_phone = (
        f"+63 {phone[0:3]} {phone[3:6]} {phone[6:]}"
        if len(phone) == 10 and phone.isdigit()
        else phone
    )
    return render_template(
        "admin/staff_view.html",
        employee=employee,
        age=age,
        formatted_phone=formatted_phone,
        last_login=employee.get("last_login_at") or "Never",
        read_only_employee_view=True,
    )


@admin_bp.route("/data-management/<employee_id>")
@login_required
def staff_detail(employee_id):
    from app.db import get_db
    from app.models import user as user_model

    employee = user_model.get_employee_by_id(employee_id)
    if employee is None:
        abort(404)
    barangay_preselect = {}
    if employee.get("barangay_id"):
        row = get_db().execute(
            "SELECT barangay_code, city_code, region_code, name FROM barangays WHERE id = ?",
            (employee["barangay_id"],),
        ).fetchone()
        if row:
            barangay_preselect = {
                "barangay_code": row["barangay_code"] or "",
                "city_code": row["city_code"] or "",
                "region_code": row["region_code"] or "",
                "barangay_name": row["name"] or "",
            }
    return render_template(
        "admin/staff_detail.html",
        employee=employee,
        roles=STAFF_ROLES,
        stations=STATIONS,
        barangay_preselect=barangay_preselect,
    )


@admin_bp.route("/data-management/<employee_id>/update-details", methods=["POST"])
@login_required
def staff_update_details(employee_id):
    from app.models import lookup_model, user as user_model

    employee = user_model.get_employee_by_id(employee_id)
    if employee is None:
        abort(404)

    errors, cleaned = _validate_staff_details(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("admin.staff_detail", employee_id=employee_id))

    role_changed = employee["role"] != cleaned["role"]
    target_user = user_model.get_user_by_employee_id(employee_id)
    if role_changed and target_user["id"] == session.get("user_id"):
        flash("You cannot change your own role.", "error")
        return redirect(url_for("admin.staff_detail", employee_id=employee_id))
    if (
        role_changed
        and employee["role"] == "Health Officer"
        and employee["status"] == "Approved"
        and not employee["is_suspended"]
    ):
        active_admins = get_db().execute(
            "SELECT COUNT(*) FROM users WHERE role = ? AND status = ? AND is_suspended = 0",
            ("medical_officer", "approved"),
        ).fetchone()[0]
        if active_admins <= 1:
            flash("The last active Health Officer cannot be demoted.", "error")
            return redirect(url_for("admin.staff_detail", employee_id=employee_id))

    if not user_model.update_staff_details(
        employee_id,
        cleaned["facility"],
        cleaned["phone"],
        cleaned["barangay_id"],
        cleaned["role"],
    ):
        flash("Employee details could not be updated.", "error")
        return redirect(url_for("admin.staff_detail", employee_id=employee_id))

    new_barangay = lookup_model.get_barangay_name_by_id(cleaned["barangay_id"]) or "Unknown"
    changes = []
    if employee["facility"] != cleaned["facility"]:
        new_station = next(label for label, value in STATION_MAP.items() if value == cleaned["facility"])
        changes.append(f"Station / LHU: {employee['station']} -> {new_station}")
    if employee["phone"] != cleaned["phone"]:
        changes.append(
            f"Contact Number: {_mask_staff_phone(employee['phone'])} -> "
            f"{_mask_staff_phone(cleaned['phone'])}"
        )
    if employee["barangay_id"] != cleaned["barangay_id"]:
        changes.append(f"Assigned Barangay: {employee['barangay']} -> {new_barangay}")
    if role_changed:
        changes.append(f"Role: {employee['role']} -> {cleaned['role']}")
    if changes:
        _audit_event(
            f"Staff details changed (employee: {employee_id}): " + "; ".join(changes),
            "Warning",
        )
    if role_changed:
        _audit_event(
            f"Role changed: {employee['role']} -> {cleaned['role']} (user: {employee_id})",
            "Warning",
        )
    flash("Employee details updated successfully.", "success")
    return redirect(url_for("admin.staff_detail", employee_id=employee_id))


@admin_bp.route("/data-management/<employee_id>/approve", methods=["POST"])
@login_required
def approve_staff(employee_id):
    from app.models import user as user_model

    employee = user_model.get_employee_by_id(employee_id)
    if employee is None:
        abort(404)

    user = user_model.get_user_by_employee_id(employee_id)
    if user is None:
        abort(404)

    user_model.set_status(user["id"], "approved")
    _audit_event(f"Staff account approved: {employee_id}", "Success")
    flash("Account approved successfully. The user can now sign in.", "success")
    return redirect(url_for("admin.staff_detail", employee_id=employee_id))


@admin_bp.route("/data-management/<employee_id>/reject", methods=["POST"])
@login_required
def reject_staff(employee_id):
    from app.models import user as user_model

    employee = user_model.get_employee_by_id(employee_id)
    if employee is None:
        abort(404)

    user = user_model.get_user_by_employee_id(employee_id)
    if user is None:
        abort(404)

    user_model.set_status(user["id"], "rejected")
    _audit_event(f"Staff account rejected: {employee_id}", "Warning")
    flash("Account rejected. The user cannot sign in.", "success")
    return redirect(url_for("admin.staff_detail", employee_id=employee_id))


@admin_bp.route("/data-management/<employee_id>/delete", methods=["POST"])
@login_required
def delete_staff(employee_id):
    from app.models import user as user_model

    if not user_model.delete_user_by_employee_id(employee_id):
        abort(404)

    _audit_event(f"Employee account deleted: {employee_id}", "Critical")
    flash("Employee account deleted successfully.", "success")
    return redirect(url_for("admin.data_management"))


@admin_bp.route("/staff/<employee_id>/reset-password", methods=["POST"])
@login_required
def reset_staff_password(employee_id):
    from app.models import user as user_model

    employee = user_model.get_user_by_employee_id(employee_id)
    if employee is None:
        abort(404)
    if employee["status"] != "recovery" and not employee["is_suspended"]:
        return jsonify({"error": "This employee does not have a pending password recovery request."}), 400

    reset_reason = "suspended account" if employee["is_suspended"] else "recovery request"
    temp_password = auth_controller.generate_temp_password()
    user_model.reset_password(
        employee["id"], generate_password_hash(temp_password), status="approved"
    )
    _audit_event(
        f"Password reset for {employee['email']} ({reset_reason})", "Warning"
    )
    return jsonify({
        "temp_password": temp_password,
        "name": " ".join(part for part in [employee["first_name"], employee["middle_name"], employee["last_name"]] if part),
        "email": employee["email"],
    })


@admin_bp.route("/data-management/<employee_id>/unlock", methods=["POST"])
@login_required
def unlock_staff(employee_id):
    from app.models import settings as settings_model, user as user_model

    employee = user_model.get_user_by_employee_id(employee_id)
    if employee is None:
        abort(404)
    is_legacy_lockout = (
        employee["status"] == "recovery"
        and employee["failed_login_attempts"] >= settings_model.get_max_login_attempts()
    )
    if not employee["is_suspended"] and not is_legacy_lockout:
        flash("This account is not locked.", "error")
        return redirect(url_for("admin.data_management"))

    if employee["is_suspended"]:
        user_model.set_suspended(employee["id"], False)
    else:
        user_model.unlock_user(employee["id"])
    _audit_event(f"Account unlocked: {employee_id}", "Warning")
    flash("Account unlocked successfully.", "success")
    return redirect(url_for("admin.data_management"))


@admin_bp.route("/data-management/<employee_id>/suspend", methods=["POST"])
@login_required
def suspend_staff(employee_id):
    from app.models import user as user_model

    employee = user_model.get_user_by_employee_id(employee_id)
    if employee is None:
        abort(404)
    if employee["id"] == session.get("user_id"):
        flash("You cannot suspend your own account.", "error")
        return redirect(url_for("admin.staff_detail", employee_id=employee_id))
    if employee["is_suspended"]:
        flash("This account is already suspended.", "error")
        return redirect(url_for("admin.staff_detail", employee_id=employee_id))
    if employee["status"] != "approved":
        flash("Only approved accounts can be suspended.", "error")
        return redirect(url_for("admin.staff_detail", employee_id=employee_id))

    if employee["role"] == "medical_officer":
        active_admins = get_db().execute(
            "SELECT COUNT(*) FROM users WHERE role = ? AND status = ? AND is_suspended = 0",
            ("medical_officer", "approved"),
        ).fetchone()[0]
        if active_admins <= 1:
            flash("The last active Health Officer account cannot be suspended.", "error")
            return redirect(url_for("admin.staff_detail", employee_id=employee_id))

    user_model.set_suspended(employee["id"], True)
    _audit_event(f"Staff account suspended: {employee_id}", "Critical")
    flash("Staff account suspended.", "success")
    return redirect(url_for("admin.staff_detail", employee_id=employee_id))


@admin_bp.route("/data-management/<employee_id>/reactivate", methods=["POST"])
@login_required
def reactivate_staff(employee_id):
    from app.models import user as user_model

    employee = user_model.get_user_by_employee_id(employee_id)
    if employee is None:
        abort(404)
    if not employee["is_suspended"]:
        flash("This account is not suspended.", "error")
        return redirect(url_for("admin.staff_detail", employee_id=employee_id))

    user_model.set_suspended(employee["id"], False)
    _audit_event(f"Staff account reactivated: {employee_id}", "Warning")
    flash("Staff account reactivated.", "success")
    return redirect(url_for("admin.staff_detail", employee_id=employee_id))


@admin_bp.route("/privacy-security")
@login_required
def privacy_security():
    from app.models import settings as settings_model
    from app.models import patient_model

    patient_model.run_retention_purge()
    session_timeout_minutes = settings_model.get_session_timeout_minutes()
    max_login_attempts = settings_model.get_max_login_attempts()
    recycle_bin_days = settings_model.get_recycle_bin_days()
    recycle_bin_status = patient_model.get_recycle_bin_status()
    patient_retention_days = settings_model.get_patient_retention_days()
    patient_retention_due_count = patient_model.count_patients_due_for_retention()
    retention_page, retention_per_page, retention_total_pages = _retention_page_args(patient_retention_due_count)
    patient_retention_due = patient_model.list_patients_due_for_retention(
        limit=retention_per_page, offset=(retention_page - 1) * retention_per_page
    )
    oldest_due = patient_model.list_patients_due_for_retention(limit=1)
    patient_retention_oldest_screening = oldest_due[0]["last_screening_date"] if oldest_due else None
    patient_retention_cutoff_date = (
        (datetime.now(timezone.utc).date() - timedelta(days=patient_retention_days)).isoformat()
        if patient_retention_days is not None else None
    )
    session["patient_retention_selection_hash"] = _retention_session_hash()
    roles = [
        {
            "key": "patient",
            "label": "Patient",
            "login_enabled": settings_model.is_role_login_enabled("patient"),
            "export_enabled": settings_model.is_role_export_enabled("patient"),
        },
        {
            "key": "health_worker",
            "label": "LHU Nurse",
            "login_enabled": settings_model.is_role_login_enabled("health_worker"),
            "export_enabled": settings_model.is_role_export_enabled("health_worker"),
        },
    ]
    lhu_agreements = [{"name": station, "status": "Signed"} for station in STATION_MAP]
    return render_template(
        "dashboard/privacy.html",
        roles=roles,
        lhu_agreements=lhu_agreements,
        session_timeout_minutes=session_timeout_minutes,
        max_login_attempts=max_login_attempts,
        recycle_bin_days=recycle_bin_days,
        recycle_bin_status=recycle_bin_status,
        patient_retention_days=patient_retention_days,
        patient_retention_due=patient_retention_due,
        patient_retention_due_count=patient_retention_due_count,
        retention_page=retention_page,
        retention_per_page=retention_per_page,
        retention_total_pages=retention_total_pages,
        retention_page_sizes=RETENTION_PAGE_SIZES,
        patient_retention_oldest_screening=patient_retention_oldest_screening,
        patient_retention_cutoff_date=patient_retention_cutoff_date,
        patient_retention_selection_hash=session.get("patient_retention_selection_hash"),
    )


@admin_bp.route("/privacy-security/patient-retention/policy", methods=["POST"])
@login_required
def update_patient_retention_policy():
    from app.models import settings as settings_model

    raw = request.form.get("patient_retention_days")
    try:
        if raw in (None, "", "None"):
            days = None
        else:
            days = int(raw)
    except (TypeError, ValueError):
        flash("Please choose a valid patient retention period.", "error")
        return redirect(url_for("admin.privacy_security") + "#data")

    if days not in settings_model.ALLOWED_PATIENT_RETENTION_DAYS:
        flash("Please choose a valid patient retention period.", "error")
        return redirect(url_for("admin.privacy_security") + "#data")

    previous = settings_model.get_patient_retention_days()
    settings_model.set_patient_retention_days(days)
    label = "disabled" if days is None else f"{days} days"
    previous_label = "disabled" if previous is None else f"{previous} days"
    _audit_event(f"Patient record retention updated from {previous_label} to {label}", "Info")
    flash(f"Patient record retention updated to {label}.", "success")
    return redirect(url_for("admin.privacy_security") + "#data")


@admin_bp.route("/privacy-security/patient-retention/action", methods=["POST"])
@login_required
def patient_retention_action():
    from app.models import patient_model

    action = (request.form.get("action") or "").strip().lower()
    if request.form.get("download_archive") == "1" or action == "export":
        return _download_retention_archive(patient_model)

    try:
        patient_ids, retention_days = _retention_selection(patient_model)
        if action not in ("anonymize", "delete"):
            raise ValueError("Choose anonymize or delete permanently.")

        try:
            confirmed_count = int(request.form.get("confirmation_count", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError("Type the exact number of selected records to confirm.") from exc
        if confirmed_count != len(patient_ids):
            raise ValueError("The typed number must match the number of selected records.")
        if request.form.get("confirm_irreversible") not in ("1", "on", "true"):
            raise ValueError("Confirm that you understand this action cannot be undone.")

        archive_hash = session.get("patient_retention_archive_hash")
        if not archive_hash or not hmac.compare_digest(archive_hash, _retention_ids_hash(patient_ids)):
            raise ValueError("Download the archive copy for this exact selection first.")

        result = patient_model.apply_patient_retention_action(patient_ids, action)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.privacy_security"))
    except Exception:
        flash("The retention batch failed. No records were changed.", "error")
        return redirect(url_for("admin.privacy_security"))

    patient_codes = result["patient_codes"]
    code_summary = ", ".join(patient_codes[:20])
    if len(patient_codes) > 20:
        code_summary += f" +{len(patient_codes) - 20} more"
    audit_action = (
        f"Patient retention {action}: records={result['processed_count']}; "
        f"anonymized={result['anonymized_count']}; deleted={result['deleted_count']}; "
        f"consent_forced_deletes={result['consent_deleted_count']}; "
        f"retention_days={retention_days}; cutoff_date={result['cutoff_date']}; "
        f"patient_codes={code_summary}"
    )
    session.pop("patient_retention_archive_hash", None)
    session.pop("patient_retention_selection_hash", None)
    _audit_event(audit_action, "Critical")

    if result["consent_deleted_count"]:
        flash(
            f"{result['anonymized_count']} patient record(s) anonymized and "
            f"{result['consent_deleted_count']} record(s) deleted because research consent was not granted.",
            "success",
        )
    elif action == "delete":
        flash(f"{result['deleted_count']} patient record(s) deleted permanently.", "success")
    else:
        flash(f"{result['anonymized_count']} patient record(s) anonymized.", "success")
    return redirect(url_for("admin.privacy_security"))


@admin_bp.route("/privacy-security/session-timeout", methods=["POST"])
@login_required
def update_session_timeout():
    from app.models import settings as settings_model

    minutes = request.form.get("session_timeout_minutes", type=int)
    max_attempts = request.form.get("max_login_attempts", type=int)
    if (minutes not in settings_model.ALLOWED_SESSION_TIMEOUTS or
            max_attempts not in settings_model.ALLOWED_MAX_LOGIN_ATTEMPTS):
        flash("Please choose valid session timeout and failed-login attempt values.", "error")
        return redirect(url_for("admin.privacy_security"))

    previous_minutes = settings_model.get_session_timeout_minutes()
    previous_max_attempts = settings_model.get_max_login_attempts()
    changed = []
    if minutes != previous_minutes:
        settings_model.set_session_timeout_minutes(minutes)
        changed.append(f"session timeout to {minutes} minute(s)")
    if max_attempts != previous_max_attempts:
        settings_model.set_max_login_attempts(max_attempts)
        changed.append(f"maximum failed login attempts to {max_attempts}")
    if changed:
        _audit_event("Security settings updated: " + "; ".join(changed), "Info")
        flash("Security settings updated: " + "; ".join(changed) + ".", "success")
    else:
        flash("Security settings unchanged.", "success")
    return redirect(url_for("admin.privacy_security"))


@admin_bp.route("/privacy-security/role-login-toggle", methods=["POST"])
@login_required
def role_login_toggle():
    from app.models import settings as settings_model

    role = request.form.get("role")
    enabled = request.form.get("enabled") == "1"
    try:
        settings_model.set_role_login_enabled(role, enabled)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("admin.privacy_security"))
    severity = "Info" if enabled else "Critical"
    state = "enabled" if enabled else "disabled"
    _audit_event(f"Logins {state} for {role}", severity)
    flash(f"Logins {state} for {role.replace('_', ' ')}.", "success")
    return redirect(url_for("admin.privacy_security"))


@admin_bp.route("/privacy-security/role-export-toggle", methods=["POST"])
@login_required
def role_export_toggle():
    from app.models import settings as settings_model

    role = request.form.get("role")
    enabled = request.form.get("enabled") == "1"
    try:
        settings_model.set_role_export_enabled(role, enabled)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("admin.privacy_security"))
    state = "enabled" if enabled else "disabled"
    _audit_event(f"Exports {state} for {role}", "Info")
    flash(f"Exports {state} for {role.replace('_', ' ')}.", "success")
    return redirect(url_for("admin.privacy_security"))


@admin_bp.route("/privacy-security/role-force-signout", methods=["POST"])
@login_required
def role_force_signout():
    from app.models import settings as settings_model

    role = request.form.get("role")
    try:
        settings_model.bump_security_version(role)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("admin.privacy_security"))
    if session.get("user_role") == role:
        session["security_version"] = settings_model.get_security_version(role)
    _audit_event(f"All {role} sessions signed out", "Critical")
    flash(f"All active {role.replace('_', ' ')} sessions have been signed out.", "success")
    return redirect(url_for("admin.privacy_security"))


@admin_bp.route("/privacy-security/data-retention", methods=["POST"])
@login_required
def update_data_retention():
    from app.models import settings as settings_model
    from app.models import patient_model

    raw = request.form.get("recycle_bin_days")
    try:
        days = int(raw)
        settings_model.set_recycle_bin_days(days)
    except (TypeError, ValueError):
        flash("Please choose a valid retention period.", "error")
        return redirect(url_for("admin.privacy_security") + "#data")
    label = f"{days} day(s)"
    _audit_event(f"Data retention threshold updated to {label}", "Info")
    removed = patient_model.run_retention_purge(force=True)
    message = f"Recycle Bin retention updated to {days} days."
    if removed:
        message += f" {removed} expired patient record(s) removed immediately."
    flash(message, "success")
    return redirect(url_for("admin.privacy_security") + "#data")


@admin_bp.route("/privacy-security/change-password", methods=["POST"])
@login_required
def change_password():
    errors = auth_controller.change_own_password(session["user_id"], request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("admin.privacy_security"))

    _audit_event("Password changed", "Warning")
    flash("Password changed successfully.", "success")
    return redirect(url_for("admin.privacy_security"))


@admin_bp.route("/green-computing")
@role_required("medical_officer")
def green_computing():
    gc, embedded_records, inferences = metrics_controller.dashboard_context(get_db())
    return render_template("metrics/green.html", gc=gc, embedded_records=embedded_records,
                           inferences=inferences)


@admin_bp.route("/green-computing/events")
@role_required("medical_officer")
def green_events():
    ctx = metrics_controller.events_page_context(
        get_db(), request.args.get("page", 1, type=int), request.args.get("type"))
    return render_template("metrics/events_log.html", **ctx)


@admin_bp.route("/green-computing/pending")
@role_required("medical_officer")
def green_pending():
    ctx = metrics_controller.pending_page_context(
        get_db(), request.args.get("page", 1, type=int), request.args.get("status", "pending"))
    return render_template("metrics/pending_sync.html", **ctx)


@admin_bp.route("/audit-trails")
@login_required
def audit_trails():
    db = get_db()
    page_size = 12
    total_count = audit_model.get_logs_count(db)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = max(1, min(request.args.get("page", 1, type=int) or 1, total_pages))
    logs = audit_model.get_recent_logs(
        db, limit=page_size, offset=(page - 1) * page_size
    )
    audit_now = datetime.utcnow()
    audit_date = f"{audit_now.strftime('%B')} {audit_now.day}"
    return render_template(
        "dashboard/audit_trails.html", logs=logs, audit_date=audit_date,
        page=page, total_pages=total_pages, total_count=total_count,
    )


@admin_bp.route("/audit-trails/export")
@login_required
def audit_trails_export():
    db = get_db()
    _audit_event("Exported CSV: audit trails", "Warning")
    logs = audit_model.get_recent_logs(db, limit=audit_model.get_logs_count(db))

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["Time", "Date", "User", "Role", "Action", "IP Address", "Severity"])
    for log in logs:
        writer.writerow([
            log["time"], log["date"], log["user"], log["role"], log["action"],
            log["ip"], log["severity"],
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=audit_trails.csv"
    return response