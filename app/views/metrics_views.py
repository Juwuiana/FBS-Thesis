"""JSON API behind the Green Computing page (the page itself is admin.green_computing)."""
from time import perf_counter

from flask import Blueprint, current_app, g, jsonify, request

from app.controllers import demo_controller, metrics_controller as mc
from app.db import get_db
from app.views.auth_views import login_required, role_required

metrics_bp = Blueprint("metrics", __name__, url_prefix="/api/v1")

admin_only = role_required("medical_officer")


@metrics_bp.before_request
def _start_timer():
    g.req_t0 = perf_counter()


def _page_args():
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 200))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        limit, offset = 50, 0
    return limit, offset


@metrics_bp.get("/green/score")
@admin_only
def score():
    return jsonify(mc.green_score(get_db()))


@metrics_bp.get("/green/stats/today")
@admin_only
def stats_today():
    return jsonify(mc.stats_today(get_db()))


@metrics_bp.get("/green/charts/realtime")
@admin_only
def realtime():
    data = mc.realtime_chart(get_db(), request.args.get("range", "24h"))
    if data is None:
        return jsonify(error="range must be one of " + ", ".join(mc.RANGES)), 400
    return jsonify(data)


@metrics_bp.get("/green/charts/component-breakdown")
@admin_only
def component_breakdown():
    return jsonify(mc.component_breakdown(get_db()))


@metrics_bp.get("/green/logs/events")
@admin_only
def events():
    limit, offset = _page_args()
    return jsonify(events=mc.events_log(get_db(), limit, offset))


@metrics_bp.get("/green/sync/pending")
@admin_only
def sync_pending():
    limit, offset = _page_args()
    return jsonify(records=mc.pending_records(get_db(), limit, offset))


@metrics_bp.get("/green/sync/summary")
@admin_only
def sync_summary():
    return jsonify(mc.sync_block(get_db()))


@metrics_bp.post("/predict")
@login_required
def predict():
    """Run the model inside the energy-measurement wrapper.

    Body: {"features": {...}, "lab_screening_id": optional int}. Returns the model output plus
    green_log_id; the nurse flow can link that log row to the lab_screenings row it saves.
    """
    payload = request.get_json(silent=True) or {}
    features = payload.get("features")
    if not isinstance(features, dict) or not features:
        return jsonify(error="'features' must be a non-empty object"), 400
    ext = current_app.extensions
    return jsonify(mc.run_measured_prediction(
        get_db(), ext["predictor"], ext["battery"], features, payload.get("lab_screening_id")))


# ---- demo / presentation (FBS_DEMO_MODE=1 only) -------------------------------------------

@metrics_bp.post("/green/sync/retry")
@admin_only
def sync_retry():
    if not current_app.config["DEMO_MODE"]:
        return jsonify(error="no upstream sync configured"), 501
    return jsonify(demo_controller.retry_sync(get_db()))


@metrics_bp.post("/green/demo/<action>")
@admin_only
def demo(action):
    if not current_app.config["DEMO_MODE"]:
        return jsonify(error="demo mode is off"), 404
    ext, db = current_app.extensions, get_db()
    if action == "screening":
        n = max(1, min(int((request.get_json(silent=True) or {}).get("count", 1)), 25))
        return jsonify(demo_controller.run_screenings(db, ext["predictor"], ext["battery"], n))
    if action == "disconnect":
        return jsonify(demo_controller.disconnect(db))
    if action == "reconnect":
        return jsonify(demo_controller.reconnect(db))
    if action == "seed":
        return jsonify(demo_controller.seed_history(current_app._get_current_object()))
    if action == "clear":
        return jsonify(demo_controller.clear_demo(current_app._get_current_object()))
    return jsonify(error="unknown action"), 404
