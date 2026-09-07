from app import db
from datetime import datetime


class Screening(db.Model):
    __tablename__ = 'screenings'

    id = db.Column(db.Integer, primary_key=True)
    screening_code = db.Column(db.String(30), unique=True, nullable=False)  # e.g. "CAB-2025-0156"
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)

    fbs_value = db.Column(db.Float, nullable=False)  # mg/dL

    # ADA (2024) threshold-based category, from raw FBS value directly.
    ada_category = db.Column(db.String(20), nullable=False)  # 'Normal' | 'Pre-Diabetic' | 'Diabetic'

    # ML-predicted probability + resulting risk level bucket (separate
    # classification from ada_category — this is the model's output).
    predicted_probability = db.Column(db.Float, nullable=True)
    ml_risk_level = db.Column(db.String(20), nullable=False)  # 'Low' | 'Moderate' | 'High'

    bmi = db.Column(db.Float, nullable=True)
    waist_circumference_cm = db.Column(db.Float, nullable=True)
    systolic_bp = db.Column(db.Integer, nullable=True)
    diastolic_bp = db.Column(db.Integer, nullable=True)

    recommendation_text = db.Column(db.Text, nullable=True)
    next_followup_date = db.Column(db.Date, nullable=True)
    referred_to = db.Column(db.String(150), nullable=True)

    model_used = db.Column(db.String(50), nullable=True)  # which trained model produced this prediction

    screened_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Screening {self.screening_code} FBS={self.fbs_value} risk={self.ml_risk_level}>'