import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("""CREATE INDEX IF NOT EXISTS idx_visits_pending_edit_acknowledgement
    ON visits(edit_acknowledged_by_staff_id)
    WHERE edit_acknowledged_by_staff_id IS NOT NULL""")
con.commit()
print([r[0] for r in con.execute("select name from sqlite_master where type='index' and tbl_name='visits'")])
