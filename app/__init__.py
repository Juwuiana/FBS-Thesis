import os

from flask import Flask

from config import Config


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Make sure the instance folder (holds the sqlite file, gitignored)
    # exists, and default the DB path there if one wasn't set via env var.
    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("DATABASE"):
        app.config["DATABASE"] = os.path.join(app.instance_path, "fbs_thesis.sqlite3")

    from app import db
    db.init_app(app)

    from app.views.auth_views import auth_bp
    app.register_blueprint(auth_bp)

    _register_cli(app)

    # Idempotent: schema.sql uses CREATE TABLE IF NOT EXISTS, so this is
    # safe to run on every startup.
    with app.app_context():
        db.init_db()

    return app


def _register_cli(app):
    import click

    @app.cli.command("init-db")
    def init_db_command():
        """flask init-db — (re)create tables from schema.sql."""
        from app import db as db_module

        db_module.init_db()
        click.echo("Initialized the database.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--first-name", default="Admin")
    @click.option("--last-name", default="User")
    def create_admin_command(email, password, first_name, last_name):
        """flask create-admin — seed one pre-approved account so you have
        a way to log in and start approving other sign-ups."""
        from werkzeug.security import generate_password_hash

        from app.models import user as user_model

        if user_model.email_exists(email):
            click.echo(f"A user with email {email} already exists.")
            return

        data = {
            "first_name": first_name,
            "middle_name": None,
            "last_name": last_name,
            "birthday": "1990-01-01",
            "sex": "male",
            "email": email,
            "phone": "9000000000",
            "role": "medical_officer",
            "facility": "rhui",
            "barangay": "aplaya",
        }
        password_hash = generate_password_hash(password)
        user_model.create_user(data, password_hash, status="approved")
        click.echo(f"Admin account created for {email} (status=approved).")

    @app.cli.command("approve-user")
    @click.option("--email", prompt=True)
    def approve_user_command(email):
        """flask approve-user — flip a pending account to approved."""
        from app.models import user as user_model

        user = user_model.get_user_by_email(email)
        if not user:
            click.echo(f"No user found with email {email}.")
            return
        user_model.set_status(user["id"], "approved")
        click.echo(f"{email} is now approved.")
