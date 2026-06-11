from flask import Flask, redirect, url_for

def create_app():
    # Initialize the app
    app = Flask(__name__)
    app.secret_key = "fbs-thesis-secret-key"

    @app.route('/')
    def index():
        return redirect(url_for('patient.patient_dashboard'))

    # Register ONLY the Patient Blueprint (because we are on the patient branch!)
    from app.views.patient_views import patient_bp
    app.register_blueprint(patient_bp)

    return app