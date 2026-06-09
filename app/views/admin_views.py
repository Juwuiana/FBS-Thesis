from flask import Blueprint, render_template

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


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