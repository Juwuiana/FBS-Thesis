"""Offline-record queue.

Two responsibilities:

1. `on_visit_saved()` - the ONE function the nurse/patient branch calls when it saves a visit.
   If the connectivity monitor currently reports the link as down, the visit is queued
   (sync_queue_log, status QUEUED) so it shows up on the Green Computing page as
   "logged while offline - pending sync". When the link is up it does nothing.

2. `flush_pending()` - hands queued records to a `SyncTransport` once the link is back, records
   SYNC_* events and updates each record's status. No transport is configured by default
   (there is no upstream server yet), so queued records honestly stay QUEUED until one exists.

Integration guide: docs/NURSE_BRANCH_INTEGRATION.md
"""
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Protocol, Tuple

from app.models import green

log = logging.getLogger("fbs.sync")

LINK_UP, LINK_DOWN = "up", "down"


def _sql_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def link_state(db) -> str:
    """'down' if the latest connectivity event is a DISCONNECT, else 'up' (also when unknown)."""
    last = green.last_connectivity_event(db)
    return LINK_DOWN if last and last["event_type"] == "DISCONNECT" else LINK_UP


def open_gap(db) -> Optional[Tuple[str, str]]:
    """(gap_identifier, started_at) of the DISCONNECT with no RECONNECT yet, else None."""
    if link_state(db) != LINK_DOWN:
        return None
    row = db.execute(
        """SELECT gap_identifier, created_at FROM network_event_log
           WHERE event_type = 'DISCONNECT' ORDER BY created_at DESC, id DESC LIMIT 1""").fetchone()
    return (row["gap_identifier"], row["created_at"]) if row else None


def on_visit_saved(db, visit_id: int, *, saved_at: Optional[str] = None) -> Optional[int]:
    """Queue `visit_id` if it was saved while the link is down.

    Call it inside the same transaction that saves the visit, before your `commit()`, so the
    visit and its queue entry are atomic. This function never commits and never raises: the
    queue is observability, so a failure here must not block a clinical save.

    Returns the queue row id when a row was added; None when the link is up, the visit was
    already queued, or the insert failed (logged).
    """
    try:
        gap = open_gap(db)
        if gap is None:
            return None
        cur = db.execute(
            """INSERT OR IGNORE INTO sync_queue_log (visit_id, offline_created_at, gap_identifier)
               VALUES (?, ?, ?)""", (visit_id, saved_at or _sql_now(), gap[0]))
        return cur.lastrowid if cur.rowcount else None
    except sqlite3.Error:
        log.exception("could not queue visit %s for sync", visit_id)
        return None


# ---- transport ----------------------------------------------------------------------------

@dataclass(frozen=True)
class QueuedRecord:
    visit_id: int
    queued_at: str
    gap_identifier: Optional[str]
    attempts: int


class SyncTransport(Protocol):
    """Whatever carries records upstream (server API, encrypted export, ...).

    `send` receives a batch and returns {visit_id: None if delivered else an error string}.
    Raising an exception fails the whole batch. Deliveries must be idempotent (at-least-once):
    a record may be offered again after a failure.
    """
    def send(self, records: List[QueuedRecord]) -> Dict[int, Optional[str]]: ...


_TRANSPORTS: Dict[str, Callable[[], SyncTransport]] = {}


def register_transport(name: str, factory: Callable[[], SyncTransport]) -> None:
    _TRANSPORTS[name] = factory


def get_transport(name: Optional[str]) -> Optional[SyncTransport]:
    """None for 'none'/empty (default). Unknown names raise, so a typo fails loudly at startup."""
    if not name or name == "none":
        return None
    if name not in _TRANSPORTS:
        raise ValueError(f"unknown sync transport {name!r}; registered: {sorted(_TRANSPORTS)}")
    return _TRANSPORTS[name]()


class DemoTransport:
    """Always succeeds. Used only by the presentation controls."""
    def send(self, records):
        return {r.visit_id: None for r in records}


register_transport("demo", DemoTransport)


@dataclass
class FlushResult:
    sent: int = 0
    failed: int = 0


def flush_pending(db, transport: SyncTransport, *, batch_size: int = 50,
                  gap_identifier: Optional[str] = None) -> FlushResult:
    """Send everything QUEUED/FAILED through `transport`; commits. Safe to call repeatedly."""
    result = FlushResult()
    batch = green.queued_for_flush(db, batch_size, gap_identifier)
    if not batch:
        return result
    green.log_event(db, "SYNC_START", gap_identifier, record_count=len(batch),
                    detail="Sending queued records")
    first_error = None
    while batch:
        records = [QueuedRecord(r["visit_id"], r["offline_created_at"], r["gap_identifier"],
                                r["attempts"]) for r in batch]
        try:
            outcome = transport.send(records)
        except Exception as exc:  # a transport bug/outage fails the batch, not the process
            log.exception("sync transport raised")
            outcome = {r.visit_id: f"transport error: {exc}" for r in records}
        for r in records:
            err = outcome.get(r.visit_id, "no result from transport")
            if err is None:
                green.mark_synced(db, r.visit_id)
                result.sent += 1
            else:
                green.mark_failed(db, r.visit_id, err)
                result.failed += 1
                first_error = first_error or str(err)
        db.commit()
        if result.failed:                 # stop on failures; the next reconnect retries them
            break
        batch = green.queued_for_flush(db, batch_size, gap_identifier)
    if result.failed:
        green.log_event(db, "SYNC_FAILED", gap_identifier, record_count=result.failed,
                        detail=(first_error or "")[:200])
    if result.sent:
        green.log_event(db, "SYNC_COMPLETE", gap_identifier, record_count=result.sent,
                        detail="Queue flushed" if not result.failed else "Partially flushed")
    db.commit()
    return result
