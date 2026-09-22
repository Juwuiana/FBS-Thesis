"""Periodic device sampling for system_telemetry_log (idle power, uptime, power source)."""
import time

from app.ml.green_metrics import BatteryReader


def power_source(sample: dict, feed: str) -> str:
    if sample.get("charging"):
        return "SOLAR_UPS" if feed == "solar_ups" else "AC_CHARGING"
    return "BATTERY"


def record_sample(conn, reader: BatteryReader, feed: str = "grid", is_idle: bool = False):
    """Insert one telemetry row. Returns False if the battery nodes are unreadable."""
    s = reader.sample()
    if s is None:
        return False
    # power_w is only meaningful on battery; while charging the reading is charge current, so
    # store NULL (the row still counts for uptime and power-source history).
    power_w = None if s.get("charging") else s["power_w"]
    conn.execute(
        "INSERT INTO system_telemetry_log (battery_level_pct, battery_temp_c, power_w, is_idle,"
        " power_source) VALUES (?,?,?,?,?)",
        (s["level_pct"], s["temp_c"], power_w, 1 if is_idle else 0, power_source(s, feed)),
    )
    conn.commit()
    return True


def run_loop(conn_factory, reader, feed, interval_s, is_idle_fn=lambda: False):
    """Blocking loop for `flask telemetry-loop`. Opens a connection per sample so a long-running
    process never holds a write lock, and batches nothing: one tiny insert per interval."""
    while True:
        conn = conn_factory()
        try:
            record_sample(conn, reader, feed, is_idle_fn())
        finally:
            conn.close()
        time.sleep(interval_s)
