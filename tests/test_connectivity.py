"""Connectivity monitor + offline sync queue."""
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.models import green  # noqa: E402
from app.services import connectivity, sync_queue  # noqa: E402
from config import Config  # noqa: E402

T0 = datetime(2026, 9, 21, 8, 0, 0, tzinfo=timezone.utc)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


@pytest.fixture
def ctx(tmp_path):
    cfg = type("C", (Config,), {"DATABASE": str(tmp_path / "c.sqlite3"), "TESTING": True,
                                "BATTERY_SYSFS_DIR": str(tmp_path / "nobat")})
    app = create_app(cfg)
    with app.app_context():
        yield app


def make_monitor(results, transport=None, fail=3, ok=2):
    """Monitor whose probe returns the scripted booleans in order."""
    it = iter(results)
    cfg = connectivity.MonitorConfig(targets=[("h", 1)], interval_s=15, fail_threshold=fail, ok_threshold=ok)
    return connectivity.ConnectivityMonitor(get_connection, cfg, lambda: next(it), transport)


def make_visit(conn, code="P-1"):
    pid = conn.execute("INSERT INTO patients (patient_code,last_name,first_name,birthdate,sex)"
                       " VALUES (?, 'A','B','1980-01-01','Male')", (code,)).lastrowid
    vid = conn.execute("INSERT INTO visits (patient_id,visit_type,assessment_date)"
                       " VALUES (?, 'intake','2026-09-21')", (pid,)).lastrowid
    return vid


# ---- probe / config ---------------------------------------------------------------------

def test_parse_targets():
    assert connectivity.parse_targets("1.1.1.1:53, router.lan:80") == [("1.1.1.1", 53), ("router.lan", 80)]
    for bad in ("", "nohost", "a:notaport", "a:0", "a:70000", ":53"):
        with pytest.raises(ValueError):
            connectivity.parse_targets(bad)


def test_probe_any_target_wins_and_all_fail():
    class Sock:
        def close(self): pass

    calls = []

    def connect(addr, timeout):
        calls.append(addr)
        if addr[0] == "bad":
            raise OSError("unreachable")
        return Sock()

    assert connectivity.probe([("bad", 1), ("good", 2)], 1, connect) is True
    assert calls == [("bad", 1), ("good", 2)]
    assert connectivity.probe([("bad", 1)], 1, connect) is False


# ---- state machine ------------------------------------------------------------------------

def test_debounce_short_blips_are_ignored(ctx):
    m = make_monitor([False, False, True, False, False, True])   # never 3 in a row
    assert [m.step(at(15 * i)) for i in range(6)] == [None] * 6
    assert sync_queue.link_state(get_connection()) == "up"


def test_disconnect_is_backdated_and_reconnect_records_gap(ctx):
    m = make_monitor([False, False, False,           # DOWN after the 3rd, back-dated to the 1st
                      True, False, True, True])      # a lone success is reset; UP at 2nd of last streak
    events = [m.step(at(15 * i)) for i in range(3)]
    assert events == [None, None, "DISCONNECT"] and m.state == "down"
    conn = get_connection()
    d = conn.execute("SELECT * FROM network_event_log WHERE event_type='DISCONNECT'").fetchone()
    assert d["created_at"] == "2026-09-21 08:00:00" and d["gap_identifier"].startswith("gap-20260921080000")
    vid = make_visit(conn)                           # a visit saved during the gap is queued
    assert sync_queue.on_visit_saved(conn, vid) is not None
    conn.commit()
    assert [m.step(at(45 + 15 * i)) for i in range(4)] == [None, None, None, "RECONNECT"]
    r = conn.execute("SELECT * FROM network_event_log WHERE event_type='RECONNECT'").fetchone()
    assert r["gap_identifier"] == d["gap_identifier"] and r["record_count"] == 1
    assert r["created_at"] == "2026-09-21 08:01:15"          # first success of the final streak
    assert r["duration_s"] == pytest.approx(75)
    assert sync_queue.link_state(conn) == "up"


def test_restart_continues_an_open_gap(ctx):
    m = make_monitor([False] * 3)
    for i in range(3):
        m.step(at(15 * i))
    fresh = make_monitor([True, True])                       # process restarted while still down
    assert fresh.start() == "down"
    assert [fresh.step(at(100 + 15 * i)) for i in range(2)] == [None, "RECONNECT"]


def test_heartbeat_and_status(ctx):
    conn = get_connection()
    assert connectivity.monitor_status(conn)["status"] == "never"
    make_monitor([True]).step(at(0))
    st = connectivity.monitor_status(get_connection(), at(30))
    assert st["status"] == "running" and st["last_probe_ok"] is True
    assert connectivity.monitor_status(get_connection(), at(600))["status"] == "stale"


# ---- queue + flush ----------------------------------------------------------------------------

def test_on_visit_saved_rules(ctx):
    conn = get_connection()
    vid = make_visit(conn)
    assert sync_queue.on_visit_saved(conn, vid) is None            # link up: nothing queued
    green.log_event(conn, "DISCONNECT", "gap-x")
    qid = sync_queue.on_visit_saved(conn, vid)
    assert qid is not None
    assert sync_queue.on_visit_saved(conn, vid) is None            # idempotent
    assert sync_queue.on_visit_saved(conn, 99999) is None          # FK failure never raises


def test_on_visit_saved_does_not_commit(ctx):
    conn = get_connection()
    vid = make_visit(conn)
    green.log_event(conn, "DISCONNECT", "gap-x")
    conn.commit()
    sync_queue.on_visit_saved(conn, vid)
    other = get_connection()
    assert other.execute("SELECT COUNT(*) FROM sync_queue_log").fetchone()[0] == 0   # caller controls commit
    conn.commit()
    assert other.execute("SELECT COUNT(*) FROM sync_queue_log").fetchone()[0] == 1


class Recorder:
    def __init__(self, fail_ids=()):
        self.fail_ids, self.batches = set(fail_ids), []

    def send(self, records):
        self.batches.append([r.visit_id for r in records])
        return {r.visit_id: ("rejected" if r.visit_id in self.fail_ids else None) for r in records}


def _queue_two(conn):
    green.log_event(conn, "DISCONNECT", "gap-1")
    vids = [make_visit(conn, "P-1"), make_visit(conn, "P-2")]
    for v in vids:
        sync_queue.on_visit_saved(conn, v)
    conn.commit()
    return vids


def test_reconnect_flushes_through_transport(ctx):
    conn = get_connection()
    vids = _queue_two(conn)
    rec = Recorder()
    m = make_monitor([True, True], transport=rec)
    m.start()
    m.step(at(0)), m.step(at(15))
    assert sorted(rec.batches[0]) == sorted(vids)
    rows = conn.execute("SELECT sync_status, synced_at FROM sync_queue_log").fetchall()
    assert {r["sync_status"] for r in rows} == {"SYNCED"} and all(r["synced_at"] for r in rows)
    types = [r[0] for r in conn.execute("SELECT event_type FROM network_event_log ORDER BY id")]
    assert types == ["DISCONNECT", "RECONNECT", "SYNC_START", "SYNC_COMPLETE"]


def test_failed_records_are_kept_and_retried(ctx):
    conn = get_connection()
    v1, v2 = _queue_two(conn)
    res = sync_queue.flush_pending(conn, Recorder(fail_ids={v2}))
    assert (res.sent, res.failed) == (1, 1)
    row = conn.execute("SELECT sync_status, attempts, last_error FROM sync_queue_log WHERE visit_id=?", (v2,)).fetchone()
    assert (row["sync_status"], row["attempts"], row["last_error"]) == ("FAILED", 1, "rejected")
    assert "SYNC_FAILED" in [r[0] for r in conn.execute("SELECT event_type FROM network_event_log")]
    retry = sync_queue.flush_pending(conn, Recorder())                # next reconnect retries FAILED rows
    assert (retry.sent, retry.failed) == (1, 0)


def test_transport_exception_fails_batch_not_process(ctx):
    conn = get_connection()
    _queue_two(conn)

    class Boom:
        def send(self, records):
            raise RuntimeError("upstream down")

    res = sync_queue.flush_pending(conn, Boom())
    assert res.failed == 2 and res.sent == 0
    assert conn.execute("SELECT COUNT(*) FROM sync_queue_log WHERE sync_status='FAILED'").fetchone()[0] == 2


def test_no_transport_leaves_records_queued(ctx):
    conn = get_connection()
    _queue_two(conn)
    m = make_monitor([True, True], transport=None)
    m.start(), m.step(at(0)), m.step(at(15))
    assert conn.execute("SELECT COUNT(*) FROM sync_queue_log WHERE sync_status='QUEUED'").fetchone()[0] == 2


def test_transport_registry():
    assert sync_queue.get_transport("none") is None and sync_queue.get_transport("") is None
    assert isinstance(sync_queue.get_transport("demo"), sync_queue.DemoTransport)
    with pytest.raises(ValueError):
        sync_queue.get_transport("typo")


def test_run_loop_survives_db_errors(ctx):
    import threading

    def locked():
        raise sqlite3.OperationalError("database is locked")

    cfg = connectivity.MonitorConfig(targets=[("h", 1)], interval_s=0.01)
    m = connectivity.ConnectivityMonitor(locked, cfg, lambda: True)   # start() AND step() both fail
    stop = threading.Event()
    t = threading.Thread(target=m.run, args=(stop,))
    t.start()
    stop.wait(0.1)
    assert t.is_alive()                     # still retrying, not crashed
    stop.set()
    t.join(2)
    assert not t.is_alive()
