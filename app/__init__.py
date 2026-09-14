from flask import Flask, redirect, url_for

def create_app():
    # Initialize the app
    app = Flask(__name__)
    app.secret_key = "fbs-thesis-secret-key"

    @app.route('/')
    def index():
        return redirect(url_for('patient.patient_dashboard'))

    from app.controllers.patient_controller import patient_bp
    app.register_blueprint(patient_bp)

    return app