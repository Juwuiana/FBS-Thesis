from flask import Blueprint, render_template
from sqlalchemy import func
from datetime import datetime, timedelta
from app import db
from app.models.patient import Patient
from app.models.screening import Screening
from app.models.model_performance import ModelPerformanceLog
from sqlalchemy import func

nurse_bp = Blueprint('nurse', __name__, url_prefix='/nurse')

@nurse_bp.route('/nurse_dashboard')
def nurse_dashboard():
    total_screened = Screening.query.count()
    at_risk_count = Screening.query.filter(Screening.ml_risk_level.in_(["Moderate", "High"])).count()
    high_risk_count = Screening.query.filter(Screening.ml_risk_level == "High").count()

    avg_fbs_row = db.session.query(func.avg(Screening.fbs_value)).scalar()
    avg_fbs = round(avg_fbs_row, 1) if avg_fbs_row else 0

    best_model = ModelPerformanceLog.query.filter_by(is_best=True).first()
    model_accuracy = round(best_model.accuracy * 100, 1) if best_model else None

    metrics = {
        "total_screened": total_screened,
        "at_risk": at_risk_count,
        "high_risk": high_risk_count,
        "avg_fbs": avg_fbs,
        "model_accuracy": model_accuracy,
    }

    risk_counts = dict(
        db.session.query(Screening.ml_risk_level, func.count(Screening.id))
        .group_by(Screening.ml_risk_level).all()
    )
    low_count = risk_counts.get("Low", 0)
    moderate_count = risk_counts.get("Moderate", 0)
    high_count = risk_counts.get("High", 0)
    risk_distribution = {
        "low":      round(100*low_count/total_screened,1) if total_screened else 0,
        "moderate": round(100*moderate_count/total_screened,1) if total_screened else 0,
        "high":     round(100*high_count/total_screened,1) if total_screened else 0,
    }

    barangay_rows = (
        db.session.query(Patient.barangay, func.count(Screening.id).label("cnt"))
        .join(Screening, Screening.patient_id == Patient.id)
        .group_by(Patient.barangay)
        .order_by(func.count(Screening.id).desc())
        .limit(5).all()
    )
    barangay_list = [{"name": b or "Unknown", "count": c} for b, c in barangay_rows]

    recent_rows = (
        db.session.query(Screening, Patient)
        .join(Patient, Screening.patient_id == Patient.id)
        .order_by(Screening.screened_at.desc())
        .limit(5).all()
    )
    recent_registries = [
        {
            "id": s.screening_code, "name": p.full_name,
            "age": p.age, "sex": p.sex, "fbs": s.fbs_value,
            "risk": s.ml_risk_level, "date": s.screened_at.strftime("%b %d, %Y"),
        }
        for s, p in recent_rows
    ]

    today = datetime.utcnow().date()
    start_day = today - timedelta(days=6)
    period_screenings = Screening.query.filter(
        Screening.screened_at >= datetime.combine(start_day, datetime.min.time())
    ).all()
    day_totals, day_at_risk = {}, {}
    for s in period_screenings:
        d = s.screened_at.date()
        day_totals[d] = day_totals.get(d, 0) + 1
        if s.ml_risk_level in ("Moderate", "High"):
            day_at_risk[d] = day_at_risk.get(d, 0) + 1
    timeline_labels, timeline_total, timeline_at_risk = [], [], []
    for i in range(7):
        d = start_day + timedelta(days=i)
        timeline_labels.append(d.strftime("%b %d"))
        timeline_total.append(day_totals.get(d, 0))
        timeline_at_risk.append(day_at_risk.get(d, 0))
    timeline = {"labels": timeline_labels, "totalScreened": timeline_total, "atRisk": timeline_at_risk}

    model_performance = None
    if best_model:
        model_performance = {
            "accuracy": best_model.accuracy, "precision": best_model.precision,
            "recall": best_model.recall, "f1_score": best_model.f1_score,
            "roc_auc": best_model.roc_auc,
        }

    return render_template(
        'nurse/nurse_dashboard.html',
        metrics=metrics,
        risk_distribution=risk_distribution,
        barangay_list=barangay_list,
        recent_registries=recent_registries,
        timeline=timeline,
        model_performance=model_performance,
        active_page='dashboard',
    )

@nurse_bp.route('/nurse_intake')
def nurse_intake():
    return render_template('nurse/nurse_intake.html', active_page='intake')

@nurse_bp.route('/nurse_screening')
def nurse_screening():
    return render_template('nurse/nurse_screening.html', active_page='screening')

@nurse_bp.route('/nurse_health_results')
def nurse_health_results():
    return render_template('nurse/nurse_health_results.html', active_page='health_results')

@nurse_bp.route('/nurse_data_management')
def nurse_data_management():
    barangays = ["Aplaya", "Balibago", "Caingin", "Dila", "Dita", "Don Jose",
                 "Ibaba", "Kanluran (Poblacion Uno)", "Labas", "Macabling",
                 "Malitlit", "Malusak (Poblacion Dos)", "Market Area (Poblacion Tres)",
                 "Pooc (Pook)", "Pulong Santa Cruz", "Santo Domingo", "Sinalhan", "Tagapo"]

    patients = [
        {"id":"CAB-2025-0156","name":"Juan Dela Cruz","age":30,"sex":"M","fbs":142,"risk":"High","date":"May 27, 2025","barangay":"Calamba"},
        {"id":"CAB-2025-0155","name":"Maria Santos","age":32,"sex":"F","fbs":118,"risk":"Moderate","date":"May 27, 2025","barangay":"Sta. Rosa"},
        {"id":"CAB-2025-0154","name":"Pedro Reyes","age":34,"sex":"M","fbs":96,"risk":"Low","date":"May 27, 2025","barangay":"San Pedro"},
        {"id":"CAB-2025-0153","name":"Ana Garcia","age":36,"sex":"F","fbs":134,"risk":"Moderate","date":"May 27, 2025","barangay":"Cabuyao"},
        {"id":"CAB-2025-0152","name":"Jerome Elano","age":38,"sex":"M","fbs":155,"risk":"High","date":"May 26, 2025","barangay":"Biñan"},
        {"id":"CAB-2025-0151","name":"Maria Santos","age":32,"sex":"F","fbs":118,"risk":"Moderate","date":"May 26, 2025","barangay":"Calamba"},
        {"id":"CAB-2025-0150","name":"Juan Dela Cruz","age":30,"sex":"M","fbs":142,"risk":"High","date":"May 26, 2025","barangay":"Sta. Rosa"},
        {"id":"CAB-2025-0149","name":"Maria Santos","age":32,"sex":"F","fbs":118,"risk":"Moderate","date":"May 26, 2025","barangay":"San Pedro"},
        {"id":"CAB-2025-0148","name":"Pedro Reyes","age":34,"sex":"M","fbs":96,"risk":"Low","date":"May 26, 2025","barangay":"Cabuyao"},
        {"id":"CAB-2025-0147","name":"Ana Garcia","age":36,"sex":"F","fbs":134,"risk":"Moderate","date":"May 26, 2025","barangay":"Biñan"},
        {"id":"CAB-2025-0146","name":"Lisa Perez","age":45,"sex":"F","fbs":161,"risk":"High","date":"May 25, 2025","barangay":"Dila"},
        {"id":"CAB-2025-0145","name":"Ramon Cruz","age":52,"sex":"M","fbs":109,"risk":"Moderate","date":"May 25, 2025","barangay":"Dita"},
        {"id":"CAB-2025-0144","name":"Sofia Reyes","age":28,"sex":"F","fbs":88,"risk":"Low","date":"May 25, 2025","barangay":"Kanluran (Poblacion Uno)"},
        {"id":"CAB-2025-0143","name":"Carlo Mendoza","age":41,"sex":"M","fbs":147,"risk":"High","date":"May 25, 2025","barangay":"Malitlit"},
        {"id":"CAB-2025-0142","name":"Elena Flores","age":37,"sex":"F","fbs":103,"risk":"Moderate","date":"May 24, 2025","barangay":"Market Area (Poblacion Tres)"},
    ]
    return render_template('nurse/nurse_data_management.html', barangays=barangays, patients=patients, active_page='data_management')

@nurse_bp.route('/nurse_privacy_security')
def nurse_privacy_security():
    return render_template('nurse/nurse_privacy_security.html', active_page='privacy')