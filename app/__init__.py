from flask import Flask

def create_app():
    app = Flask(__name__)
    app.secret_key = "fbs-thesis-secret-key"

 #   from app.views.auth_views import auth_bp
 #   app.register_blueprint(auth_bp)

    from app.views.nurse_views import nurse_bp
    app.register_blueprint(nurse_bp)

    return app

from flask import Flask, redirect, url_for

def create_app():
    app = Flask(__name__)
    app.secret_key = "fbs-thesis-secret-key"

    # from app.views.auth_views import auth_bp
    # app.register_blueprint(auth_bp)

    from app.views.nurse_views import nurse_bp
    app.register_blueprint(nurse_bp)

    # Add this right before returning the app!
    @app.route('/')
    def default_home():
        return redirect(url_for('nurse.nurse_dashboard'))

    return app