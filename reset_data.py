# For testing only: wipes all patient data. Schema and lookup tables are untouched.
import sqlite3
from app.models.db import get_connection

conn = get_connection()

# Backup first, so a wrong run is never final.
backup = sqlite3.connect("instance/fbs_thesis_before_reset.sqlite3")
conn.backup(backup)
backup.close()

conn.execute("PRAGMA foreign_keys = OFF")

tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
parents = {t: {fk[2] for fk in conn.execute(f"PRAGMA foreign_key_list({t})")} for t in tables}

# Every table that depends on patients, directly or through another table.
doomed = {"patients"}
changed = True
while changed:
    changed = False
    for t, ps in parents.items():
        if t not in doomed and ps & doomed:
            doomed.add(t)
            changed = True

# Children first: delete a table only after nothing left still references it.
order, remaining = [], set(doomed)
while remaining:
    ready = [t for t in remaining
             if not any(t in parents[c] for c in remaining if c != t)] or list(remaining)
    for t in sorted(ready):
        order.append(t)
        remaining.discard(t)

for t in order:
    conn.execute(f"DELETE FROM {t}")
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (t,))   # reset AUTOINCREMENT
    except sqlite3.OperationalError:
        pass

conn.commit()
conn.execute("PRAGMA foreign_keys = ON")
leftover = conn.execute("PRAGMA foreign_key_check").fetchall()
conn.close()

print("Cleared:", ", ".join(order))
print("Foreign key problems left:", leftover or "none")