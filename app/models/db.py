import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[2] / "fbs_thesis.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")  
    return conn


def run_migrations() -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    TEXT PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    applied = {
        row["filename"]
        for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
    }
    pending = sorted(f for f in MIGRATIONS_DIR.glob("*.sql") if f.name not in applied)

    for f in pending:
        conn.executescript(f.read_text())
        conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (f.name,))
        conn.commit()

    conn.close()