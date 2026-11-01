import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print("== schema_migrations (all) ==")
for r in con.execute("select filename, applied_at from schema_migrations order by applied_at, filename"):
    print("  ", r[0], "|", r[1])
print("\n== tables and columns ==")
for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
    print(t, [c[1] for c in con.execute(f"PRAGMA table_info({t})")])
print("\n== indexes ==")
for n, t in con.execute("select name, tbl_name from sqlite_master where type='index' and name not like 'sqlite_%' order by tbl_name, name"):
    print("  ", t, "->", n)
