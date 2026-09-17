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
    from app.views.admin_views import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    @app.template_filter("number_format")
    def number_format(value):
        try:
            return f"{value:,}"
        except (ValueError, TypeError):
            return value

    @app.context_processor
    def inject_session_settings():
        from app.models import settings as settings_model
        return {"session_timeout_minutes": settings_model.get_session_timeout_minutes()}

    @app.before_request
    def _enforce_session_timeout():
        """Log the user out if they've been inactive longer than the
        timeout configured on the Privacy & Security admin page."""
        from datetime import datetime, timezone

        from flask import flash, redirect, request, session, url_for

        if request.endpoint == "static" or "user_id" not in session:
            return

        from app.models import settings as settings_model

        timeout_minutes = settings_model.get_session_timeout_minutes()
        now = datetime.now(timezone.utc)
        last_active_raw = session.get("last_active")

        if last_active_raw:
            last_active = datetime.fromisoformat(last_active_raw)
            elapsed_seconds = (now - last_active).total_seconds()
            if elapsed_seconds > timeout_minutes * 60:
                session.clear()
                flash(
                    "You were signed out after "
                    f"{timeout_minutes} minute(s) of inactivity.",
                    "error",
                )
                return redirect(url_for("auth.login"))

        session["last_active"] = now.isoformat()

    _register_cli(app)

    # init_db() now runs pending migrations from app/models/migrations/ in
    # filename order and records each one in schema_migrations, so this is a
    # no-op once the schema is current -- safe on every startup.
    with app.app_context():
        if _auto_migrate_enabled():
            applied = db.init_db()
            if applied:
                app.logger.info("Applied migrations: %s", ", ".join(applied))
            # Seeding reads the `users` table, so it only makes sense once
            # the schema is known to be current.
            from app.models import user as user_model
            user_model.seed_demo_users()

    return app



def _auto_migrate_enabled():
    """Whether create_app() should apply pending migrations on startup.

    Normally yes. Set SKIP_AUTO_MIGRATE=1 to build the app without touching
    the schema -- needed for `flask db-baseline`, and for recovering a
    database where a migration failed partway and startup would just retry
    the broken file.
    """
    return os.environ.get("SKIP_AUTO_MIGRATE", "").strip().lower() not in ("1", "true", "yes")

def _register_cli(app):
    import click

    @app.cli.command("init-db")
    def init_db_command():
        """flask init-db — apply any pending migrations, in order."""
        from app import db as db_module

        applied = db_module.init_db()
        if applied:
            for name in applied:
                click.echo(f"applied {name}")
        else:
            click.echo("Database already up to date.")

    @app.cli.command("db-status")
    def db_status_command():
        """flask db-status — show which migrations have run and which haven't."""
        from app import db as db_module

        conn = db_module.get_connection()
        try:
            applied = db_module.applied_migrations(conn)
            click.echo(f"database: {db_module.database_path()}")
            for path in db_module.migration_files():
                mark = "x" if path.name in applied else " "
                click.echo(f"  [{mark}] {path.name}")
        finally:
            conn.close()

    @app.cli.command("db-check")
    def db_check_command():
        """flask db-check — verify every foreign key in the database resolves."""
        from app import db as db_module

        violations = db_module.foreign_key_violations()
        if not violations:
            click.echo("No foreign key violations.")
            return
        for v in violations:
            click.echo(
                f"  {v['table']} rowid={v['rowid']} -> {v['references']} (fk #{v['fk_index']})"
            )
        raise SystemExit(1)

    @app.cli.command("db-baseline")
    @click.argument("filenames", nargs=-1)
    @click.option("--all", "all_", is_flag=True, help="Baseline every pending migration.")
    def db_baseline_command(filenames, all_):
        """flask db-baseline — mark migrations as applied WITHOUT running them.

        For a database that already has the tables (e.g. one built by the old
        schema.sql) so the runner doesn't try to create them again.
        """
        from app import db as db_module

        conn = db_module.get_connection()
        try:
            if all_:
                names = [p.name for p in db_module.pending_migrations(conn)]
            else:
                names = list(filenames)
            if not names:
                click.echo("Nothing to baseline.")
                return
            db_module.mark_applied(names, conn=conn)
            for name in names:
                click.echo(f"marked applied (not run): {name}")
        finally:
            conn.close()

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
