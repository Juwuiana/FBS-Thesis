# for testing lang toh para ma reset ko database
from app.models.db import get_connection

TABLES_IN_DELETE_ORDER = [
    "cvd_responses",
    "visit_conditions",
    "lab_screenings",
    "visits",
    "patients",
]

conn = get_connection()
for table in TABLES_IN_DELETE_ORDER:
    conn.execute(f"DELETE FROM {table}")
    conn.execute(f"DELETE FROM sqlite_sequence WHERE name = ?", (table,))  # resets AUTOINCREMENT counters
conn.commit()
conn.close()
print("All patient data cleared. Schema and lookup tables (barangays, condition_catalog) untouched.")