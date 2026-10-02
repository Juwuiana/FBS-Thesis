import sqlite3
con = sqlite3.connect('instance/fbs_thesis.sqlite3')
cur = con.cursor()
cur.execute("SELECT id, email, role FROM users LIMIT 10")
for r in cur.fetchall():
    print(r)
