from flask import Blueprint, render_template, request, redirect, url_for, abort
from datetime import datetime

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

STAFF_ROLES = ["Admin", "Health Officer", "LHU Nurse", "Encoder"]
STATIONS = ["Sta. Rosa", "Cabuyao", "Calamba", "Biñan", "San Pedro"]
STAFF_STATUSES = ["Active", "Inactive", "On Leave"]

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
def data_management():
    return render_template("dashboard/records.html", employees=EMPLOYEES)


# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# Appends to the in-memory EMPLOYEES list above — does NOT persist to a
# database (there isn't one yet) and resets on app restart. The ID scheme
# below (EMP-2025-{count+1}) is only safe because nothing ever removes an
# employee; a real implementation should let the DB assign the ID instead.
@admin_bp.route("/data-management/add", methods=["GET", "POST"])
def add_staff():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "").strip()
        station = request.form.get("station", "").strip()
        contact = request.form.get("contact", "").strip()
        status = request.form.get("status", "").strip()

        errors = []
        if not name:
            errors.append("Full name is required.")
        if not email:
            errors.append("Email is required.")
        if role not in STAFF_ROLES:
            errors.append("Please select a valid role.")
        if station not in STATIONS:
            errors.append("Please select a valid station.")
        if status not in STAFF_STATUSES:
            errors.append("Please select a valid status.")

        if errors:
            return render_template(
                "admin/add_staff.html",
                roles=STAFF_ROLES, stations=STATIONS, statuses=STAFF_STATUSES,
                errors=errors,
                form_data={"name": name, "email": email, "role": role,
                           "station": station, "contact": contact, "status": status},
            )

        now = datetime.now()
        new_employee = {
            "id": f"EMP-2025-{len(EMPLOYEES) + 1:03d}",
            "name": name,
            "email": email,
            "role": role,
            "station": station,
            "contact": contact,
            "status": status,
            "date_added": f"{now.strftime('%b')} {now.day}, {now.year}",
        }
        EMPLOYEES.append(new_employee)
        return redirect(url_for("admin.staff_detail", employee_id=new_employee["id"]))

    return render_template(
        "admin/add_staff.html",
        roles=STAFF_ROLES, stations=STATIONS, statuses=STAFF_STATUSES,
        errors=[], form_data={},
    )
# ── END TEMPORARY STUB ───────────────────────────────────────────────────


# ── TEMPORARY STUB ────────────────────────────────────────────────────────
# Shows full staff info (read-only) with Role as the one editable field, per
# spec: "view and edit the staffs... edit only the roles given." Updating
# only mutates the in-memory EMPLOYEES list above — it does NOT persist to
# a database (there isn't one yet) and resets on app restart. When a real
# Staff/User model lands, replace the lookup/update below with actual
# queries and delete this comment.
@admin_bp.route("/data-management/<employee_id>")
def staff_detail(employee_id):
    employee = next((e for e in EMPLOYEES if e["id"] == employee_id), None)
    if employee is None:
        abort(404)
    return render_template("admin/staff_detail.html", employee=employee, roles=STAFF_ROLES)


@admin_bp.route("/data-management/<employee_id>/update-role", methods=["POST"])
def staff_update_role(employee_id):
    employee = next((e for e in EMPLOYEES if e["id"] == employee_id), None)
    if employee is None:
        abort(404)

    new_role = request.form.get("role", "").strip()
    if new_role in STAFF_ROLES:
        employee["role"] = new_role

    return redirect(url_for("admin.staff_detail", employee_id=employee_id))
# ── END TEMPORARY STUB ───────────────────────────────────────────────────


@admin_bp.route("/privacy-security")
def privacy_security():
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
    )


@admin_bp.route("/green-computing")
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
