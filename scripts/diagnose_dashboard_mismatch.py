"""Read-only: explain why the admin and nurse dashboards disagree.

Usage: python -m scripts.diagnose_dashboard_mismatch [path-to-sqlite]
Opens the database with mode=ro, so it can never write.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import database_path  # noqa: E402

RISK = "COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level)"
ADMIN_RISK = "COALESCE(ls.final_risk_level, ls.preliminary_risk_level)"


def connect(path):
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def totals(conn, sql_from, risk):
    r = conn.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN {risk} IN ('Moderate','High') THEN 1 ELSE 0 END) AS at_risk,
               SUM(CASE WHEN {risk} = 'High' THEN 1 ELSE 0 END) AS high
        {sql_from}""").fetchone()
    return r["total"] or 0, r["at_risk"] or 0, r["high"] or 0


ADMIN_FROM = """
    FROM lab_screenings ls
    WHERE ls.id IN (
        SELECT id FROM (
            SELECT ls2.id, ROW_NUMBER() OVER (
                PARTITION BY v2.patient_id ORDER BY ls2.test_datetime DESC, ls2.id DESC) AS rn
            FROM lab_screenings ls2 JOIN visits v2 ON v2.id = ls2.visit_id)
        WHERE rn = 1)
"""

NURSE_FROM = """
    FROM patients p
    JOIN visits v ON v.id = (SELECT v2.id FROM visits v2 WHERE v2.patient_id = p.id ORDER BY v2.id DESC LIMIT 1)
    JOIN lab_screenings ls ON ls.visit_id = v.id
    WHERE p.deleted_at IS NULL AND ls.fbs_mg_dl IS NOT NULL
"""

CANON_FROM = """
    FROM (
        SELECT ls.*, ROW_NUMBER() OVER (
            PARTITION BY v.patient_id ORDER BY ls.test_datetime DESC, ls.id DESC) AS rn
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        WHERE p.deleted_at IS NULL AND p.anonymized_at IS NULL AND ls.fbs_mg_dl IS NOT NULL
    ) ls
    WHERE ls.rn = 1
"""


def one(conn, sql):
    return conn.execute(sql).fetchone()[0]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else database_path()
    print(f"Database: {path} (opened read-only)\n")
    conn = connect(path)

    print("Admin-style (current code)   total / at-risk / high:", totals(conn, ADMIN_FROM, ADMIN_RISK))
    print("Nurse-style (current code)   total / at-risk / high:", totals(conn, NURSE_FROM, RISK))
    print("Canonical (proposed)         total / at-risk / high:", totals(conn, CANON_FROM, RISK))
    print()

    print("Cause 1 - patients soft-deleted (Recycle Bin) with screenings, counted by admin:",
          one(conn, """SELECT COUNT(DISTINCT p.id) FROM patients p JOIN visits v ON v.patient_id = p.id
                       JOIN lab_screenings ls ON ls.visit_id = v.id WHERE p.deleted_at IS NOT NULL"""))
    print("         anonymized patients with screenings:",
          one(conn, """SELECT COUNT(DISTINCT p.id) FROM patients p JOIN visits v ON v.patient_id = p.id
                       JOIN lab_screenings ls ON ls.visit_id = v.id WHERE p.anonymized_at IS NOT NULL"""))
    print("Cause 2 - screenings with NULL fbs_mg_dl:",
          one(conn, "SELECT COUNT(*) FROM lab_screenings WHERE fbs_mg_dl IS NULL"))
    print("Cause 3 - patients whose latest-by-date screening differs from latest-by-visit-id:",
          one(conn, """
            WITH by_date AS (
                SELECT patient_id, id FROM (
                    SELECT v.patient_id, ls.id, ROW_NUMBER() OVER (
                        PARTITION BY v.patient_id ORDER BY ls.test_datetime DESC, ls.id DESC) AS rn
                    FROM lab_screenings ls JOIN visits v ON v.id = ls.visit_id) WHERE rn = 1),
            by_visit AS (
                SELECT patient_id, id FROM (
                    SELECT v.patient_id, ls.id, ROW_NUMBER() OVER (
                        PARTITION BY v.patient_id ORDER BY v.id DESC, ls.id DESC) AS rn
                    FROM lab_screenings ls JOIN visits v ON v.id = ls.visit_id) WHERE rn = 1)
            SELECT COUNT(*) FROM by_date d JOIN by_visit b ON b.patient_id = d.patient_id AND b.id != d.id"""))
    print("Cause 4 - screenings with only model_predicted_risk_level (no final/preliminary):",
          one(conn, """SELECT COUNT(*) FROM lab_screenings
                       WHERE final_risk_level IS NULL AND preliminary_risk_level IS NULL
                         AND model_predicted_risk_level IS NOT NULL"""))
    print("         screenings with no risk level at all:",
          one(conn, """SELECT COUNT(*) FROM lab_screenings
                       WHERE final_risk_level IS NULL AND preliminary_risk_level IS NULL
                         AND model_predicted_risk_level IS NULL"""))
    print("Cause 5 - nurse donut 'Pending' rows (no FBS filter, incl. no-risk/no-screening latest visit):",
          one(conn, """SELECT COUNT(*) FROM patients p
                       LEFT JOIN visits v ON v.id = (SELECT v2.id FROM visits v2 WHERE v2.patient_id = p.id ORDER BY v2.id DESC LIMIT 1)
                       LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
                       WHERE p.deleted_at IS NULL
                         AND COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) IS NULL"""))
    conn.close()


if __name__ == "__main__":
    main()
