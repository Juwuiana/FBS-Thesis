import sqlite3
con = sqlite3.connect('instance/fbs_thesis.sqlite3')
print(con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
