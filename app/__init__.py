from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app(config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "change-me-in-production"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fbs_thesis.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if config:
        app.config.update(config)

    db.init_app(app)

    from app.views.auth_views import auth_bp
    from app.views.admin_views import admin_bp
    from app.views.nurse_views import nurse_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(nurse_bp)

    @app.template_filter('number_format')
    def number_format(value):
        try:
            return f'{value:,}'
        except (ValueError, TypeError):
            return value

    with app.app_context():
        db.create_all()

    return app