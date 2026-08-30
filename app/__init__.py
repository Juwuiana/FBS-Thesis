from flask import Flask, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.routing.exceptions import BuildError

db = SQLAlchemy()

def create_app(config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "change-me-in-production"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fbs_thesis.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if config:
        app.config.update(config)

    db.init_app(app)

    from app.views.nurse_views import nurse_bp

    app.register_blueprint(nurse_bp)

    @app.template_filter("number_format")
    def number_format(value):
        try:
            return f"{value:,}"
        except (ValueError, TypeError):
            return value

    def safe_url_for(endpoint, fallback="#", **values):
        """
        A wrapper around Flask's url_for that returns a fallback URL 
        """
        try:
            return url_for(endpoint, **values)
        except BuildError:
            return fallback

    app.jinja_env.globals["safe_url_for"] = safe_url_for

    with app.app_context():
        db.create_all()

    return app