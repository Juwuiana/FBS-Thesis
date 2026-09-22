"""Connectivity monitor: detects when the edge device loses / regains its network link.

How it works
------------
Every `interval_s` seconds it tries a TCP connect (no data is sent) to each configured probe
target; the link is "up" if any target answers. Debouncing (hysteresis) avoids flapping:
  up   -> down after `fail_threshold` consecutive failed probes
  down -> up   after `ok_threshold`   consecutive good probes
Transitions are written to network_event_log as DISCONNECT / RECONNECT, back-dated to the first
failed / first successful probe, and grouped by a gap_identifier. After a RECONNECT the queued
records are flushed through the configured transport (if any).

State is derived from the event log, so a restart continues an open gap instead of forgetting it.
The monitor also writes a heartbeat (app_settings) so the dashboard can warn when the monitor
itself is not running.

What "online" means is a deployment choice (FBS_PROBE_TARGETS): the internet (default), the
router/gateway (is the phone still on the clinic network?), or an upstream server.

Run:  flask --app run connectivity-monitor      Inspect:  flask --app run connectivity-status
"""
import logging
import socket
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence, Tuple

from app.models import green
from app.services import sync_queue

log = logging.getLogger("fbs.connectivity")

Target = Tuple[str, int]
HEARTBEAT_S = 60          # how often the monitor records that it is alive
STALE_AFTER_S = 3 * HEARTBEAT_S
KEY_LAST_PROBE = "connectivity_last_probe_at"
KEY_LAST_OK = "connectivity_last_probe_ok"


def sql_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_targets(text: str) -> List[Target]:
    """'1.1.1.1:53,8.8.8.8:53' -> [('1.1.1.1', 53), ('8.8.8.8', 53)]. Raises ValueError."""
    targets = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        host, sep, port = part.rpartition(":")
        if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError(f"bad probe target {part!r}; expected host:port")
        targets.append((host, int(port)))
    if not targets:
        raise ValueError("at least one probe target is required (FBS_PROBE_TARGETS)")
    return targets


def probe(targets: Sequence[Target], timeout_s: float,
          connect: Callable = socket.create_connection) -> bool:
    """True if a TCP connection to any target succeeds within the timeout."""
    for host, port in targets:
        try:
            connect((host, port), timeout=timeout_s).close()
            return True
        except OSError:
            continue
    return False


@dataclass(frozen=True)
class MonitorConfig:
    targets: Sequence[Target]
    interval_s: float = 15.0
    timeout_s: float = 2.0
    fail_threshold: int = 3
    ok_threshold: int = 2

    @classmethod
    def from_app_config(cls, cfg) -> "MonitorConfig":
        mc = cls(targets=parse_targets(cfg["PROBE_TARGETS"]), interval_s=cfg["PROBE_INTERVAL_S"],
                 timeout_s=cfg["PROBE_TIMEOUT_S"], fail_threshold=cfg["PROBE_FAIL_THRESHOLD"],
                 ok_threshold=cfg["PROBE_OK_THRESHOLD"])
        if mc.fail_threshold < 1 or mc.ok_threshold < 1 or mc.interval_s <= 0 or mc.timeout_s <= 0:
            raise ValueError("probe interval/timeout must be > 0 and thresholds >= 1")
        return mc

    @property
    def detection_delay_s(self) -> float:
        return self.fail_threshold * self.interval_s


@dataclass
class ConnectivityMonitor:
    conn_factory: Callable            # () -> sqlite3 connection (caller-owned; monitor closes it)
    config: MonitorConfig
    probe_fn: Callable[[], bool]
    transport: Optional[object] = None
    state: Optional[str] = field(default=None, init=False)
    _fails: int = field(default=0, init=False)
    _oks: int = field(default=0, init=False)
    _first_change_at: Optional[datetime] = field(default=None, init=False)
    _last_heartbeat: Optional[datetime] = field(default=None, init=False)

    # -- lifecycle --------------------------------------------------------------------
    def start(self) -> str:
        conn = self.conn_factory()
        try:
            self.state = sync_queue.link_state(conn)
        finally:
            conn.close()
        log.info("monitor started; link state from event log: %s", self.state)
        return self.state

    def step(self, now: Optional[datetime] = None) -> Optional[str]:
        """One probe cycle. Returns 'DISCONNECT' / 'RECONNECT' when the state flipped."""
        now = now or datetime.now(timezone.utc)
        if self.state is None:
            self.start()
        ok = bool(self.probe_fn())
        event = None
        if self.state == sync_queue.LINK_UP:
            if ok:
                self._fails, self._first_change_at = 0, None
            else:
                self._fails += 1
                self._first_change_at = self._first_change_at or now
                if self._fails >= self.config.fail_threshold:
                    event = self._disconnect(self._first_change_at)
        else:
            if ok:
                self._oks += 1
                self._first_change_at = self._first_change_at or now
                if self._oks >= self.config.ok_threshold:
                    event = self._reconnect(self._first_change_at)
            else:
                self._oks, self._first_change_at = 0, None
        self._heartbeat(now, ok)
        return event

    def run(self, stop: threading.Event) -> None:
        while self.state is None and not stop.is_set():   # DB may be briefly locked at boot
            try:
                self.start()
            except Exception:
                log.exception("monitor could not read its initial state; retrying")
                stop.wait(self.config.interval_s)
        while not stop.is_set():
            try:
                self.step()
            except Exception:  # transient DB lock etc. must not kill the monitor
                log.exception("monitor step failed; continuing")
            stop.wait(self.config.interval_s)
        log.info("monitor stopped")

    # -- transitions ---------------------------------------------------------------------
    def _disconnect(self, started: datetime) -> str:
        gap_id = f"gap-{started.astimezone(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4]}"
        conn = self.conn_factory()
        try:
            green.log_event(conn, "DISCONNECT", gap_id, created_at=sql_utc(started),
                            detail="Network link lost")
            conn.commit()
        finally:
            conn.close()
        self.state, self._fails, self._oks, self._first_change_at = sync_queue.LINK_DOWN, 0, 0, None
        log.warning("link DOWN (gap %s)", gap_id)
        return "DISCONNECT"

    def _reconnect(self, restored: datetime) -> str:
        conn = self.conn_factory()
        try:
            gap = sync_queue.open_gap(conn)
            gap_id, started = gap if gap else (None, None)
            queued = green.gap_record_count(conn, gap_id) if gap_id else 0
            duration = None
            if started:
                begun = datetime.strptime(started, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                duration = max((restored - begun).total_seconds(), 0.0)
            green.log_event(conn, "RECONNECT", gap_id, record_count=queued, duration_s=duration,
                            created_at=sql_utc(restored), detail="Network link restored")
            conn.commit()
            if self.transport is not None and queued:
                res = sync_queue.flush_pending(conn, self.transport, gap_identifier=None)
                log.info("flushed %s record(s), %s failed", res.sent, res.failed)
        finally:
            conn.close()
        self.state, self._fails, self._oks, self._first_change_at = sync_queue.LINK_UP, 0, 0, None
        log.warning("link UP (gap %s, %s queued)", gap_id, queued)
        return "RECONNECT"

    def _heartbeat(self, now: datetime, ok: bool) -> None:
        if self._last_heartbeat and (now - self._last_heartbeat).total_seconds() < HEARTBEAT_S:
            return
        conn = self.conn_factory()
        try:
            green.set_kv(conn, KEY_LAST_PROBE, sql_utc(now))
            green.set_kv(conn, KEY_LAST_OK, "1" if ok else "0")
            conn.commit()
        finally:
            conn.close()
        self._last_heartbeat = now


def monitor_status(db, now: Optional[datetime] = None) -> dict:
    """{'status': 'running'|'stale'|'never', 'last_probe_at': str|None, 'last_probe_ok': bool|None}"""
    now = now or datetime.now(timezone.utc)
    last = green.get_kv(db, KEY_LAST_PROBE)
    if not last:
        return {"status": "never", "last_probe_at": None, "last_probe_ok": None}
    age = (now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)).total_seconds()
    return {"status": "running" if age <= STALE_AFTER_S else "stale", "last_probe_at": last,
            "last_probe_ok": green.get_kv(db, KEY_LAST_OK) == "1"}
