"""Business logic for the Green Computing page and its JSON API.

Definitions used on the dashboard (also documented in README):
  Energy Efficiency  inference latency vs TARGET_LATENCY_MS
  Carbon per Screen  attributed energy per screening (model + web + DB) vs TARGET_KWH_PER_SCREEN
  Idle Power Usage   TARGET_IDLE_W vs measured idle draw (needs telemetry idle samples)
  Renewable Usage    share of telemetry samples taken while on SOLAR_UPS
  Green Score        mean of the available sub-scores; Renewable Usage counts only when
                     FBS_POWER_FEED=solar_ups (a grid-fed phone would otherwise be punished for
                     something it cannot change).
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from time import perf_counter
from zoneinfo import ZoneInfo

from flask import current_app, g

from app.ml.green_metrics import measure
from app.models import green
from app.services.connectivity import monitor_status

RANGES = {          # key: (span, bucket kind)
    "24h": (timedelta(hours=24), "hour"),
    "7d": (timedelta(days=7), "day"),
    "30d": (timedelta(days=30), "day"),
    "90d": (timedelta(days=90), "day"),
}
COMPONENT_COLORS = {"ML Inference": "#4caf50", "Web Server (LAN)": "#1565c0",
                    "Database I/O": "#ff9800", "Idle & Other": "#9c27b0"}


# ---- time helpers -------------------------------------------------------------------

def sql_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now():
    return datetime.now(timezone.utc)


def _tz():
    return ZoneInfo(current_app.config["TIMEZONE"])


def _local_now():
    return _now().astimezone(_tz())


def _offset_s(local_dt=None):
    return int((local_dt or _local_now()).utcoffset().total_seconds())


def _local_midnight():
    return _local_now().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _cap_s():
    return current_app.config["TELEMETRY_INTERVAL_S"] * 3


def human_duration(seconds) -> str:
    s = int(round(seconds or 0))
    if s < 60:
        return f"{s} sec"
    m = s // 60
    return f"{m} min" if m < 60 else f"{m // 60}h {m % 60:02d}m"


def time_ago(ts) -> str:
    if not ts:
        return "never"
    s = (_now() - _parse(ts)).total_seconds()
    if s < 60:
        return "just now"
    return f"{human_duration(s)} ago"


def _change(now_v, before_v, ref, lower_is_better=True):
    """('8% lower than yesterday so far', css class) for the stat cards."""
    if not before_v:
        return "no earlier data to compare", "neutral"
    pct = (now_v - before_v) / before_v * 100
    if abs(pct) < 0.5:
        return f"no change vs {ref}", "neutral"
    good = (pct < 0) == lower_is_better
    return f"{abs(pct):.0f}% {'lower' if pct < 0 else 'higher'} than {ref}", "down" if good else "up-bad"


# ---- energy sources ---------------------------------------------------------------------

def _energy_kwh(db, start, end):
    """(kWh, carbon kg, basis). Device telemetry when it exists, else model-inference energy."""
    factor = current_app.config["EMISSION_FACTOR_KG_PER_KWH"]
    if green.has_telemetry(db, start, end):
        kwh = green.device_energy_kwh(db, start, end, _cap_s())
        return kwh, kwh * factor, "device_telemetry"
    t = green.totals(db, start, end)
    return t["energy_kwh"], t["carbon_kg"], "inference_only"


# ---- score ----------------------------------------------------------------------------------

def _ratio(target, actual):
    return None if not actual or actual <= 0 else min(1.0, target / actual)


def score_for_window(db, start, end):
    cfg = current_app.config
    t = green.totals(db, start, end)
    tel = green.idle_and_source(db, start, end)
    per_screen = (t["ml_kwh"] + t["web_kwh"] + t["db_kwh"]) / t["n"] if t["n"] else None
    parts = {
        "Energy Efficiency": _ratio(cfg["TARGET_LATENCY_MS"], t["avg_latency_ms"]) if t["n"] else None,
        "Carbon per Screen": _ratio(cfg["TARGET_KWH_PER_SCREEN"], per_screen),
        "Idle Power Usage": _ratio(cfg["TARGET_IDLE_W"], tel["idle_w"]),
        "Renewable Usage": (tel["solar_n"] / tel["n"]) if tel["n"] else None,
    }
    counted = [v for k, v in parts.items()
               if v is not None and (k != "Renewable Usage" or cfg["POWER_FEED"] == "solar_ups")]
    score = round(100 * sum(counted) / len(counted), 1) if counted else None
    return {"score": score, "inferences": t["n"],
            "breakdown": [{"label": k, "pct": None if v is None else round(v * 100)} for k, v in parts.items()],
            "avg_latency_ms": round(t["avg_latency_ms"], 3), "per_screen_kwh": per_screen}


def _grade_label(score):
    if score is None:
        return "No data"
    return "Excellent" if score >= 90 else "Good" if score >= 75 else "Fair" if score >= 60 else "Needs work"


def green_score(db):
    now = _now()
    cur = score_for_window(db, sql_utc(now - timedelta(days=7)), sql_utc(now + timedelta(seconds=1)))
    prev = score_for_window(db, sql_utc(now - timedelta(days=14)), sql_utc(now - timedelta(days=7)))
    change = None if cur["score"] is None or prev["score"] is None else round(cur["score"] - prev["score"], 1)
    return {**cur, "label": _grade_label(cur["score"]), "change_pts": change, "window": "7d",
            "targets": {"latency_ms": current_app.config["TARGET_LATENCY_MS"],
                        "kwh_per_screen": current_app.config["TARGET_KWH_PER_SCREEN"],
                        "idle_w": current_app.config["TARGET_IDLE_W"]}}


# ---- today ------------------------------------------------------------------------------------

def stats_today(db):
    mid = _local_midnight()
    now = _now()
    start = sql_utc(mid)
    elapsed = now - mid.astimezone(timezone.utc)
    y_start, y_end = sql_utc(mid - timedelta(days=1)), sql_utc(mid - timedelta(days=1) + elapsed)
    kwh, kg, basis = _energy_kwh(db, start, sql_utc(now + timedelta(seconds=1)))
    y_kwh, _, _ = _energy_kwh(db, y_start, y_end)
    w_kwh, w_kg, _ = _energy_kwh(db, sql_utc(now - timedelta(days=7)), sql_utc(now + timedelta(seconds=1)))
    p_kwh, p_kg, _ = _energy_kwh(db, sql_utc(now - timedelta(days=14)), sql_utc(now - timedelta(days=7)))
    e_txt, e_cls = _change(kwh, y_kwh, "yesterday so far")
    c_txt, c_cls = _change(w_kg, p_kg, "the previous 7 days")
    t = green.totals(db, start)
    up = green.uptime_seconds(db, start, sql_utc(now + timedelta(seconds=1)), _cap_s()) \
        if green.has_telemetry(db, start) else None
    return {"energy_kwh": kwh, "carbon_kg": kg, "energy_basis": basis, "inferences": t["n"],
            "energy_change": e_txt, "energy_change_cls": e_cls,
            "carbon_week_kg": w_kg, "carbon_change": c_txt, "carbon_change_cls": c_cls,
            "uptime_s": up, "uptime_text": human_duration(up) if up is not None else "–",
            "includes_seeded_demo_data": t["seeded_n"] > 0}


# ---- charts -------------------------------------------------------------------------------------

def realtime_chart(db, rng):
    if rng not in RANGES:
        return None
    span, kind = RANGES[rng]
    fmt = "%Y-%m-%d %H:00" if kind == "hour" else "%Y-%m-%d"
    now = _now()
    start = sql_utc(now - span)
    off = _offset_s()
    factor = current_app.config["EMISSION_FACTOR_KG_PER_KWH"]
    if green.has_telemetry(db, start):
        basis, rows = "device_telemetry", {r["bucket"]: (r["energy_kwh"], r["energy_kwh"] * factor)
                                           for r in green.device_series(db, start, fmt, off, _cap_s())}
    else:
        basis, rows = "inference_only", {r["bucket"]: (r["energy_kwh"], r["carbon_kg"])
                                         for r in green.inference_series(db, start, fmt, off)}
    # continuous axis: fill empty buckets with 0
    local_end = _local_now().replace(minute=0, second=0, microsecond=0)
    if kind == "day":
        local_end = local_end.replace(hour=0)
    step = timedelta(hours=1) if kind == "hour" else timedelta(days=1)
    n = int(span / step)
    keys = [(local_end - step * i) for i in range(n - 1, -1, -1)]
    labels, energy, carbon = [], [], []
    for k in keys:
        key = k.strftime(fmt)
        e, c = rows.get(key, (0.0, 0.0))
        labels.append(k.strftime("%H:00") if kind == "hour" else
                      k.strftime("%a") if rng == "7d" else k.strftime("%b %d"))
        energy.append(e)
        carbon.append(c)
    return {"range": rng, "timezone": current_app.config["TIMEZONE"], "basis": basis,
            "labels": labels, "energy_values": energy, "carbon_values": carbon}


def component_breakdown(db, hours=24):
    now = _now()
    start, end = sql_utc(now - timedelta(hours=hours)), sql_utc(now + timedelta(seconds=1))
    t = green.totals(db, start, end)
    parts = {"ML Inference": t["ml_kwh"], "Web Server (LAN)": t["web_kwh"], "Database I/O": t["db_kwh"]}
    if green.has_telemetry(db, start, end):
        device = green.device_energy_kwh(db, start, end, _cap_s())
        parts["Idle & Other"] = max(device - sum(parts.values()), 0.0)
    total = sum(parts.values())
    return {"window_hours": hours, "total_kwh": total,
            "components": [{"label": k, "kwh": v, "pct": round(100 * v / total, 2) if total else 0,
                            "color": COMPONENT_COLORS[k]} for k, v in parts.items()],
            "method": "device power x time spent in each component; Idle & Other = telemetry "
                      "energy minus the attributed components"}


# ---- connectivity & sync --------------------------------------------------------------------------

def _gaps(db, since_utc, now_utc):
    """[(start, end_or_None, records, gap_id)] from DISCONNECT/RECONNECT pairs, oldest first."""
    open_, gaps = {}, []
    for e in green.events_since(db, since_utc):
        gid = e["gap_identifier"] or e["created_at"]
        if e["event_type"] == "DISCONNECT":
            open_[gid] = _parse(e["created_at"])
        elif e["event_type"] == "RECONNECT" and gid in open_:
            gaps.append([open_.pop(gid), _parse(e["created_at"]), e["record_count"], gid])
    gaps += [[s, None, None, gid] for gid, s in open_.items()]
    return sorted(gaps, key=lambda g_: g_[0])


def connectivity(db):
    now = _now()
    tz = _tz()
    win_start = now - timedelta(hours=12)
    gaps = _gaps(db, sql_utc(now - timedelta(hours=13)), now)
    segs, cursor = [], win_start
    for s, e, _, _ in gaps:
        e = e or now
        s, e = max(s, win_start), min(e, now)
        if e <= win_start or s >= now:
            continue
        if s > cursor:
            segs.append({"online": True, "weight": (s - cursor).total_seconds()})
        segs.append({"online": False, "weight": (e - s).total_seconds()})
        cursor = e
    if cursor < now:
        segs.append({"online": True, "weight": (now - cursor).total_seconds()})
    labels = [(win_start + timedelta(hours=2 * i)).astimezone(tz).strftime("%I%p").lstrip("0").lower()
              for i in range(7)]
    mid = _local_midnight().astimezone(timezone.utc)
    today = [g_ for g_ in _gaps(db, sql_utc(mid), now) if g_[0] >= mid]
    events, total = [], 0.0
    for s, e, rec, gid in today:
        dur = ((e or now) - s).total_seconds()
        total += dur
        if rec is None:   # gap still open (or reconnect without a count): count what is queued for it
            rec = green.gap_record_count(db, gid)
        events.append({"time_range": f"{s.astimezone(tz):%H:%M}–{(e.astimezone(tz).strftime('%H:%M') if e else 'ongoing')}",
                       "duration": human_duration(dur), "records": rec})
    last = green.last_connectivity_event(db)
    return {"is_offline": bool(last and last["event_type"] == "DISCONNECT"),
            "timeline": segs, "timeline_labels": labels, "offline_events": events[::-1],
            "gap_count": len(today), "total_offline": human_duration(total) if today else "0 sec"}


def sync_block(db):
    s = green.sync_summary(db)
    c = green.pending_counts(db)
    return {"queued": s["queued"], "synced": s["synced"], "failed": s["failed"],
            "last_sync": time_ago(s["last_synced_at"]),
            "queue": {"screenings": c["screenings"], "patients": c["patients"], "assessments": c["assessments"]}}


def _local_hm(ts):
    return _parse(ts).astimezone(_tz()).strftime("%H:%M")


def embedded_records(db, limit=7):
    return [{"id": r["patient_code"], "fbs": "–" if r["fbs_mg_dl"] is None else f"{r['fbs_mg_dl']:g}",
             "risk": r["risk"] or "Pending",
             "status": "Queued" if r["sync_status"] != "SYNCED" else "Synced",
             "time": _local_hm(r["offline_created_at"])} for r in green.recent_sync_rows(db, limit)]


def dashboard_context(db):
    """Everything metrics/green.html renders on first load (the template's `gc` dict)."""
    today = stats_today(db)
    score = green_score(db)
    conn = connectivity(db)
    sync = sync_block(db)
    tracker = realtime_chart(db, "7d")
    comps = component_breakdown(db)
    sc = score["score"]
    score_cls = "neutral" if score["change_pts"] is None else ("positive" if score["change_pts"] >= 0 else "up-bad")
    gc = {
        "energy_kwh": _fmt(today["energy_kwh"]), "energy_change": today["energy_change"],
        "energy_change_cls": today["energy_change_cls"], "energy_basis": today["energy_basis"],
        "carbon": _fmt(today["carbon_kg"]), "carbon_change": today["carbon_change"],
        "carbon_change_cls": today["carbon_change_cls"],
        "green_score": "–" if sc is None else round(sc), "score_label": score["label"],
        "score_change": "no earlier week to compare" if score["change_pts"] is None
        else f"{score['change_pts']:+.1f} pts vs last week",
        "score_change_cls": score_cls,
        "sync_queue": sync["queue"]["screenings"], "uptime": today["uptime_text"],
        "offline_gaps": conn["gap_count"], "is_offline": conn["is_offline"], "last_sync": sync["last_sync"],
        "queued_count": sync["queued"], "synced_count": sync["synced"],
        "total_offline": conn["total_offline"], "gap_count": conn["gap_count"], "queue": sync["queue"],
        "energy_labels": tracker["labels"], "energy_values": tracker["energy_values"],
        "carbon_values": tracker["carbon_values"],
        "score_breakdown": [{"label": b["label"], "pct": b["pct"] if b["pct"] is not None else 0,
                             "na": b["pct"] is None} for b in score["breakdown"]],
        "energy_breakdown": _active_breakdown(comps),
        "idle_note": _idle_note(comps),
        "demo_mode": current_app.config["DEMO_MODE"],
        "monitor": monitor_status(db),
        "conn_timeline": conn["timeline"], "conn_labels": conn["timeline_labels"],
        "offline_events": conn["offline_events"],
        "has_data": today["inferences"] > 0 or sc is not None,
        "seeded": today["includes_seeded_demo_data"],
    }
    return gc, embedded_records(db), recent_inferences(db)


def _active_breakdown(comps):
    """Donut shows the active components only; idle would otherwise be ~100% of the ring."""
    active = [c for c in comps["components"] if c["label"] != "Idle & Other"]
    tot = sum(c["kwh"] for c in active)
    return [{"label": c["label"], "pct": round(100 * c["kwh"] / tot, 1) if tot else 0,
             "kwh": _fmt(c["kwh"]), "color": c["color"]} for c in active]


def _idle_note(comps):
    idle = next((c for c in comps["components"] if c["label"] == "Idle & Other"), None)
    if idle is None:
        return None
    pct = ">99.9" if idle["pct"] >= 99.95 else f"{idle['pct']}"
    return f"Idle & other: {pct}% of total phone energy ({_fmt(idle['kwh'])} kWh)"


def recent_inferences(db, limit=6):
    """Latest model runs with the metrics named in the thesis (latency, CPU, memory, power, carbon)."""
    tz = _tz()
    return [{"time": _parse(r["created_at"]).astimezone(tz).strftime("%H:%M:%S"),
             "latency": (f"{r['inference_latency_ms']:.3f} ms" if r["inference_latency_ms"] < 1
                         else f"{r['inference_latency_ms']:.1f} ms"),
             "cpu": "–" if r["cpu_utilization_pct"] is None else f"{r['cpu_utilization_pct']:.0f}%",
             "ram": "–" if r["ram_utilization_mb"] is None else f"{r['ram_utilization_mb']:.0f} MB",
             "power": "–" if r["power_draw_w"] is None else f"{r['power_draw_w']:.2f} W",
             "energy": f"{r['energy_consumed_kwh']:.2e} kWh",
             "carbon": f"{r['carbon_emissions_kg'] * 1000:.2e} g",
             "method": r["measurement_method"]} for r in green.recent_inferences(db, limit)]


def _fmt(v):
    if not v:
        return "0"
    return f"{v:.2f}" if v >= 0.01 else f"{v:.2e}"


# ---- API-only helpers ----------------------------------------------------------------------------------

def events_log(db, limit, offset):
    return [dict(r) for r in green.events(db, limit, offset)]


def pending_records(db, limit, offset):
    return [{"patient_code": r["patient_code"], "fbs_mg_dl": r["fbs_mg_dl"], "risk": r["risk"],
             "sync_status": r["sync_status"], "offline_created_at": r["offline_created_at"],
             "gap_identifier": r["gap_identifier"]} for r in green.pending_sync(db, limit, offset)]


def run_measured_prediction(db, predictor, reader, features: dict, lab_screening_id=None):
    """Runs the model inside the measurement wrapper and writes one green_computing_log row.

    Does NOT create patients/visits/lab_screenings - the nurse flow saves those and can pass
    lab_screening_id now, or call green.link_lab_screening(log_id, ...) after saving.
    """
    cfg = current_app.config
    t0 = g.get("req_t0") or perf_counter()
    with measure(reader, cfg["EMISSION_FACTOR_KG_PER_KWH"], cfg["IDLE_POWER_W"],
                 cfg["ESTIMATED_TDP_W"]) as m:
        result = predictor.predict(features)
    ema = current_app.extensions.get("db_ms_ema", 0.0)   # DB time estimated from earlier writes
    log_id = green.insert_log(db, {
        "lab_screening_id": lab_screening_id, "inference_latency_ms": m.latency_ms,
        "cpu_utilization_pct": m.cpu_pct, "ram_utilization_mb": m.ram_mb, "power_draw_w": m.power_w,
        "energy_consumed_kwh": m.energy_kwh, "carbon_emissions_kg": m.carbon_kg,
        "request_ms": (perf_counter() - t0) * 1000.0, "db_io_ms": ema,
        "measurement_method": m.method})
    w0 = perf_counter()
    db.commit()
    current_app.extensions["db_ms_ema"] = 0.8 * ema + 0.2 * (perf_counter() - w0) * 1000.0 if ema else (perf_counter() - w0) * 1000.0
    return {**result, "green_log_id": log_id, "is_stub_model": predictor.is_stub,
            "measurement_method": m.method, "latency_ms": round(m.latency_ms, 3)}


# ---- "View all" pages ----------------------------------------------------------------------------

PER_PAGE = 25
EVENT_LABELS = {"DISCONNECT": ("Connection lost", "danger"), "RECONNECT": ("Connection restored", "success"),
                "SYNC_START": ("Sync started", "info"), "SYNC_COMPLETE": ("Sync complete", "success"),
                "SYNC_FAILED": ("Sync failed", "danger")}


def _local_full(ts):
    return _parse(ts).astimezone(_tz()).strftime("%Y-%m-%d %H:%M:%S") if ts else "–"


def paginate(total, page, params=None, per_page=PER_PAGE):
    """Pagination metadata plus ready-made links that keep the active filters (`params`)."""
    params = {k: v for k, v in (params or {}).items() if v}
    pages = max(1, -(-total // per_page))
    page = min(max(page, 1), pages)
    lo = max(1, page - 2)
    hi = min(pages, lo + 4)
    lo = max(1, hi - 4)

    def url(n):
        return "?" + urlencode({**params, "page": n})

    return {"page": page, "pages": pages, "total": total, "per_page": per_page,
            "offset": (page - 1) * per_page, "start": 0 if not total else (page - 1) * per_page + 1,
            "end": min(page * per_page, total),
            "links": [(n, url(n)) for n in range(lo, hi + 1)],
            "prev_url": url(page - 1) if page > 1 else None,
            "next_url": url(page + 1) if page < pages else None}


def events_page_context(db, page, event_type):
    event_type = event_type if event_type in green.EVENT_TYPES else None
    total = db.execute("SELECT COUNT(*) FROM network_event_log" + (" WHERE event_type = ?" if event_type else ""),
                       (event_type,) if event_type else ()).fetchone()[0]
    pg = paginate(total, page, {"type": event_type})
    rows, _ = green.events_page(db, PER_PAGE, pg["offset"], event_type)
    events = []
    for r in rows:
        label, tone = EVENT_LABELS[r["event_type"]]
        events.append({"time": _local_full(r["created_at"]), "label": label, "tone": tone,
                       "gap": r["gap_identifier"] or "–", "records": "–" if r["record_count"] is None else r["record_count"],
                       "duration": "–" if r["duration_s"] is None else human_duration(r["duration_s"]),
                       "detail": r["detail"] or ""})
    return {"events": events, "pg": pg, "event_type": event_type,
            "event_types": [(k, EVENT_LABELS[k][0]) for k in green.EVENT_TYPES],
            "timezone": current_app.config["TIMEZONE"]}


def pending_page_context(db, page, status):
    status = status if status in green.SYNC_FILTERS else "pending"
    total = db.execute("SELECT COUNT(*) FROM sync_queue_log q JOIN visits v ON v.id = q.visit_id "
                       "JOIN patients p ON p.id = v.patient_id AND p.deleted_at IS NULL WHERE "
                       + green.SYNC_FILTERS[status]).fetchone()[0]
    pg = paginate(total, page, {"status": status})
    rows, _ = green.sync_rows_page(db, status, PER_PAGE, pg["offset"])
    records = [{"id": r["patient_code"], "fbs": "–" if r["fbs_mg_dl"] is None else f"{r['fbs_mg_dl']:g}",
                "risk": r["risk"] or "Pending", "status": r["sync_status"].title(),
                "status_key": r["sync_status"], "queued_at": _local_full(r["offline_created_at"]),
                "synced_at": _local_full(r["synced_at"]), "gap": r["gap_identifier"] or "–",
                "attempts": r["attempts"], "error": r["last_error"] or ""} for r in rows]
    summ = sync_block(db)
    return {"records": records, "pg": pg, "status": status, "summary": summ,
            "monitor": monitor_status(db), "timezone": current_app.config["TIMEZONE"]}
