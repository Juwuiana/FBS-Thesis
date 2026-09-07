from app import db
from datetime import datetime


class Patient(db.Model):
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    patient_code = db.Column(db.String(30), unique=True, nullable=False)  # e.g. "CAB-2025-0156"

    # Link to the patient's login account — per project design, this account
    # is auto-generated at nurse intake (Patient ID as username, one-time
    # temp password), so this stays nullable until that flow creates it.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=True)
    user = db.relationship('User', backref=db.backref('patient_profile', uselist=False))

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    sex = db.Column(db.String(1), nullable=True)  # 'M' | 'F'
    barangay = db.Column(db.String(100), nullable=True)
    contact_number = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    screenings = db.relationship(
        'Screening', backref='patient', lazy=True,
        order_by='Screening.screened_at.desc()'
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self):
        return f'<Patient {self.patient_code} {self.full_name}>'