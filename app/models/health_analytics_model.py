"""
Read-only  
"""
from app.models.db import get_connection


def _base_query():
    return """
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        LEFT JOIN visits v ON v.id = (
            SELECT v2.id FROM visits v2 WHERE v2.patient_id = p.id ORDER BY v2.id DESC LIMIT 1
        )
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
        WHERE p.deleted_at IS NULL
    """


def get_fbs_distribution() -> dict:
    """Buckets FBS into clinical ranges: Normal (<100), Prediabetic (100-125), Diabetic (>=126)."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT
            CASE
                WHEN ls.fbs_mg_dl < 100 THEN 'Normal (<100)'
                WHEN ls.fbs_mg_dl < 126 THEN 'Prediabetic (100-125)'
                ELSE 'Diabetic (>=126)'
            END AS bucket,
            COUNT(*) AS n
        {_base_query()} AND ls.fbs_mg_dl IS NOT NULL
        GROUP BY bucket
    """).fetchall()
    conn.close()
    return {r["bucket"]: r["n"] for r in rows}


def get_risk_status_distribution() -> dict:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT COALESCE(ls.final_risk_level, ls.preliminary_risk_level, 'Pending') AS status, COUNT(*) AS n
        {_base_query()}
        GROUP BY status
    """).fetchall()
    conn.close()
    return {r["status"]: r["n"] for r in rows}


def get_age_distribution() -> dict:
    from datetime import date
    conn = get_connection()
    rows = conn.execute(f"SELECT p.birthdate {_base_query()}").fetchall()
    conn.close()
    buckets = {"<20": 0, "20-29": 0, "30-39": 0, "40-49": 0, "50-59": 0, "60+": 0}
    today = date.today()
    for r in rows:
        if not r["birthdate"]:
            continue
        b = date.fromisoformat(r["birthdate"])
        age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        if age < 20: buckets["<20"] += 1
        elif age < 30: buckets["20-29"] += 1
        elif age < 40: buckets["30-39"] += 1
        elif age < 50: buckets["40-49"] += 1
        elif age < 60: buckets["50-59"] += 1
        else: buckets["60+"] += 1
    return buckets


def get_sex_distribution() -> dict:
    conn = get_connection()
    rows = conn.execute(f"SELECT p.sex, COUNT(*) AS n {_base_query()} GROUP BY p.sex").fetchall()
    conn.close()
    return {r["sex"] or "Unspecified": r["n"] for r in rows}


def get_bmi_distribution() -> dict:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT v.obesity_class, COUNT(*) AS n {_base_query()} AND v.obesity_class IS NOT NULL
        GROUP BY v.obesity_class
    """).fetchall()
    conn.close()
    return {r["obesity_class"]: r["n"] for r in rows}


def get_bp_distribution() -> dict:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT
            CASE
                WHEN v.bp_systolic < 120 AND v.bp_diastolic < 80 THEN 'Normal'
                WHEN v.bp_systolic < 130 AND v.bp_diastolic < 80 THEN 'Elevated'
                WHEN v.bp_systolic < 140 OR v.bp_diastolic < 90 THEN 'Stage 1 Hypertension'
                ELSE 'Stage 2 Hypertension'
            END AS bucket,
            COUNT(*) AS n
        {_base_query()} AND v.bp_systolic IS NOT NULL AND v.bp_diastolic IS NOT NULL
        GROUP BY bucket
    """).fetchall()
    conn.close()
    return {r["bucket"]: r["n"] for r in rows}


def get_hypertension_history_distribution() -> dict:
    """PMH 'Hypertension' checkbox, counted per most-recent visit."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT
            CASE WHEN EXISTS (
                SELECT 1 FROM visit_conditions vc
                JOIN condition_catalog cc ON cc.id = vc.condition_id
                WHERE vc.visit_id = v.id AND cc.category = 'pmh' AND cc.code = 'Hypertension'
            ) THEN 'Yes' ELSE 'No' END AS has_htn,
            COUNT(*) AS n
        {_base_query()}
        GROUP BY has_htn
    """).fetchall()
    conn.close()
    return {r["has_htn"]: r["n"] for r in rows}


def get_waist_distribution() -> dict:
    """Asian-Pacific central obesity cutoffs: Male >90cm, Female >80cm = 'At Risk'."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT
            CASE
                WHEN (p.sex = 'Male' AND v.waist_cm > 90) OR (p.sex = 'Female' AND v.waist_cm > 80)
                THEN 'At Risk' ELSE 'Normal'
            END AS bucket,
            COUNT(*) AS n
        {_base_query()} AND v.waist_cm IS NOT NULL
        GROUP BY bucket
    """).fetchall()
    conn.close()
    return {r["bucket"]: r["n"] for r in rows}


def get_smoking_distribution() -> dict:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT v.smoking_status, COUNT(*) AS n {_base_query()} AND v.smoking_status IS NOT NULL
        GROUP BY v.smoking_status
    """).fetchall()
    conn.close()
    return {r["smoking_status"]: r["n"] for r in rows}


def get_family_history_distribution() -> dict:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT
            CASE WHEN EXISTS (
                SELECT 1 FROM visit_conditions vc
                JOIN condition_catalog cc ON cc.id = vc.condition_id
                WHERE vc.visit_id = v.id AND cc.category = 'family_history' AND cc.code = 'Diabetes Mellitus'
            ) THEN 'Yes' ELSE 'No' END AS has_fh,
            COUNT(*) AS n
        {_base_query()}
        GROUP BY has_fh
    """).fetchall()
    conn.close()
    return {r["has_fh"]: r["n"] for r in rows}


def get_barangay_risk_matrix() -> dict:
    """Returns {barangay: {'Low': n, 'Moderate': n, 'High': n}} for all barangays with data."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT b.name AS barangay, COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk, COUNT(*) AS n
        {_base_query()} AND b.name IS NOT NULL
        GROUP BY b.name, risk
    """).fetchall()
    conn.close()
    result = {}
    for r in rows:
        result.setdefault(r["barangay"], {"Low": 0, "Moderate": 0, "High": 0})
        if r["risk"] in result[r["barangay"]]:
            result[r["barangay"]][r["risk"]] = r["n"]
    return result


def get_risk_by_sex() -> dict:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT p.sex, COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk, COUNT(*) AS n
        {_base_query()}
        GROUP BY p.sex, risk
    """).fetchall()
    conn.close()
    result = {}
    for r in rows:
        result.setdefault(r["sex"] or "Unspecified", {"Low": 0, "Moderate": 0, "High": 0})
        if r["risk"] in result[r["sex"] or "Unspecified"]:
            result[r["sex"] or "Unspecified"][r["risk"]] = r["n"]
    return result


def get_risk_by_age() -> dict:
    from datetime import date
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT p.birthdate, COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk {_base_query()}
    """).fetchall()
    conn.close()
    buckets = {"<20": {"Low": 0, "Moderate": 0, "High": 0}, "20-29": {"Low": 0, "Moderate": 0, "High": 0},
               "30-39": {"Low": 0, "Moderate": 0, "High": 0}, "40-49": {"Low": 0, "Moderate": 0, "High": 0},
               "50-59": {"Low": 0, "Moderate": 0, "High": 0}, "60+": {"Low": 0, "Moderate": 0, "High": 0}}
    today = date.today()
    for r in rows:
        if not r["birthdate"] or r["risk"] not in ("Low", "Moderate", "High"):
            continue
        b = date.fromisoformat(r["birthdate"])
        age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        if age < 20: key = "<20"
        elif age < 30: key = "20-29"
        elif age < 40: key = "30-39"
        elif age < 50: key = "40-49"
        elif age < 60: key = "50-59"
        else: key = "60+"
        buckets[key][r["risk"]] += 1
    return buckets

def get_dashboard_summary() -> dict:
    """Top stat cards: total screened, at-risk, high-risk, avg FBS."""
    conn = get_connection()
    row = conn.execute(f"""
        SELECT
            COUNT(*) AS total_screened,
            SUM(CASE WHEN COALESCE(ls.final_risk_level, ls.preliminary_risk_level) IN ('Moderate','High') THEN 1 ELSE 0 END) AS at_risk,
            SUM(CASE WHEN COALESCE(ls.final_risk_level, ls.preliminary_risk_level) = 'High' THEN 1 ELSE 0 END) AS high_risk,
            AVG(ls.fbs_mg_dl) AS avg_fbs
        {_base_query()} AND ls.fbs_mg_dl IS NOT NULL
    """).fetchone()
    conn.close()
    return {
        "total_screened": row["total_screened"] or 0,
        "at_risk": row["at_risk"] or 0,
        "high_risk": row["high_risk"] or 0,
        "avg_fbs": round(row["avg_fbs"], 1) if row["avg_fbs"] else 0,
    }


def get_screening_volume_timeline(days: int = 14) -> dict:
    """Screenings per day, last N days -- feeds the line chart."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT DATE(ls.test_datetime) AS day, COUNT(*) AS n
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        WHERE p.deleted_at IS NULL AND ls.test_datetime IS NOT NULL
        GROUP BY day
        ORDER BY day DESC
        LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    data = {r["day"]: r["n"] for r in rows if r["day"] is not None}
    return dict(sorted(data.items()))


def get_top_barangays(limit: int = 8) -> dict:
    """Top N barangays by total screening volume -- feeds the bar chart."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT b.name AS barangay, COUNT(*) AS n
        {_base_query()} AND b.name IS NOT NULL
        GROUP BY b.name
        ORDER BY n DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return {r["barangay"]: r["n"] for r in rows}


def get_recent_registries(limit: int = 5) -> list[dict]:
    """Backs the 'Recent Patient Registries' table."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT p.patient_code, p.first_name, p.last_name, p.birthdate, p.sex,
               ls.fbs_mg_dl, COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS risk,
               v.assessment_date
        {_base_query()}
        ORDER BY v.id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    from datetime import date
    result = []
    for r in rows:
        d = dict(r)
        if d["birthdate"]:
            b = date.fromisoformat(d["birthdate"])
            today = date.today()
            d["age"] = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        else:
            d["age"] = None
        result.append(d)
    return result