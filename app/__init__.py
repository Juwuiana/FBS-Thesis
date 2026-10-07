import os
import secrets

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

    # CSRF protection for every unsafe-method request on every blueprint (no per-route opt-in).
    from flask_wtf.csrf import CSRFError, CSRFProtect
    CSRFProtect(app)

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(_error):
        from flask import jsonify, render_template, request

        if request.path.startswith("/api/"):
            return jsonify({"error": "csrf"}), 400
        return render_template("errors/csrf.html"), 400

    from app.views.auth_views import auth_bp
    from app.views.admin_views import admin_bp
    from app.views.metrics_views import metrics_bp
    from app.controllers.nurse_controller import nurse_bp
    from app.controllers.patient_controller import patient_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(nurse_bp)
    app.register_blueprint(patient_bp)

    # Green computing: the model and battery reader are created once at startup, never per request.
    from app.ml.green_metrics import BatteryReader
    from app.ml.predictor import Predictor

    app.extensions["predictor"] = Predictor(
        app.config.get("MODEL_PATH")
        or os.path.join(app.root_path, "ml", "artifacts", "model.joblib"))
    app.extensions["battery"] = BatteryReader(
        app.config["BATTERY_SYSFS_DIR"], app.config["CURRENT_NOW_UNIT"])

    @app.get("/health")
    def health():
        import sqlite3

        from flask import jsonify

        from app.db import get_db
        from app.services import connectivity, sync_queue
        try:
            db = get_db()
            monitor = connectivity.monitor_status(db)["status"]
            link = sync_queue.link_state(db)
        except sqlite3.Error:
            monitor = link = "unknown"
        return jsonify(status="ok",
                       model_loaded=not app.extensions["predictor"].is_stub,
                       battery_readable=app.extensions["battery"].available(),
                       connectivity_monitor=monitor, link_state=link)

    @app.template_filter("number_format")
    def number_format(value):
        try:
            return f"{value:,}"
        except (ValueError, TypeError):
            return value

    def safe_url_for(endpoint, fallback="#", **values):
        # From the nurse/patient branch: lets a shared base template link to a
        # blueprint that might not be registered in every build.
        from flask import url_for
        from werkzeug.routing.exceptions import BuildError
        try:
            return url_for(endpoint, **values)
        except BuildError:
            return fallback

    app.jinja_env.globals["safe_url_for"] = safe_url_for

    @app.context_processor
    def inject_session_settings():
        from app.models import settings as settings_model
        from flask import session
        from app.models import user as user_model

        signed_in_user = user_model.get_user_by_id(session["user_id"]) if session.get("user_id") else None
        return {
            "session_timeout_minutes": settings_model.get_session_timeout_minutes(),
            "signed_in_user_name": session.get("user_name"),
            "current_user_avatar": signed_in_user["avatar_filename"] if signed_in_user else None,
        }

    @app.before_request
    def _enforce_session_timeout():
        """Log the user out if they've been inactive longer than the
        timeout configured on the Privacy & Security admin page."""
        from datetime import datetime, timezone

        from flask import flash, jsonify, redirect, request, session, url_for

        if request.endpoint == "static" or "user_id" not in session:
            return

        from app.models import settings as settings_model
        from app.models import user as user_model

        role = session.get("user_role")
        if role and session.get("security_version") != settings_model.get_security_version(role):
            user_model.release_session(session["user_id"], session.get("session_token"))
            session.clear()
            flash(
                "You've been signed out for security reasons. Please log in again.",
                "error",
            )
            return redirect(url_for("auth.login"))

        signed_in_user = user_model.get_user_by_id(session["user_id"])
        if signed_in_user is None or signed_in_user["is_suspended"]:
            session.clear()
            flash(
                "Your account has been suspended. Contact your LHU administrator.",
                "error",
            )
            return redirect(url_for("auth.login"))

        timeout_minutes = settings_model.get_session_timeout_minutes()
        now = datetime.now(timezone.utc)
        last_active_raw = session.get("last_active")

        if last_active_raw:
            last_active = datetime.fromisoformat(last_active_raw)
            elapsed_seconds = (now - last_active).total_seconds()
            if elapsed_seconds > timeout_minutes * 60:
                user_model.release_session(session["user_id"], session.get("session_token"))
                session.clear()
                flash(
                    "You were signed out after "
                    f"{timeout_minutes} minute(s) of inactivity.",
                    "error",
                )
                return redirect(url_for("auth.login"))

        # Single active session: the cookie's token must match the one stored for the account.
        db_token = signed_in_user["active_session_token"]
        cookie_token = session.get("session_token")
        if not db_token or not cookie_token or not secrets.compare_digest(db_token, cookie_token):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify(error="authentication required"), 401
            flash(
                "You were signed out because this account was signed in on another device.",
                "error",
            )
            return redirect(url_for("auth.login"))

        session["last_active"] = now.isoformat()

        # Throttle the DB write so ordinary requests don't each hit SQLite.
        last_touch_raw = session.get("session_touched_at")
        if not last_touch_raw or (now - datetime.fromisoformat(last_touch_raw)).total_seconds() > 30:
            user_model.touch_session(session["user_id"])
            session["session_touched_at"] = now.isoformat()

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
            from app.models import patient_model
            patient_model.run_retention_purge(force=True)

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

    @app.cli.command("purge-expired")
    def purge_expired_command():
        """flask purge-expired -- immediately purge expired Recycle Bin records."""
        from app.models import patient_model

        purged = patient_model.run_retention_purge(force=True)
        click.echo(f"Purged {purged} expired patient record(s).")

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

    @app.cli.command("telemetry-loop")
    @click.option("--interval", default=None, type=int, help="Seconds between samples.")
    @click.option("--idle/--active", default=False,
                  help="Tag samples as idle-baseline (run with the phone otherwise unused).")
    def telemetry_loop_command(interval, idle):
        """flask telemetry-loop — sample battery power/temperature into system_telemetry_log.

        Run under supervisord/termux-services next to the web server. Use --idle for a few
        minutes with no traffic to measure the idle baseline for IDLE_POWER_W."""
        from flask import current_app

        from app import db as db_module
        from app.ml import telemetry

        cfg = current_app.config
        if not current_app.extensions["battery"].available():
            raise SystemExit("Battery nodes not readable at " + cfg["BATTERY_SYSFS_DIR"])
        telemetry.run_loop(db_module.get_connection, current_app.extensions["battery"],
                           cfg["POWER_FEED"], interval or cfg["TELEMETRY_INTERVAL_S"], lambda: idle)

    @app.cli.command("connectivity-monitor")
    @click.option("--interval", type=float, default=None, help="Seconds between probes.")
    def connectivity_monitor_command(interval):
        """flask connectivity-monitor — watch the network link and record DISCONNECT/RECONNECT
        events, queue-aware. Run it beside the web server (see scripts/termux_start.sh)."""
        import logging
        import signal
        import threading
        from dataclasses import replace

        from flask import current_app

        from app import db as db_module
        from app.services import connectivity, sync_queue

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        cfg = connectivity.MonitorConfig.from_app_config(current_app.config)
        if interval:
            cfg = replace(cfg, interval_s=interval)
        transport = sync_queue.get_transport(current_app.config["SYNC_TRANSPORT"])
        monitor = connectivity.ConnectivityMonitor(
            db_module.get_connection, cfg,
            lambda: connectivity.probe(cfg.targets, cfg.timeout_s), transport)
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        click.echo(f"Probing {list(cfg.targets)} every {cfg.interval_s:g}s "
                   f"(down after {cfg.fail_threshold} failures, up after {cfg.ok_threshold} successes)")
        monitor.run(stop)

    @app.cli.command("connectivity-status")
    def connectivity_status_command():
        """flask connectivity-status — one probe plus what the database currently believes."""
        from flask import current_app

        from app import db as db_module
        from app.services import connectivity, sync_queue

        cfg = connectivity.MonitorConfig.from_app_config(current_app.config)
        conn = db_module.get_connection()
        try:
            reachable = connectivity.probe(cfg.targets, cfg.timeout_s)
            click.echo(f"Probe now         : {'reachable' if reachable else 'UNREACHABLE'} {list(cfg.targets)}")
            click.echo(f"Recorded link     : {sync_queue.link_state(conn)}")
            st = connectivity.monitor_status(conn)
            click.echo(f"Monitor           : {st['status']} (last probe {st['last_probe_at']})")
            click.echo(f"Detection delay   : ~{cfg.detection_delay_s:g}s to declare DOWN")
        finally:
            conn.close()

    from app.constants import BARANGAYS

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--first-name", default="Admin", show_default=True)
    @click.option("--last-name", default="User", show_default=True)
    @click.option("--birthday", prompt=True, help="Admin birthday (YYYY-MM-DD).")
    @click.option("--sex", prompt=True, type=click.Choice(["male", "female"], case_sensitive=False))
    @click.option("--phone", prompt=True, help="10-digit mobile number starting with 9, or +63/0 form.")
    @click.option("--barangay", prompt=True, type=click.Choice([value for value, _ in BARANGAYS]))
    def create_admin_command(email, password, first_name, last_name, birthday, sex, phone, barangay):
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
            "birthday": birthday,
            "sex": sex.lower(),
            "email": email,
            "phone": phone,
            "role": "medical_officer",
            "facility": "lhui",
            "barangay": barangay,
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
