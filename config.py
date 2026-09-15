import os
from datetime import timedelta


class Config:
    """
    Central app configuration.

    Values are read from environment variables so secrets never live in
    source control. Copy `.env.example` to `.env` and fill it in locally.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-in-.env")

    # If DATABASE_PATH isn't set, app/__init__.py falls back to
    # <instance folder>/fbs_thesis.sqlite3 (created automatically).
    DATABASE = os.environ.get("DATABASE_PATH")

    # Signup accounts start as "pending" and can't log in until an admin
    # approves them.
    REQUIRE_ADMIN_APPROVAL = os.environ.get("REQUIRE_ADMIN_APPROVAL", "True").lower() == "true"

    # Session / cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
