"""Dev-only seed data for visually verifying the Admin Landing Dashboard
(charts, legend, barangay list, recent screenings, timeline) against a
mostly-empty local database.

    python -m scripts.seed_dashboard_dev            # add seed data
    python -m scripts.seed_dashboard_dev --purge    # remove everything this script added

Seed patients use patient_code 'SEEDTEST-####' so they're easy to find and
purge, and are kept clearly separate from scripts/seed_green_demo.py's
'DEMO-####' patients (different feature, do not mix purge logic).
"""
import random
import sys
from datetime import date, datetime, timedelta

from app.db import get_connection

# (final_risk_level, model_predicted_risk_level, fbs range) -- kept
# internally consistent so the dashboard's numbers read as plausible.
RISK_PROFILES = [
    ("Low", "Normal", (75, 99)),
    ("Moderate", "Pre-Diabetic", (100, 125)),
    ("High", "Diabetic", (126, 160)),
]
RISK_WEIGHTS = [60, 25, 15]  # roughly realistic screening population split

# Reuses the same barangay names the dashboard template's own placeholder
# fallback used, so the "Barangay List by At-Risk Count" panel exercises
# more than one bar.
BARANGAY_NAMES = ["Kanluran", "Market Area (Poblacion)", "Dila", "Dita", "Malitlit"]

FIRST_NAMES = ["Juan", "Maria", "Pedro", "Ana", "Jose", "Rosa", "Carlos", "Elena",
               "Miguel", "Carmen", "Antonio", "Luisa", "Ramon", "Teresa", "Manuel"]
LAST_NAMES = ["Dela Cruz", "Santos", "Reyes", "Garcia", "Perez", "Mendoza",
              "Torres", "Flores", "Ramos", "Villanueva"]


def purge(conn):
    n = conn.execute(
        "SELECT COUNT(*) FROM patients WHERE patient_code LIKE 'SEEDTEST-%'"
    ).fetchone()[0]
    conn.execute("DELETE FROM patients WHERE patient_code LIKE 'SEEDTEST-%'")
    conn.commit()
    print(f"Removed {n} seed patient(s) (visits/lab_screenings cascaded).")


def barangay_ids(conn):
    rows = conn.execute(
        f"SELECT id, name FROM barangays WHERE name IN "
        f"({','.join('?' for _ in BARANGAY_NAMES)})",
        BARANGAY_NAMES,
    ).fetchall()
    by_name = {row["name"]: row["id"] for row in rows}
    missing = [n for n in BARANGAY_NAMES if n not in by_name]
    if missing:
        raise RuntimeError(
            f"Expected barangays not found (check migration 0001 ran): {missing}"
        )
    return [by_name[n] for n in BARANGAY_NAMES]


def seed(conn, days_back=6, per_day=3):
    rnd = random.Random(42)
    ids = barangay_ids(conn)
    counter = 1

    for day_offset in range(days_back, -1, -1):  # oldest day first
        day = date.today() - timedelta(days=day_offset)
        for _ in range(per_day):
            code = f"SEEDTEST-{counter:04d}"
            counter += 1

            sex = rnd.choice(["Male", "Female"])
            first = rnd.choice(FIRST_NAMES)
            last = rnd.choice(LAST_NAMES)
            age_years = rnd.randint(25, 75)
            birthdate = (date.today() - timedelta(days=age_years * 365)).isoformat()
            barangay_id = rnd.choice(ids)

            pid = conn.execute(
                "INSERT INTO patients "
                "(patient_code, last_name, first_name, birthdate, sex, barangay_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code, last, first, birthdate, sex, barangay_id),
            ).lastrowid

            vid = conn.execute(
                "INSERT INTO visits (patient_id, visit_type, assessment_date, status) "
                "VALUES (?, 'intake', ?, 'submitted')",
                (pid, day.isoformat()),
            ).lastrowid

            final_risk, model_risk, fbs_range = rnd.choices(
                RISK_PROFILES, weights=RISK_WEIGHTS, k=1
            )[0]
            fbs = rnd.randint(*fbs_range)
            test_dt = datetime.combine(
                day, datetime.min.time()
            ) + timedelta(hours=rnd.randint(7, 16), minutes=rnd.randint(0, 59))

            conn.execute(
                "INSERT INTO lab_screenings "
                "(visit_id, fbs_mg_dl, test_datetime, preliminary_risk_level, "
                " model_predicted_risk_level, model_confidence, final_risk_level) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (vid, fbs, test_dt.isoformat(), final_risk, model_risk,
                 round(rnd.uniform(0.75, 0.97), 2), final_risk),
            )

    conn.commit()
    total = days_back == days_back and (days_back + 1) * per_day
    print(f"Seeded {total} patient(s)/visit(s)/screening(s) across "
          f"{days_back + 1} day(s). Remove with: "
          f"python -m scripts.seed_dashboard_dev --purge")


if __name__ == "__main__":
    conn = get_connection()
    try:
        purge(conn) if "--purge" in sys.argv else seed(conn)
    finally:
        conn.close()