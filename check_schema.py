from app.db import get_connection

TABLES = [
    "patients", "visits", "lab_screenings", "visit_conditions",
    "cvd_responses", "patient_login_events", "model_performance_logs",
    "users", "audit_log",
]

conn = get_connection()
for t in TABLES:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)
    ).fetchone()
    print(f"-- {t} --")
    print(row["sql"] if row else "(not found)")
    print()

conn.close()
