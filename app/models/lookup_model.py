"""
read-only lookups pang populate 

"""
from app.models.db import get_connection


def list_barangays() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT name FROM barangays ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def list_conditions(category: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT code FROM condition_catalog WHERE category = ? ORDER BY id",
        (category,)
    ).fetchall()
    conn.close()
    return [r["code"] for r in rows]


def get_barangay_id(name: str) -> int | None:
    if not name:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM barangays WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None