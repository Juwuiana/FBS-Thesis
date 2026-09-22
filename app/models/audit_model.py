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


def get_recent_logs(db, limit=100, offset=0):
    rows = db.execute(
        """
        SELECT user_id, user_name, role, action, ip_address, severity, created_at
        FROM audit_log
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()

    logs = []
    for row in rows:
        try:
            created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            time = created_at.strftime("%I:%M %p")
            date = f"{created_at.strftime('%B')} {created_at.day}"
        except (TypeError, ValueError):
            time = row["created_at"] or ""
            date = ""
        logs.append({
            "time": time,
            "date": date,
            "user": row["user_name"] or "unknown",
            "role": _display_role(row["role"]),
            "action": row["action"],
            "ip": row["ip_address"] or "unknown",
            "severity": row["severity"],
        })
    return logs