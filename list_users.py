import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
cols = [c[1] for c in con.execute("PRAGMA table_info(users)")]
extra = ", (active_session_token IS NOT NULL) AS has_session, active_session_last_seen" if "active_session_token" in cols else ""
q = f"""select id, first_name, last_name, email, role, facility, status,
        is_suspended, failed_login_attempts, last_login_at{extra}
        from users order by role, id"""
cur = con.execute(q)
print([d[0] for d in cur.description])
for r in cur:
    print(tuple(r))
