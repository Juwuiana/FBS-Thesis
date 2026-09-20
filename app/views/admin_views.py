from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from datetime import datetime, timedelta
import re

from werkzeug.security import generate_password_hash

from app.views.auth_views import login_required
from app.db import get_db
from app.models.model_performance_model import list_models, get_best_model
from app.models.patient_model import _compute_age



admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

STAFF_ROLES = ["Health Officer", "LHU Nurse"]
STATIONS = ["RHU I", "RHU II"]
STAFF_STATUSES = ["Approved", "Rejected", "Pending"]

# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# In-memory only — resets whenever the app restarts. There is no Staff/User
# model or DB table for this yet. Moved to module scope (out of
# data_management()) so the new staff detail/edit route below can look up
# and update the same records the list page shows. When a real model
# lands, replace EMPLOYEES with an actual query and delete this comment.
EMPLOYEES = [
    {"id": "EMP-2025-001", "name": "Linda Walker",    "email": "l.walker@lhu.gov.ph",
     "role": "Health Officer", "station": "Sta. Rosa", "contact": "09171234567",
     "status": "Active",    "date_added": "Jan 10, 2025"},
    {"id": "EMP-2025-002", "name": "Kurt Pernia",       "email": "k.pernia@lhu.gov.ph",
     "role": "LHU Nurse",     "station": "Cabuyao",   "contact": "09182345678",
     "status": "Active",    "date_added": "Jan 10, 2025"},
    {"id": "EMP-2025-003", "name": "Clarise Espiritu",  "email": "c.espiritu@lhu.gov.ph",
     "role": "Admin",         "station": "Sta. Rosa", "contact": "09193456789",
     "status": "Active",    "date_added": "Jan 11, 2025"},
    {"id": "EMP-2025-004", "name": "Jerome Elano",      "email": "j.elano@lhu.gov.ph",
     "role": "Encoder",       "station": "Calamba",   "contact": "09204567890",
     "status": "Active",    "date_added": "Jan 12, 2025"},
    {"id": "EMP-2025-005", "name": "Maria Santos",      "email": "m.santos@lhu.gov.ph",
     "role": "LHU Nurse",     "station": "Biñan",     "contact": "09215678901",
     "status": "On Leave",  "date_added": "Feb 3, 2025"},
    {"id": "EMP-2025-006", "name": "Pedro Dela Cruz",   "email": "p.delacruz@lhu.gov.ph",
     "role": "Health Officer","station": "San Pedro", "contact": "09226789012",
     "status": "Active",    "date_added": "Feb 10, 2025"},
    {"id": "EMP-2025-007", "name": "Ana Garcia",        "email": "a.garcia@lhu.gov.ph",
     "role": "Encoder",       "station": "Cabuyao",   "contact": "09237890123",
     "status": "Inactive",  "date_added": "Mar 1, 2025"},
    {"id": "EMP-2025-008", "name": "Jose Reyes",        "email": "j.reyes@lhu.gov.ph",
     "role": "LHU Nurse",     "station": "Calamba",   "contact": "09248901234",
     "status": "Active",    "date_added": "Mar 15, 2025"},
]
# ── END TEMPORARY STUB ───────────────────────────────────────────────────

@admin_bp.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()

    total_screened = conn.execute("SELECT COUNT(*) FROM lab_screenings").fetchone()[0]
    at_risk_count = conn.execute(
        "SELECT COUNT(*) FROM lab_screenings WHERE final_risk_level IN ('Moderate', 'High')"
    ).fetchone()[0]
    high_risk_count = conn.execute(
        "SELECT COUNT(*) FROM lab_screenings WHERE final_risk_level = 'High'"
    ).fetchone()[0]
    at_risk_pct = round(100 * at_risk_count / total_screened, 1) if total_screened else 0
    high_risk_pct = round(100 * high_risk_count / total_screened, 1) if total_screened else 0

    avg_fbs_row = conn.execute("SELECT AVG(fbs_mg_dl) FROM lab_screenings").fetchone()[0]
    avg_fbs = round(avg_fbs_row, 1) if avg_fbs_row else 0

    best = get_best_model()
    model_accuracy = (
        round(best["accuracy"] * 100, 1)
        if best and best.get("accuracy") is not None
        else None
    )

    metrics = {
        "total_screened": total_screened,
        "at_risk": at_risk_count, "at_risk_pct": at_risk_pct,
        "high_risk": high_risk_count, "high_risk_pct": high_risk_pct,
        "avg_fbs": avg_fbs,
        "model_accuracy": model_accuracy,
    }

    risk_rows = conn.execute(
        "SELECT final_risk_level, COUNT(*) FROM lab_screenings "
        "WHERE final_risk_level IS NOT NULL GROUP BY final_risk_level"
    ).fetchall()
    risk_counts = {row[0]: row[1] for row in risk_rows}
    low_count = risk_counts.get("Low", 0)
    moderate_count = risk_counts.get("Moderate", 0)
    high_count = risk_counts.get("High", 0)
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

    recent_rows = conn.execute(
        """
        SELECT ls.id, p.first_name, p.middle_name, p.last_name, p.birthdate, p.sex,
               ls.fbs_mg_dl, ls.model_predicted_risk_level, ls.final_risk_level, ls.test_datetime
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

    today = datetime.utcnow().date()
    start_day = today - timedelta(days=6)
    period_rows = conn.execute(
        "SELECT test_datetime, final_risk_level FROM lab_screenings WHERE date(test_datetime) >= date(?)",
        (start_day.isoformat(),),
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
    timeline_labels, timeline_total, timeline_at_risk = [], [], []
    for i in range(7):
        d = start_day + timedelta(days=i)
        timeline_labels.append(d.strftime("%b %d"))
        timeline_total.append(day_totals.get(d, 0))
        timeline_at_risk.append(day_at_risk.get(d, 0))
    timeline = {"labels": timeline_labels, "totalScreened": timeline_total, "atRisk": timeline_at_risk}

    model_performance = None
    if best:
        model_performance = {
            "accuracy": round(best["accuracy"] * 100, 1) if best.get("accuracy") is not None else None,
            "precision": best["precision_score"],
            "recall": best["recall_score"],
            "f1_score": best["f1_score"],
            "roc_auc": best["roc_auc"],
        }

    return render_template(
        "dashboard/index.html",
        metrics=metrics, risk_distribution=risk_distribution,
        barangay_list=barangay_list, recent_screenings=recent_screenings,
        model_performance=model_performance, timeline=timeline,
    )

@admin_bp.route("/reliability")
@login_required
def reliability():
    logs = list_models()
    if not logs:
        abort(404, "No model performance data found. Run scripts/seed_model_performance.py first.")
 
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
        # {} until a raw NxN export exists; template should treat an empty
        # dict as "not available yet" rather than assuming tn/fp/fn/tp keys.
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


@admin_bp.route("/data-management/add", methods=["GET", "POST"])
@login_required
def add_staff():
    from app.models import user as user_model

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "").strip()
        station = request.form.get("station", "").strip()
        contact = request.form.get("contact", "").strip()
        password = request.form.get("password", "")

        errors = []
        name_parts = name.split()
        if len(name_parts) < 2:
            errors.append("Enter the employee's first and last name.")
        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            errors.append("Enter a valid email address.")
        elif user_model.email_exists(email):
            errors.append("An account with this email already exists.")
        if role not in STAFF_ROLES:
            errors.append("Please select a valid role.")
        if station not in STATIONS:
            errors.append("Please select a valid station.")
        normalized_contact = contact.lstrip("+").lstrip("0")
        if not re.match(r"^9\d{9}$", normalized_contact):
            errors.append("Enter a valid 10-digit mobile number starting with 9.")
        if len(password) < 12:
            errors.append("Password must be at least 12 characters.")

        if errors:
            return render_template(
                "admin/add_staff.html",
                roles=STAFF_ROLES, stations=STATIONS,
                errors=errors,
                form_data={"name": name, "email": email, "role": role,
                           "station": station, "contact": contact},
            )

        role_map = {
            "Health Officer": "medical_officer",
            "LHU Nurse": "health_worker",
        }
        facility_map = {"RHU I": "rhui", "RHU II": "rhuii"}
        user_id = user_model.create_user(
            {
                "first_name": name_parts[0],
                "middle_name": " ".join(name_parts[1:-1]) or None,
                "last_name": name_parts[-1],
                "birthday": "1990-01-01",
                "sex": "male",
                "email": email,
                "phone": normalized_contact,
                "role": role_map[role],
                "facility": facility_map[station],
                "barangay": "aplaya",
            },
            generate_password_hash(password),
            status="approved",
        )
        flash("Employee account created successfully.", "success")
        return redirect(url_for("admin.staff_detail", employee_id=f"EMP-{user_id:05d}"))

    return render_template(
        "admin/add_staff.html",
        roles=STAFF_ROLES, stations=STATIONS,
        errors=[], form_data={},
    )


# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# Shows full staff info (read-only) with Role as the one editable field, per
# spec: "view and edit the staffs... edit only the roles given." Updating
# only mutates the in-memory EMPLOYEES list above — it does NOT persist to
# a database (there isn't one yet) and resets on app restart. When a real
# Staff/User model lands, replace the lookup/update below with actual
# queries and delete this comment.
@admin_bp.route("/data-management/<employee_id>")
@login_required
def staff_detail(employee_id):
    from app.models import user as user_model

    employee = user_model.get_employee_by_id(employee_id)
    if employee is None:
        abort(404)
    return render_template("admin/staff_detail.html", employee=employee, roles=STAFF_ROLES)


@admin_bp.route("/data-management/<employee_id>/update-role", methods=["POST"])
@login_required
def staff_update_role(employee_id):
    from app.models import user as user_model

    employee = user_model.get_employee_by_id(employee_id)
    if employee is None:
        abort(404)

    new_role = request.form.get("role", "").strip()
    if user_model.update_user_role(employee_id, new_role):
        flash("Employee role updated successfully.", "success")
    else:
        flash("Please select a valid role.", "error")

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
    flash("Account rejected. The user cannot sign in.", "success")
    return redirect(url_for("admin.staff_detail", employee_id=employee_id))


@admin_bp.route("/data-management/<employee_id>/delete", methods=["POST"])
@login_required
def delete_staff(employee_id):
    from app.models import user as user_model

    if not user_model.delete_user_by_employee_id(employee_id):
        abort(404)

    flash("Employee account deleted successfully.", "success")
    return redirect(url_for("admin.data_management"))
# ── END TEMPORARY STUB ───────────────────────────────────────────────────


@admin_bp.route("/privacy-security")
@login_required
def privacy_security():
    from app.models import settings as settings_model

    session_timeout_minutes = settings_model.get_session_timeout_minutes()
    roles = [
        {"name": "Patient",        "screen": True,  "view_records": "Own records", "export": "No",      "admin": "No"},
        {"name": "LHU Nurse",      "screen": True,  "view_records": "Yes",         "export": "Limited", "admin": "No"},
        {"name": "Health Officer", "screen": True,  "view_records": "Yes",         "export": "Yes",     "admin": "Read"},
        {"name": "Admin",          "screen": True,  "view_records": "Yes",         "export": "Yes",     "admin": "Yes"},
    ]
    lhu_agreements = [
        {"name": "Calamba",   "status": "Signed"},
        {"name": "Santa Rosa","status": "Signed"},
        {"name": "Biñan",     "status": "Signed"},
        {"name": "San Pedro", "status": "Pending"},
        {"name": "Cabuyao",   "status": "Pending"},
    ]
    retention_policy = [
        {"label": "Retention period",  "value": "5 years"},
        {"label": "Anonymization",     "value": "On export"},
        {"label": "Right to deletion", "value": "Yes"},
        {"label": "Backup frequency",  "value": "Daily (encrypted)"},
        {"label": "Storage location",  "value": "LHU local server"},
    ]
    return render_template(
        "dashboard/privacy.html",
        roles=roles,
        lhu_agreements=lhu_agreements,
        retention_policy=retention_policy,
        session_timeout_minutes=session_timeout_minutes,
    )


@admin_bp.route("/privacy-security/session-timeout", methods=["POST"])
@login_required
def update_session_timeout():
    from app.models import settings as settings_model

    minutes = request.form.get("session_timeout_minutes", type=int)
    if minutes not in settings_model.ALLOWED_SESSION_TIMEOUTS:
        flash("Please choose a valid session timeout value.", "error")
        return redirect(url_for("admin.privacy_security"))

    settings_model.set_session_timeout_minutes(minutes)
    flash(f"Session timeout updated to {minutes} minute(s).", "success")
    return redirect(url_for("admin.privacy_security"))


@admin_bp.route("/green-computing")
@login_required
def green_computing():
    gc = {
        "energy_kwh":    1.24,
        "energy_change": "8% vs yesterday",
        "carbon":        0.58,
        "carbon_change": "12% this week",
        "green_score":   82,
        "score_change":  "5 pts vs last week",
        "sync_queue":    47,
        "uptime":        "6h 42m",
        "offline_gaps":  3,
        "is_offline":    True,
        "last_sync":     "14 min ago",
        "queued_count":  3,
        "synced_count":  4,
        "total_offline": "58 min",
        "gap_count":     3,
        "queue": {
            "screenings":  31,
            "patients":    12,
            "assessments":  4,
        },
        "energy_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "energy_values": [1.0,   1.6,  0.7,  1.1,  1.6,  0.5,  0.8],
        "carbon_values": [0.45,  0.55, 0.38, 0.48, 0.60, 0.32, 0.42],
        "score_breakdown": [
            {"label": "Energy Efficiency", "pct": 88},
            {"label": "Carbon per Screen", "pct": 74},
            {"label": "Idle Power Usage",  "pct": 62},
            {"label": "Renewable Usage",   "pct": 90},
        ],
        "energy_breakdown": [
            {"label": "Screening App",  "pct": 38, "kwh": 0.47, "color": "#4caf50"},
            {"label": "Database Sync",  "pct": 25, "kwh": 0.31, "color": "#1565c0"},
            {"label": "Display & UI",   "pct": 19, "kwh": 0.24, "color": "#ff9800"},
            {"label": "Network",        "pct": 18, "kwh": 0.22, "color": "#9c27b0"},
        ],
        "conn_timeline": [
            {"online": True,  "weight": 3},
            {"online": False, "weight": 1},
            {"online": True,  "weight": 2},
            {"online": False, "weight": 1},
            {"online": True,  "weight": 3},
            {"online": False, "weight": 1},
            {"online": True,  "weight": 5},
        ],
        "offline_events": [
            {"time_range": "08:42\u201309:00", "duration": "18 min", "records": 7},
            {"time_range": "10:00\u201310:24", "duration": "24 min", "records": 12},
            {"time_range": "11:24\u201311:40", "duration": "16 min", "records": 4},
        ],
    }
    embedded_records = [
        {"id": "CAB-2026-0161", "fbs": 148, "risk": "High",     "status": "Queued", "time": "09:14"},
        {"id": "CAB-2026-0160", "fbs": 102, "risk": "Low",      "status": "Queued", "time": "09:08"},
        {"id": "CAB-2026-0159", "fbs": 127, "risk": "Moderate", "status": "Queued", "time": "08:55"},
        {"id": "CAB-2026-0158", "fbs": 91,  "risk": "Low",      "status": "Synced", "time": "08:40"},
        {"id": "CAB-2026-0157", "fbs": 162, "risk": "High",     "status": "Synced", "time": "08:22"},
        {"id": "CAB-2026-0156", "fbs": 118, "risk": "Moderate", "status": "Synced", "time": "08:10"},
        {"id": "CAB-2026-0155", "fbs": 95,  "risk": "Low",      "status": "Synced", "time": "07:58"},
    ]
    return render_template("metrics/green.html", gc=gc, embedded_records=embedded_records)


@admin_bp.route("/audit-trails")
@login_required
def audit_trails():
    logs = [
        {"time": "09:47 AM", "date": "May 27", "user": "lhu.admin",     "role": "Admin",
         "action": "User login",                               "ip": "192.168.1.12", "severity": "Info"},
        {"time": "09:44 AM", "date": "May 27", "user": "Nurse Kurt",     "role": "Nurse",
         "action": "Exported CSV",                             "ip": "192.168.1.45", "severity": "Warning"},
        {"time": "09:39 AM", "date": "May 27", "user": "Nurse Vennisse", "role": "Nurse",
         "action": "Screening saved: CAB-2025-0165",           "ip": "192.168.1.33", "severity": "Success"},
        {"time": "09:33 AM", "date": "May 27", "user": "unknown",        "role": "Unknown",
         "action": "Failed login attempt (3rd try)",           "ip": "103.22.88.14", "severity": "Critical"},
        {"time": "09:28 AM", "date": "May 27", "user": "Nurse Vennisse", "role": "Nurse",
         "action": "Patient record edited: CAB-2025-0150",     "ip": "192.168.1.22", "severity": "Info"},
        {"time": "09:21 AM", "date": "May 27", "user": "Nurse Kurt",     "role": "Nurse",
         "action": "Patient profile edited: CAB-2025-0148",    "ip": "192.168.1.45", "severity": "Info"},
        {"time": "09:14 AM", "date": "May 27", "user": "lhu.admin",      "role": "Admin",
         "action": "Role changed: Viewer \u2192 Health Officer (user: garcia_m)", "ip": "192.168.1.12", "severity": "Warning"},
        {"time": "09:08 AM", "date": "May 27", "user": "lhu.admin",      "role": "Admin",
         "action": "Monthly report generated (PDF)",           "ip": "192.168.1.12", "severity": "Info"},
        {"time": "09:00 AM", "date": "May 27", "user": "Nurse Kurt",     "role": "Nurse",
         "action": "User login",                               "ip": "192.168.1.33", "severity": "Info"},
        {"time": "08:55 AM", "date": "May 27", "user": "lhu.admin",      "role": "Admin",
         "action": "Patient record deleted: CAB-2024-0088 (approved)",   "ip": "192.168.1.12", "severity": "Critical"},
        {"time": "08:48 AM", "date": "May 27", "user": "lhu.admin",      "role": "Admin",
         "action": "Bulk data import: 120 patient records",   "ip": "192.168.1.12", "severity": "Warning"},
        {"time": "08:40 AM", "date": "May 27", "user": "Nurse Venisse", "role": "Nurse",
         "action": "Profile updated: contact info changed",    "ip": "192.168.1.22", "severity": "Info"},
    ]
    return render_template("dashboard/audit_trails.html", logs=logs, audit_date="March 27")
