from flask import Blueprint, render_template, redirect, url_for

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # TODO: wire up real login logic
    return render_template("auth/login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    # TODO: wire up real signup logic
    return render_template("auth/signup.html")


@auth_bp.route("/logout")
def logout():
    # TODO: call logout_user() after LoginManager is wired
    return redirect(url_for("auth.login"))