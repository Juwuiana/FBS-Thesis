from flask import Flask

def create_app():
    app = Flask(__name__)
    app.secret_key = "fbs-thesis-secret-key"

    from app.views.auth_views import auth_bp
    app.register_blueprint(auth_bp)

    return app