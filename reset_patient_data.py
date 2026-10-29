"""
Wipes all patient-related test data so counters go back to zero,
ready for a fresh CSV import. Leaves staff accounts (users), audit_log,
barangays, condition_catalog, model_performance_logs, and other reference/
system tables completely untouched.

Run from the project root (same place you ran check_schema.py):
    python reset_patient_data.py
"""
from app.db import get_connection

# Order matters: children before parents, even though the schema has
# ON DELETE CASCADE — this way it works regardless of whether foreign_keys
# enforcement happens to be on for this connection.
CHILD_TABLES_OF_VISITS = ["lab_screenings", "visit_conditions", "cvd_responses"]
CHILD_TABLES_OF_PATIENTS = ["patient_login_events"]

conn = get_connection()

before = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
print(f"patients before: {before}")

confirm = input(f"This will permanently delete all {before} patients and everything "
                f"linked to them (visits, lab screenings, etc). Type YES to continue: ")
if confirm != "YES":
    print("Aborted, nothing deleted.")
    conn.close()
    raise SystemExit(0)

for t in CHILD_TABLES_OF_VISITS:
    conn.execute(f"DELETE FROM {t}")

for t in CHILD_TABLES_OF_PATIENTS:
    conn.execute(f"DELETE FROM {t}")

conn.execute("DELETE FROM visits")
conn.execute("DELETE FROM patients")

# Reset autoincrement counters so the next import starts at id=1 again
reset_tables = ["patients", "visits", "lab_screenings", "visit_conditions",
                 "cvd_responses", "patient_login_events"]
for t in reset_tables:
    conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (t,))

conn.commit()

after = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
print(f"patients after: {after}")
print("Done. users, barangays, condition_catalog, audit_log, model_performance_logs "
      "and other reference/system tables were left untouched.")

conn.close()
