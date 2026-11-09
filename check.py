from app.models.db import get_connection

conn = get_connection()
rows = conn.execute("""
SELECT COALESCE(v.status, 'no visit') AS visit_status,
       CASE WHEN ls.fbs_mg_dl IS NULL THEN 'no FBS' ELSE 'has FBS' END AS lab,
       COUNT(*) AS n
FROM patients p
LEFT JOIN visits v ON v.id = (SELECT v2.id FROM visits v2 WHERE v2.patient_id = p.id ORDER BY v2.id DESC LIMIT 1)
LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
WHERE p.deleted_at IS NULL AND p.anonymized_at IS NULL
GROUP BY 1, 2
""").fetchall()
for r in rows:
    print(dict(r))
conn.close()