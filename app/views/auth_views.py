import os
import secrets
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from app.controllers import auth_controller
from app.constants import STATION_MAP
from app.db import get_db
from app.models import audit_model, user as user_model

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


@auth_bp.route("/auth-data/<path:filename>")
def auth_static_data(filename):
    """
    Serves FBS-Thesis/data/ files (psgc_data.json) to pages that render
    before login -- signup.html needs the region/city/barangay cascade,
    but nurse.nurse_static_data is gated behind the nurse blueprint's
    role guard, so a not-yet-authenticated visitor can't reach it.
    """
    project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    data_dir = os.path.join(project_root, "data")
    return send_from_directory(data_dir, filename)


@auth_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(_home_for_role(session.get("user_role")))
    return render_template("landing/landing.html")

@auth_bp.route("/about")
def about():
    return render_template("landing/about.html")

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user, error = auth_controller.authenticate(email, password)
        if error:
            if error == auth_controller.ACTIVE_SESSION_MESSAGE:
                audit_action = f"Login blocked, account already signed in elsewhere ({email})"
                audit_severity = "Warning"
            else:
                audit_action = f"Failed login attempt ({email or 'unknown email'})"
                audit_severity = "Critical"
            audit_model.log_event(
                get_db(), user_id=None, user_name=email or "unknown", role="Unknown",
                action=audit_action,
                ip_address=request.remote_addr, severity=audit_severity,
            )
            flash(error, "error")
            return render_template("auth/login.html"), 401

        # Clear first so nothing from a previous session/user lingers.
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["session_token"] = user_model.start_session(user["id"])
        session["user_name"] = f"{user['first_name']} {user['last_name']}"
        session["user_role"] = user["role"]
        from app.models import settings as settings_model
        session["security_version"] = settings_model.get_security_version(user["role"])
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


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    confirmation = None
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not email or not auth_controller.EMAIL_RE.match(email):
            error = "A valid email address is required."
        else:
            user = user_model.get_user_by_email(email)
            if user and user["status"] == "approved":
                user_model.set_status(user["id"], "recovery")
                audit_model.log_event(
                    get_db(), user_id=user["id"], user_name=email,
                    role=user["role"], action="Password recovery requested",
                    ip_address=request.remote_addr, severity="Warning",
                )
            confirmation = "If that email is registered, an administrator has been notified."
    return render_template(
        "auth/forgot_password.html", confirmation=confirmation, error=error
    )


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    stations = list(STATION_MAP.items())
    if request.method == "POST":
        user_id, errors = auth_controller.register_user(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("auth/signup.html", stations=stations), 400

        flash(
            "Account created. An LHU administrator needs to approve it before you can sign in.",
            "success",
        )
        return redirect(url_for("auth.login"))

    if "user_id" in session:
        return redirect(url_for("admin.dashboard"))
    return render_template("auth/signup.html", stations=stations)


@auth_bp.route("/logout")
def logout():
    if session.get("user_id"):
        audit_model.log_event(
            get_db(), user_id=session.get("user_id"),
            user_name=session.get("user_name", "unknown"),
            role=session.get("user_role", "Unknown"), action="User logout",
            ip_address=request.remote_addr, severity="Info",
        )
        # Only release the account if this browser still owns the active session.
        user_model.release_session(session["user_id"], session.get("session_token"))
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile/avatar", methods=["POST"])
@login_required
def upload_avatar():
    fallback = _home_for_role(session.get("user_role"))
    referrer = request.referrer
    if referrer:
        parsed = urlparse(referrer)
        if not parsed.netloc or parsed.netloc == request.host:
            fallback = referrer

    uploaded = request.files.get("avatar")
    allowed_extensions = {"png", "jpg", "jpeg", "webp"}
    extension = Path(uploaded.filename or "").suffix.lower().lstrip(".") if uploaded else ""
    if not uploaded or not uploaded.filename or extension not in allowed_extensions:
        flash("Please choose a PNG, JPG, JPEG, or WebP image.", "error")
        return redirect(fallback)
    if not (uploaded.content_type or "").lower().startswith("image/"):
        flash("The uploaded file must be an image.", "error")
        return redirect(fallback)

    uploaded.stream.seek(0, os.SEEK_END)
    size = uploaded.stream.tell()
    uploaded.stream.seek(0)
    if size > 2 * 1024 * 1024:
        flash("Profile photos must be 2 MB or smaller.", "error")
        return redirect(fallback)

    user_id = session["user_id"]
    avatar_dir = Path(current_app.static_folder) / "uploads" / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    filename = f"user_{user_id}.{extension}"
    for old_extension in allowed_extensions:
        old_path = avatar_dir / f"user_{user_id}.{old_extension}"
        if old_path.name != filename:
            old_path.unlink(missing_ok=True)
    uploaded.save(avatar_dir / filename)
    user_model.update_avatar(user_id, filename)
    flash("Profile photo updated successfully.", "success")
    return redirect(fallback)