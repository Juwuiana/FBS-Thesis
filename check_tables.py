"""Quick sanity check: what tables exist, and which migrations have run.

Reads the same path as the app (config DATABASE -> $DATABASE_PATH ->
instance/fbs_thesis.sqlite3) instead of hardcoding one.
"""
from app.db import applied_migrations, database_path, get_connection, migration_files

conn = get_connection()
print(f"database: {database_path()}\n")

print("tables:")
for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
):
    print(f"  {row['name']}")

applied = applied_migrations(conn)
print("\nmigrations:")
for path in migration_files():
    print(f"  [{'x' if path.name in applied else ' '}] {path.name}")

conn.close()
