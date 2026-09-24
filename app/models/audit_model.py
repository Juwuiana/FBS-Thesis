from datetime import datetime


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