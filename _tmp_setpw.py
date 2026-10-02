import sqlite3
from werkzeug.security import generate_password_hash

con = sqlite3.connect('instance/fbs_thesis.sqlite3')
cur = con.cursor()
cur.execute("SELECT password_hash FROM users WHERE id=1")
old = cur.fetchone()[0]
with open('_old_hash.txt', 'w') as f:
    f.write(old)
new_hash = generate_password_hash('TempDebug123!')
cur.execute("UPDATE users SET password_hash=? WHERE id=1", (new_hash,))
con.commit()
print("done")
