"""for checking lang kasi may mga migrations na hindi nag apply sa local db ko
 so this script is just for checking if migrations are applied or not"""

from app.db import get_connection, run_migrations, applied_migrations, pending_migrations, database_path

conn = get_connection()
run_migrations(conn)

print("DB path:", database_path())
print("Applied:", applied_migrations(conn))
print("Pending:", pending_migrations(conn))
print("patients columns:", [r[1] for r in conn.execute("PRAGMA table_info(patients)")])