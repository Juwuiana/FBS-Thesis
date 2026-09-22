from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from app.controllers import auth_controller
from app.db import get_db
from app.models import audit_model

auth_bp = Blueprint("auth", __name__)


def _home_for_role(role):
    """Where a signed-in user lands: each role has exactly one home page."""
    return url_for("admin.dashboard" if role == "medical_officer" else "nurse.nurse_dashboard")


def login_required(view):
    """Protect a route behind an active session. Use on any page that
    other feature branches (dashboard, patients, etc.) add later."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(*roles):
    """Like login_required, but the session's role must be one of `roles`
    (users.role: 'health_worker' or 'medical_officer'). /api/ paths get JSON
    401/403 instead of a redirect."""

    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            wants_json = request.path.startswith("/api/")
            if "user_id" not in session:
                if wants_json:
                    return jsonify(error="authentication required"), 401
                flash("Please sign in to continue.", "error")
                return redirect(url_for("auth.login"))
            if session.get("user_role") not in roles:
                if wants_json:
                    return jsonify(error="forbidden"), 403
                abort(403)
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def require_role_for_blueprint(bp, *roles):
    """Apply role_required(*roles) to every route on `bp`, via before_request,
    instead of decorating each view function one by one. Use this for a
    blueprint that is entirely one audience (e.g. all of `admin_bp` is
    medical_officer-only, all of `nurse_bp` is staff-only) -- an individual
    view can still add its own tighter @role_required on top if it ever
    needs to.
    """
    guard = role_required(*roles)(lambda: None)
    bp.before_request(guard)


@auth_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user, error = auth_controller.authenticate(email, password)
        if error:
            audit_model.log_event(
                get_db(), user_id=None, user_name=email or "unknown", role="Unknown",
                action=f"Failed login attempt ({email or 'unknown email'})",
                ip_address=request.remote_addr, severity="Critical",
            )
            flash(error, "error")
            return render_template("auth/login.html"), 401

        # Clear first so nothing from a previous session/user lingers.
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["user_name"] = f"{user['first_name']} {user['last_name']}"
        session["user_role"] = user["role"]
        audit_model.log_event(
            get_db(), user_id=session["user_id"], user_name=session["user_name"],
            role=session["user_role"], action="User login",
            ip_address=request.remote_addr, severity="Success",
        )

        flash(f"Welcome back, {user['first_name']}!", "success")
        return redirect(_home_for_role(user["role"]))

    if "user_id" in session:
        return redirect(_home_for_role(session.get("user_role")))
    return render_template("auth/login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        user_id, errors = auth_controller.register_user(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("auth/signup.html"), 400

        flash(
            "Account created. An LHU administrator needs to approve it before you can sign in.",
            "success",
        )
        return redirect(url_for("auth.login"))

    if "user_id" in session:
        return redirect(url_for("admin.dashboard"))
    return render_template("auth/signup.html")


@auth_bp.route("/logout")
def logout():
    if session.get("user_id"):
        audit_model.log_event(
            get_db(), user_id=session.get("user_id"),
            user_name=session.get("user_name", "unknown"),
            role=session.get("user_role", "Unknown"), action="User logout",
            ip_address=request.remote_addr, severity="Info",
        )
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))

