from flask import Blueprint, render_template, request, redirect, url_for, abort, flash
from datetime import datetime
import re

from werkzeug.security import generate_password_hash

from app.controllers import metrics_controller
from app.db import get_db
from app.views.auth_views import login_required, require_role_for_blueprint, role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# The whole Admin section is medical_officer-only (the nurse/patient portals are separate
# blueprints for the other roles). Applied once here instead of on every view.
require_role_for_blueprint(admin_bp, "medical_officer")

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
    metrics = {
        "total_screened": 1392,
        "total_screened_change": "+1.2% vs last week",
        "at_risk": 276,
        "at_risk_pct": 19.8,
        "at_risk_change": "+8% vs last week",
        "high_risk": 82,
        "high_risk_pct": 5.9,
        "high_risk_change": "+3% vs last week",
        "avg_fbs": 111.4,
        "avg_fbs_change": "+2.6 vs last week",
        "model_accuracy": 89.3,
    }

    risk_distribution = {
        "low": {"count": 1073, "pct": 72.1},
        "moderate": {"count": 237, "pct": 17.0},
        "high": {"count": 82, "pct": 5.9},
    }

    barangay_list = [
        {"name": "Kanluran", "count": 58},
        {"name": "Market Area", "count": 47},
        {"name": "Dila", "count": 41},
        {"name": "Dita", "count": 33},
        {"name": "Malitlit", "count": 29},
    ]

    recent_screenings = [
        {"id": "CAB-2025-0156", "name": "Juan Dela Cruz", "fbs": 142,
         "category": "Diabetic", "risk": "High", "date": "May 27, 2025"},
        {"id": "CAB-2025-0155", "name": "Maria Santos", "fbs": 118,
         "category": "Prediabetic", "risk": "Low", "date": "May 27, 2025"},
        {"id": "CAB-2025-0154", "name": "Pedro Reyes", "fbs": 96,
         "category": "Normal", "risk": "Moderate", "date": "May 27, 2025"},
        {"id": "CAB-2025-0153", "name": "Ana Garcia", "fbs": 134,
         "category": "Prediabetic", "risk": "High", "date": "May 27, 2025"},
        {"id": "CAB-2025-0152", "name": "Lisa Perez", "fbs": 155,
         "category": "Diabetic", "risk": "High", "date": "May 26, 2025"},
    ]

    model_performance = {
        "accuracy": 89.3,
        "precision": 0.87,
        "recall": 0.88,
        "f1_score": 0.87,
        "roc_auc": 0.93,
    }

    return render_template(
        "dashboard/index.html",
        metrics=metrics,
        risk_distribution=risk_distribution,
        barangay_list=barangay_list,
        recent_screenings=recent_screenings,
        model_performance=model_performance,
    )


@admin_bp.route("/reliability")
@login_required
def reliability():
    benchmarks = [
        {"name": "Random Forest", "accuracy": 0.883, "precision": 0.871,
         "recall": 0.856, "f1": 0.863, "auc": 0.889, "best": True},
        {"name": "XGBoost",       "accuracy": 0.871, "precision": 0.858,
         "recall": 0.843, "f1": 0.850, "auc": 0.878, "best": False},
        {"name": "LightGBM",      "accuracy": 0.865, "precision": 0.851,
         "recall": 0.837, "f1": 0.844, "auc": 0.872, "best": False},
    ]
    best_model = {
        "name":      "Random Forest",
        "accuracy":  0.883,
        "precision": 0.871,
        "recall":    0.856,
        "f1":        0.863,
        "auc":       0.889,
        "test_n":    800,
        "cm": {"tn": 512, "fp": 48, "fn": 65, "tp": 175},
    }
    optimization = {
        "technique":      "Post-Training Quantization",
        "original_size":  "2.1 MB",
        "optimized_size": "182 KB",
        "reduction":      "91% \u2198",
        "accuracy_loss":  "< 0.5%",
        "inference_time": "0.4 ms",
        "target_device":  "Rpi Zero 2W",
    }
    training_set = {
        "source":            "1 LHU \u2013 Santa Rosa City",
        "total_records":     4820,
        "diabetic_count":    1644,
        "diabetic_pct":      34.1,
        "non_diabetic_count": 3176,
        "non_diabetic_pct":  65.9,
        "train_split":       70,
        "test_split":        30,
        "primary_feature":   "FBS (mg/dL)",
    }
    feature_importance = [
        {"name": "FBS (mg/dL)",  "importance": 0.5821},
        {"name": "Age",           "importance": 0.1342},
        {"name": "BMI",           "importance": 0.0987},
        {"name": "Systolic BP",   "importance": 0.0765},
        {"name": "Diastolic BP",  "importance": 0.0534},
        {"name": "Sex",           "importance": 0.0312},
        {"name": "Waist Circum.", "importance": 0.0239},
    ]
    cv = {
        "fold_scores": [0.881, 0.893, 0.876, 0.901, 0.885,
                        0.879, 0.897, 0.868, 0.891, 0.883],
        "mean_auc": 0.885,
        "std_auc":  0.009,
        "min_auc":  0.868,
        "max_auc":  0.901,
    }
    # Simplified ROC curve points (FPR, TPR pairs)
    roc_points = [
        {"fpr": 0.00, "tpr": 0.00},
        {"fpr": 0.02, "tpr": 0.32},
        {"fpr": 0.05, "tpr": 0.55},
        {"fpr": 0.10, "tpr": 0.72},
        {"fpr": 0.15, "tpr": 0.80},
        {"fpr": 0.20, "tpr": 0.85},
        {"fpr": 0.30, "tpr": 0.91},
        {"fpr": 0.40, "tpr": 0.94},
        {"fpr": 0.50, "tpr": 0.96},
        {"fpr": 0.70, "tpr": 0.98},
        {"fpr": 1.00, "tpr": 1.00},
    ]
    return render_template(
        "model/reliability.html",
        benchmarks=benchmarks,
        best_model=best_model,
        optimization=optimization,
        training_set=training_set,
        feature_importance=feature_importance,
        cv=cv,
        roc_points=roc_points,
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
