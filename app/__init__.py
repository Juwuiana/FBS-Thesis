from flask import Flask, url_for
from werkzeug.routing.exceptions import BuildError
from flask import Flask, redirect, url_for

def create_app(config=None):
def create_app():
    # Initialize the app
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "change-me-in-production"

    if config:
        app.config.update(config)

    from app.controllers.nurse_controller import nurse_bp
    app.register_blueprint(nurse_bp)

    @app.template_filter("number_format")
    def number_format(value):
        try:
            return f"{value:,}"
        except (ValueError, TypeError):
            return value

    def safe_url_for(endpoint, fallback="#", **values):
        try:
            return url_for(endpoint, **values)
        except BuildError:
            return fallback

    app.jinja_env.globals["safe_url_for"] = safe_url_for

    from app.models.db import run_migrations
    run_migrations()
    app.secret_key = "fbs-thesis-secret-key"

    @app.route('/')
    def index():
        return redirect(url_for('patient.patient_dashboard'))

    from app.controllers.patient_controller import patient_bp
    app.register_blueprint(patient_bp)

    return app