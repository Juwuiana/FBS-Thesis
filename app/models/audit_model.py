from datetime import datetime
from datetime import timedelta


def log_event(db, *, user_id, user_name, role, action, ip_address, severity="Info"):
    """Record one audit event and make it visible to the next request."""
    if user_id is not None and db.execute(
        "SELECT 1 FROM users WHERE id = ?", (user_id,)
    ).fetchone() is None:
        user_id = None
    db.execute(
        """
        INSERT INTO audit_log
            (user_id, user_name, role, action, ip_address, severity)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            user_name or "unknown",
            role or "Unknown",
            action,
            ip_address or "unknown",
            severity,
        ),
    )
    db.commit()


def _display_role(role):
    return {
        "medical_officer": "Admin",
        "health_worker": "Nurse",
    }.get(role, role or "Unknown")


from datetime import datetime
from zoneinfo import ZoneInfo

PH_TZ = ZoneInfo("Asia/Manila")


def _format_logs(rows):
    logs = []
    for row in rows:
        try:
            created_at = (
                datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=ZoneInfo("UTC"))
                .astimezone(PH_TZ)
            )
            time = created_at.strftime("%I:%M %p")
            date = f"{created_at.strftime('%B')} {created_at.day}"
            timestamp = (
                f"{created_at.strftime('%B')} {created_at.day}, {created_at.year} "
                f"· {created_at.strftime('%I:%M:%S %p')}"
            )
        except (TypeError, ValueError):
            time = row["created_at"] or ""
            date = ""
            timestamp = row["created_at"] or ""
            timestamp_iso = row["created_at"] or ""
        else:
            timestamp_iso = row["created_at"]
        logs.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "time": time,
            "date": date,
            "timestamp": timestamp,
            "timestamp_iso": timestamp_iso,
            "user": row["user_name"] or "unknown",
            "role": _display_role(row["role"]),
            "action": row["action"],
            "ip": row["ip_address"] or "unknown",
            "severity": row["severity"],
        })
    return logs


def get_recent_logs(db, limit=100, offset=0):
    """System-wide log, newest first -- for the admin-facing audit view."""
    rows = db.execute(
        """
        SELECT id, user_id, user_name, role, action, ip_address, severity, created_at
        FROM audit_log
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return _format_logs(rows)


def get_logs_count(db):
    """Return the total number of system-wide audit events."""
    return db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


def get_recent_logs_for_user(db, user_id, limit=20):
    """Same shape, scoped to one account -- backs the nurse's own
    Privacy & Security > Audit Trail tab ("your recorded actions")."""
    rows = db.execute(
        """
        SELECT id, user_id, user_name, role, action, ip_address, severity, created_at
        FROM audit_log
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return _format_logs(rows)

def _ph_midnight_as_utc(day):
    """Stored timestamps are UTC but people think in Manila time, so a picked
    calendar day is converted: Manila 00:00 of that day -> the matching UTC string."""
    local = datetime(day.year, day.month, day.day, tzinfo=PH_TZ)
    return local.astimezone(_UTC).strftime("%Y-%m-%d %H:%M:%S")

_UTC = ZoneInfo("UTC")
_MAX_SEARCH_LEN = 100

def _user_log_where(user_id, severity=None, q=None, date_from=None, date_to=None):
    """(WHERE clause, params). Everything user-supplied is a bound parameter;
    the LIKE wildcards in a search are escaped so '%' and '_' match literally."""
    where, params = ["user_id = ?"], [user_id]
    if severity:
        where.append("severity = ?")
        params.append(severity)
    if q:
        q = q.strip()[:_MAX_SEARCH_LEN]
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("action LIKE ? ESCAPE '\\'")
        params.append(f"%{escaped}%")
    if date_from:
        where.append("created_at >= ?")
        params.append(_ph_midnight_as_utc(date_from))
    if date_to:
        where.append("created_at < ?")                       # end of day = start of next day
        params.append(_ph_midnight_as_utc(date_to + timedelta(days=1)))
    return " AND ".join(where), params


def list_severities_for_user(db, user_id):
    """Severity values this account actually has, in a sensible order, for the filter dropdown."""
    rows = db.execute(
        "SELECT DISTINCT severity FROM audit_log WHERE user_id = ? AND severity IS NOT NULL", (user_id,)
    ).fetchall()
    found = {r["severity"] for r in rows}
    order = ["Info", "Success", "Warning", "Critical"]
    return [s for s in order if s in found] + sorted(found - set(order))


def count_logs_for_user(db, user_id, *, severity=None, q=None, date_from=None, date_to=None):
    where, params = _user_log_where(user_id, severity, q, date_from, date_to)
    return db.execute(f"SELECT COUNT(*) FROM audit_log WHERE {where}", params).fetchone()[0]


def get_logs_for_user_page(db, user_id, *, severity=None, q=None, date_from=None, date_to=None,
                           limit=10, offset=0):
    """One page of this account's own log, newest first, same shape as get_recent_logs_for_user."""
    where, params = _user_log_where(user_id, severity, q, date_from, date_to)
    rows = db.execute(
        f"""
        SELECT id, user_id, user_name, role, action, ip_address, severity, created_at
        FROM audit_log
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, int(limit), int(offset)),
    ).fetchall()
    return _format_logs(rows)