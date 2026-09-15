from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.controllers import auth_controller

auth_bp = Blueprint("auth", __name__)


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


@auth_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("auth.home"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user, error = auth_controller.authenticate(email, password)
        if error:
            flash(error, "error")
            return render_template("auth/login.html"), 401

        # Clear first so nothing from a previous session/user lingers.
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["user_name"] = f"{user['first_name']} {user['last_name']}"
        session["user_role"] = user["role"]

        flash(f"Welcome back, {user['first_name']}!", "success")
        return redirect(url_for("auth.home"))

    if "user_id" in session:
        return redirect(url_for("auth.home"))
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
        return redirect(url_for("auth.home"))
    return render_template("auth/signup.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/home")
@login_required
def home():
    """Minimal placeholder landing page proving auth works end-to-end.
    Other feature branches can point their own routes here or replace it."""
    return render_template(
        "auth/home.html",
        name=session.get("user_name"),
        role=session.get("user_role"),
    )
