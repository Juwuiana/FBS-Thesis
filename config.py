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

    # CSRF tokens live as long as the session; idle timeout is enforced separately.
    WTF_CSRF_TIME_LIMIT = None

    # ------------------------------------------------------------------
    # Green computing (Android/Termux edge server). See README "Green metrics".
    # ------------------------------------------------------------------
    TIMEZONE = os.environ.get("FBS_TIMEZONE", "Asia/Manila")

    BATTERY_SYSFS_DIR = os.environ.get("FBS_BATTERY_DIR", "/sys/class/power_supply/battery")
    CURRENT_NOW_UNIT = os.environ.get("FBS_CURRENT_UNIT", "auto")     # auto | uA | mA
    # "grid" or "solar_ups": what the charger is fed from (sysfs can't tell them apart).
    POWER_FEED = os.environ.get("FBS_POWER_FEED", "grid").lower()

    # PLACEHOLDER: replace with the grid emission factor you cite in the thesis.
    EMISSION_FACTOR_KG_PER_KWH = float(os.environ.get("FBS_EMISSION_FACTOR", "0.6"))
    # Whole-phone power at idle (measure once, then set). Subtracted from per-inference power.
    IDLE_POWER_W = float(os.environ.get("FBS_IDLE_POWER_W", "0"))
    # Only used when the battery nodes are unreadable (e.g. running on a laptop).
    ESTIMATED_TDP_W = float(os.environ.get("FBS_ESTIMATED_TDP_W", "5"))

    TELEMETRY_INTERVAL_S = int(os.environ.get("FBS_TELEMETRY_INTERVAL_S", "60"))

    # Green-score targets. Tighten once you have real measurements: the plan's original
    # 0.001 kWh/inference (~3.6 kJ) is far above what a phone uses, so it would always score 100.
    TARGET_LATENCY_MS = float(os.environ.get("FBS_TARGET_LATENCY_MS", "50"))
    TARGET_KWH_PER_SCREEN = float(os.environ.get("FBS_TARGET_KWH_PER_SCREEN", "0.000001"))
    TARGET_IDLE_W = float(os.environ.get("FBS_TARGET_IDLE_W", "1.0"))

    # Trained model file (joblib). Until it exists a flagged stub runs and /health reports it.
    MODEL_PATH = os.environ.get("FBS_MODEL_PATH")

    # Presentation mode: shows demo controls on the Green Computing page (simulate LAN drop,
    # run screenings, load/clear demo history). Leave off in real use.
    DEMO_MODE = os.environ.get("FBS_DEMO_MODE", "0") == "1"

    # ------------------------------------------------------------------
    # Connectivity monitor / offline queue (flask connectivity-monitor)
    # ------------------------------------------------------------------
    # What "online" means: host:port list, any one answering = link up. Default = public DNS
    # (internet). Use your router (e.g. 192.168.1.1:80) to watch the clinic Wi-Fi link instead,
    # or an upstream server. NOTE: a site with no internet at all will read "offline" permanently
    # with the default; choose a target that matches what you want to monitor.
    PROBE_TARGETS = os.environ.get("FBS_PROBE_TARGETS", "1.1.1.1:53,8.8.8.8:53")
    PROBE_INTERVAL_S = float(os.environ.get("FBS_PROBE_INTERVAL_S", "15"))
    PROBE_TIMEOUT_S = float(os.environ.get("FBS_PROBE_TIMEOUT_S", "2"))
    PROBE_FAIL_THRESHOLD = int(os.environ.get("FBS_PROBE_FAIL_THRESHOLD", "3"))   # -> DOWN
    PROBE_OK_THRESHOLD = int(os.environ.get("FBS_PROBE_OK_THRESHOLD", "2"))       # -> UP
    # Where queued records go after a reconnect. "none" (default): no upstream exists yet, so
    # records stay QUEUED. "demo" is used by the presentation controls only.
    SYNC_TRANSPORT = os.environ.get("FBS_SYNC_TRANSPORT", "none")

    # Dev-only opt-in that unblocks the patient portal before real patient auth exists.
    # NEVER set FBS_DEV_NO_AUTH outside your own local machine: it disables the check that
    # keeps every /patient_* route 404ing (see app/controllers/patient_controller.py).
    DEV_NO_AUTH = os.environ.get("FBS_DEV_NO_AUTH", "0") == "1"
