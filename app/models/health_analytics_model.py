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
        SELECT COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level, 'Pending') AS status, COUNT(*) AS n
        {_base_query()}
        GROUP BY COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level, 'Pending')
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
                WHEN v.bp_systolic < 140 AND v.bp_diastolic < 90 THEN 'Stage 1 Hypertension'
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
        SELECT b.name AS barangay, COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) AS risk, COUNT(*) AS n
        {_base_query()} AND b.name IS NOT NULL AND LOWER(b.name) NOT LIKE 'select %'
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
        SELECT p.sex, COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) AS risk, COUNT(*) AS n
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
        SELECT p.birthdate, COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) AS risk {_base_query()}
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
            SUM(CASE WHEN COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) IN ('Moderate','High') THEN 1 ELSE 0 END) AS at_risk,
            SUM(CASE WHEN COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) = 'High' THEN 1 ELSE 0 END) AS high_risk,
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


def _summary_as_of(cutoff_iso: str) -> dict:
    """
    Same numbers as get_dashboard_summary(), but each patient's state as it
    stood on `cutoff_iso` (YYYY-MM-DD): their latest visit whose lab test
    happened on or before that day. Used to compare "now" against a past date.
    """
    conn = get_connection()
    row = conn.execute(f"""
        SELECT
            COUNT(*) AS total_screened,
            SUM(CASE WHEN {_RISK} IN ('Moderate','High') THEN 1 ELSE 0 END) AS at_risk,
            SUM(CASE WHEN {_RISK} = 'High' THEN 1 ELSE 0 END) AS high_risk,
            AVG(ls.fbs_mg_dl) AS avg_fbs
        FROM patients p
        LEFT JOIN visits v ON v.id = (
            SELECT v2.id FROM visits v2
            JOIN lab_screenings l2 ON l2.visit_id = v2.id
            WHERE v2.patient_id = p.id AND DATE(l2.test_datetime) <= DATE(?)
            ORDER BY v2.id DESC LIMIT 1
        )
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
        WHERE p.deleted_at IS NULL AND ls.fbs_mg_dl IS NOT NULL
    """, (cutoff_iso,)).fetchone()
    conn.close()
    return {
        "total_screened": row["total_screened"] or 0,
        "at_risk": row["at_risk"] or 0,
        "high_risk": row["high_risk"] or 0,
        "avg_fbs": round(row["avg_fbs"], 1) if row["avg_fbs"] else 0,
    }


def get_dashboard_changes(days: int = 7) -> dict:
    """
    Change in each top stat card since `days` days ago, for the up/down arrows:
    {"at_risk": {"dir": "up"|"down"|"flat", "diff": 5}, ...}
    Returns {} when nothing had been screened yet back then (no baseline to
    compare against, so no arrow is better than a misleading one).
    """
    from datetime import date, timedelta
    today = date.today()
    now = _summary_as_of(today.isoformat())
    before = _summary_as_of((today - timedelta(days=days)).isoformat())
    if not before["total_screened"]:
        return {}
    changes = {}
    for key in ("total_screened", "at_risk", "high_risk", "avg_fbs"):
        diff = round(now[key] - before[key], 1)
        if key != "avg_fbs":
            diff = int(diff)
        changes[key] = {
            "dir": "up" if diff > 0 else ("down" if diff < 0 else "flat"),
            "diff": abs(diff),
        }
    return changes


def get_actual_vs_predicted(months: int = 6) -> dict:
    """
    Actual vs model-predicted risk, for the nurse dashboard.
      actual    = final_risk_level (nurse-confirmed) if set, else the FBS-based
                  preliminary_risk_level
      predicted = model_predicted_risk_level
    Only screenings that have BOTH are counted. Returns:
      monthly: [{month, total, agree, actual_at_risk, predicted_at_risk,
                 actual_high, predicted_high}, ...] (last `months` months, oldest first)
      matrix:  {actual: {predicted: n}} over all time
      total, agree, agree_pct, high_total, high_caught
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT STRFTIME('%Y-%m', ls.test_datetime) AS month,
               COALESCE(ls.final_risk_level, ls.preliminary_risk_level) AS actual,
               ls.model_predicted_risk_level AS predicted,
               COUNT(*) AS n
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        WHERE p.deleted_at IS NULL AND ls.test_datetime IS NOT NULL
          AND ls.model_predicted_risk_level IN ('Low','Moderate','High')
          AND COALESCE(ls.final_risk_level, ls.preliminary_risk_level) IN ('Low','Moderate','High')
        GROUP BY month, actual, predicted
    """).fetchall()
    conn.close()

    levels = ("Low", "Moderate", "High")
    matrix = {a: {p: 0 for p in levels} for a in levels}
    by_month = {}
    for r in rows:
        a, p, n, m = r["actual"], r["predicted"], r["n"], r["month"]
        matrix[a][p] += n
        if not m:
            continue
        d = by_month.setdefault(m, {"month": m, "total": 0, "agree": 0, "actual_at_risk": 0,
                                    "predicted_at_risk": 0, "actual_high": 0, "predicted_high": 0})
        d["total"] += n
        if a == p:
            d["agree"] += n
        if a != "Low":
            d["actual_at_risk"] += n
        if p != "Low":
            d["predicted_at_risk"] += n
        if a == "High":
            d["actual_high"] += n
        if p == "High":
            d["predicted_high"] += n

    total = sum(sum(row.values()) for row in matrix.values())
    agree = sum(matrix[l][l] for l in levels)
    return {
        "monthly": [by_month[k] for k in sorted(by_month)][-months:],
        "matrix": matrix,
        "total": total,
        "agree": agree,
        "agree_pct": round(agree / total * 100) if total else 0,
        "high_total": sum(matrix["High"].values()),
        "high_caught": matrix["High"]["High"],
    }


_VOLUME_LEVELS = ("year", "month", "week")
TIMELINE_START_YEAR = 2018  # year axis always begins here, even if older years have no data


def _parse_year(year) -> int:
    try:
        y = int(year)
    except (TypeError, ValueError):
        raise ValueError("year must be a 4-digit number")
    if not 2000 <= y <= 2100:
        raise ValueError("year out of range")
    return y


def _parse_month(month) -> int:
    try:
        m = int(month)
    except (TypeError, ValueError):
        raise ValueError("month must be 1-12")
    if not 1 <= m <= 12:
        raise ValueError("month must be 1-12")
    return m


# Screening date = the visit's assessment_date (what imported historical CSV
# rows carry), falling back to lab_screenings.test_datetime. Accepts ISO
# (2018-01-01) or dd/mm/yyyy (01/01/2018).
_DAY_EXPR = """COALESCE(
    CASE
        WHEN v.assessment_date LIKE '____-__-__%'
            THEN SUBSTR(v.assessment_date, 1, 10)
        WHEN v.assessment_date LIKE '__/__/____'
            THEN SUBSTR(v.assessment_date, 7, 4) || '-' ||
                 SUBSTR(v.assessment_date, 4, 2) || '-' ||
                 SUBSTR(v.assessment_date, 1, 2)
    END,
    DATE(ls.test_datetime)
)"""


def _screening_records() -> list[tuple[str, float | None]]:
    """[(ISO day, fbs_mg_dl or None)] for every screening of a non-deleted patient."""
    conn = get_connection()
    try:
        rows = conn.execute(f"""
            SELECT {_DAY_EXPR} AS day, ls.fbs_mg_dl AS fbs
            FROM lab_screenings ls
            JOIN visits v ON v.id = ls.visit_id
            JOIN patients p ON p.id = v.patient_id
            WHERE p.deleted_at IS NULL
        """).fetchall()
    finally:
        conn.close()
    return [(r["day"], r["fbs"]) for r in rows if r["day"] and len(r["day"]) == 10]


def _screening_days() -> list[str]:
    return [day for day, _ in _screening_records()]


FBS_CLASSES = ("Normal", "Prediabetic", "Diabetic")


def _fbs_class(fbs) -> str | None:
    """Same clinical cut-offs as the dashboard legend: <100, 100-125, >=126."""
    if fbs is None:
        return None
    return "Normal" if fbs < 100 else ("Prediabetic" if fbs < 126 else "Diabetic")


def get_screening_trend(level: str = "year", year=None, month=None,
                        start_year: int = TIMELINE_START_YEAR) -> dict:
    """
    Screenings split into three lines (Normal / Prediabetic / Diabetic by FBS),
    for the drill-down chart on the Health Results page:
      level="year"  -> one point per year, start_year .. current year
      level="month" -> Jan..Dec of `year`                      (labels YYYY-MM)
      level="day"   -> every date of `year`/`month`            (labels YYYY-MM-DD)
    Gaps are zero-filled so each line is continuous. Screenings with no FBS
    value can't be classed, so they are left out (reported as `unclassified`).
    Returns {"level", "labels": [...], "series": {"Normal": [...], ...},
             "unclassified": n}. Raises ValueError on bad input.
    """
    import calendar
    from collections import Counter
    from datetime import date

    if level not in ("year", "month", "day"):
        raise ValueError("level must be year, month or day")

    counts = {c: Counter() for c in FBS_CLASSES}
    unclassified = 0

    if level == "year":
        key = lambda d: int(d[:4]) if d[:4].isdigit() else None
        in_scope = lambda d: True
    else:
        y = _parse_year(year)
        if level == "month":
            key = lambda d: int(d[5:7]) if d[5:7].isdigit() else None
            in_scope = lambda d: d[:4] == f"{y:04d}"
        else:
            m = _parse_month(month)
            prefix = f"{y:04d}-{m:02d}-"
            key = lambda d: int(d[8:10]) if d[8:10].isdigit() else None
            in_scope = lambda d: d.startswith(prefix)

    for day, fbs in _screening_records():
        if not in_scope(day):
            continue
        k = key(day)
        if k is None:
            continue
        cls = _fbs_class(fbs)
        if cls is None:
            unclassified += 1
            continue
        counts[cls][k] += 1

    if level == "year":
        seen = [k for c in counts.values() for k in c]
        keys = list(range(min([start_year, *seen]), max([date.today().year, *seen]) + 1))
        labels = [str(k) for k in keys]
    elif level == "month":
        keys = list(range(1, 13))
        labels = [f"{y:04d}-{k:02d}" for k in keys]
    else:
        keys = list(range(1, calendar.monthrange(y, m)[1] + 1))
        labels = [f"{y:04d}-{m:02d}-{k:02d}" for k in keys]

    return {
        "level": level,
        "labels": labels,
        "series": {c: [counts[c].get(k, 0) for k in keys] for c in FBS_CLASSES},
        "unclassified": unclassified,
    }


def get_screening_volume_timeline(level: str = "year", year=None, month=None,
                                  start_year: int = TIMELINE_START_YEAR) -> dict:
    """
    Screening counts for the drill-down line chart (insertion-ordered dict,
    gaps zero-filled so the line is continuous):
      level="year"  -> {"2018": n, ... "2026": n}           start_year .. current year
                       (extends earlier/later if data falls outside that range)
      level="month" -> {"2026-01": n, ... "2026-12": n}     needs year
      level="week"  -> {"Wk 1 (Sep 1-7)": n, ...}           needs year + month
    Weeks are fixed 7-day blocks (1-7, 8-14, 15-21, 22-28, 29-end) so they
    always line up with the calendar month the nurse drilled into.
    Raises ValueError on a bad level/year/month (route turns it into a 400).
    """
    import calendar
    from collections import Counter
    from datetime import date

    if level not in _VOLUME_LEVELS:
        raise ValueError("level must be year, month or week")

    days = _screening_days()

    if level == "year":
        counts = Counter(int(d[:4]) for d in days if d[:4].isdigit())
        first = min([start_year, *counts])
        last = max([date.today().year, *counts])
        return {str(y): counts.get(y, 0) for y in range(first, last + 1)}

    y = _parse_year(year)

    if level == "month":
        counts = Counter(int(d[5:7]) for d in days if d[:4] == f"{y:04d}" and d[5:7].isdigit())
        return {f"{y:04d}-{m:02d}": counts.get(m, 0) for m in range(1, 13)}

    m = _parse_month(month)
    prefix = f"{y:04d}-{m:02d}-"
    days_in_month = calendar.monthrange(y, m)[1]
    n_weeks = (days_in_month + 6) // 7
    buckets = [0] * n_weeks
    for d in days:
        if d.startswith(prefix) and d[8:10].isdigit():
            day = int(d[8:10])
            if 1 <= day <= days_in_month:
                buckets[(day - 1) // 7] += 1
    out = {}
    for i in range(n_weeks):
        lo, hi = i * 7 + 1, min((i + 1) * 7, days_in_month)
        out[f"Wk {i + 1} ({calendar.month_abbr[m]} {lo}-{hi})"] = buckets[i]
    return out


def get_top_barangays(limit: int = 8) -> dict:
    """Top N barangays by total screening volume -- feeds the bar chart."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT b.name AS barangay, COUNT(*) AS n
        {_base_query()} AND b.name IS NOT NULL AND LOWER(b.name) NOT LIKE 'select %'
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
               ls.fbs_mg_dl, COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level) AS risk,
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


# ---------------------------------------------------------------------------
# Health Results page: nurse action items
# ---------------------------------------------------------------------------
_RISK = "COALESCE(ls.final_risk_level, ls.preliminary_risk_level, ls.model_predicted_risk_level)"
# A referral counts as recorded if EITHER the action or the destination was filled in.
_HAS_REFERRAL = "(COALESCE(TRIM(ls.referral_action), '') != '' OR COALESCE(TRIM(ls.referred_to), '') != '')"


def _age_from(birthdate):
    from datetime import date
    if not birthdate:
        return None
    b = date.fromisoformat(birthdate)
    today = date.today()
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


def get_followup_summary() -> dict:
    """Action cards: Moderate/High with no referral logged, follow-up dates already
    past (latest visit only, so a newer visit clears it), and visits (drafts included) with no FBS yet."""
    conn = get_connection()
    row = conn.execute(f"""
        SELECT
            SUM(CASE WHEN {_RISK} IN ('Moderate','High')
                      AND NOT {_HAS_REFERRAL} THEN 1 ELSE 0 END) AS no_action,
            SUM(CASE WHEN {_RISK} IN ('Moderate','High')
                      AND ls.follow_up_date IS NOT NULL
                      AND ls.follow_up_date < DATE('now') THEN 1 ELSE 0 END) AS overdue,
            SUM(CASE WHEN v.id IS NOT NULL AND ls.fbs_mg_dl IS NULL THEN 1 ELSE 0 END) AS awaiting_lab
        {_base_query()}
    """).fetchone()
    conn.close()
    return {k: row[k] or 0 for k in ("no_action", "overdue", "awaiting_lab")}


def get_followup_worklist(limit: int = 100) -> list[dict]:
    """Moderate/High patients (latest visit), most urgent first:
    High before Moderate, then overdue, then no referral, then highest FBS."""
    from datetime import date
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT p.patient_code, p.first_name, p.last_name, p.birthdate, p.sex,
               b.name AS barangay, v.assessment_date, ls.fbs_mg_dl,
               {_RISK} AS risk, ls.referral_action, ls.referred_to, ls.follow_up_date
        {_base_query()} AND {_RISK} IN ('Moderate','High')
    """).fetchall()
    conn.close()

    today = date.today().isoformat()
    result = []
    for r in rows:
        d = dict(r)
        d["age"] = _age_from(d["birthdate"])
        action = (d["referral_action"] or "").strip() or ("Referred" if (d["referred_to"] or "").strip() else "")
        if d["follow_up_date"] and d["follow_up_date"][:10] < today:
            d["status_key"], d["status"] = "overdue", "Follow-up overdue"
        elif not action:
            d["status_key"], d["status"] = "none", "No referral recorded"
        else:
            d["status_key"], d["status"] = "ok", action
        result.append(d)

    order = {"overdue": 0, "none": 1, "ok": 2}
    result.sort(key=lambda d: (d["risk"] != "High", order[d["status_key"]], -(d["fbs_mg_dl"] or 0)))
    return result[:limit]


def get_monthly_risk_trend(months: int = 6) -> dict:
    """{'2026-09': {'Low': n, 'Moderate': n, 'High': n}} -- every screening, not just latest per patient."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT STRFTIME('%Y-%m', ls.test_datetime) AS month, {_RISK} AS risk, COUNT(*) AS n
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        WHERE p.deleted_at IS NULL AND ls.test_datetime IS NOT NULL
        GROUP BY month, risk
    """).fetchall()
    conn.close()
    data = {}
    for r in rows:
        if r["month"] and r["risk"] in ("Low", "Moderate", "High"):
            data.setdefault(r["month"], {"Low": 0, "Moderate": 0, "High": 0})[r["risk"]] = r["n"]
    return dict(sorted(data.items())[-months:])


# ---------------------------------------------------------------------------
# Health Results page: referral progress, quality checks, logs, red flags
# ---------------------------------------------------------------------------
def _pct(n, total):
    return round((n or 0) / total * 100) if total else 0


def _tone(pct):
    return "good" if pct >= 90 else ("warn" if pct >= 70 else "bad")


def get_barangay_summary() -> list[dict]:
    """One row per barangay for the heat table + CSV, highest % High first.
    heat_* are 0-0.6 alpha values scaled to the column max."""
    rows = []
    for name, c in get_barangay_risk_matrix().items():
        total = c["Low"] + c["Moderate"] + c["High"]
        if not total:
            continue
        rows.append({
            "barangay": name, "total": total,
            "low": c["Low"], "moderate": c["Moderate"], "high": c["High"],
            "pct_high": _pct(c["High"], total),
            "pct_at_risk": _pct(c["Moderate"] + c["High"], total),
        })
    max_high = max((r["pct_high"] for r in rows), default=0)
    max_risk = max((r["pct_at_risk"] for r in rows), default=0)
    for r in rows:
        r["heat_high"] = round(r["pct_high"] / max_high * 0.6, 2) if max_high else 0
        r["heat_risk"] = round(r["pct_at_risk"] / max_risk * 0.6, 2) if max_risk else 0
    rows.sort(key=lambda r: (-r["pct_high"], -r["total"]))
    return rows


def get_referral_funnel() -> dict:
    """Moderate/High patients (latest visit): referral logged, follow-up date set, overdue."""
    conn = get_connection()
    row = conn.execute(f"""
        SELECT
            SUM(CASE WHEN {_RISK} IN ('Moderate','High') THEN 1 ELSE 0 END) AS at_risk,
            SUM(CASE WHEN {_RISK} IN ('Moderate','High')
                      AND {_HAS_REFERRAL} THEN 1 ELSE 0 END) AS referred,
            SUM(CASE WHEN {_RISK} IN ('Moderate','High')
                      AND COALESCE(TRIM(ls.follow_up_date), '') != '' THEN 1 ELSE 0 END) AS scheduled,
            SUM(CASE WHEN {_RISK} IN ('Moderate','High')
                      AND ls.follow_up_date IS NOT NULL
                      AND ls.follow_up_date < DATE('now') THEN 1 ELSE 0 END) AS overdue
        {_base_query()}
    """).fetchone()
    dest = conn.execute(f"""
        SELECT TRIM(ls.referred_to) AS name, COUNT(*) AS n
        {_base_query()} AND {_RISK} IN ('Moderate','High') AND COALESCE(TRIM(ls.referred_to), '') != ''
        GROUP BY TRIM(ls.referred_to) ORDER BY n DESC LIMIT 5
    """).fetchall()
    conn.close()
    at_risk = row["at_risk"] or 0
    steps = []
    for label, key in (("Referral recorded", "referred"), ("Follow-up date set", "scheduled")):
        n = row[key] or 0
        p = _pct(n, at_risk)
        steps.append({"label": label, "n": n, "pct": p, "tone": _tone(p)})
    n = row["overdue"] or 0
    steps.append({"label": "Follow-up overdue", "n": n, "pct": _pct(n, at_risk), "tone": "bad" if n else "good"})
    return {"at_risk": at_risk, "steps": steps, "destinations": [dict(d) for d in dest]}


def get_screening_quality() -> dict:
    """Checklist compliance across all screenings + measurement completeness on latest visits."""
    conn = get_connection()
    c = conn.execute(f"""
        SELECT COUNT(*) AS total,
            SUM(COALESCE(ls.fasted_ge_8h, 0)) AS fasted,
            SUM(COALESCE(ls.identity_verified, 0)) AS identity,
            SUM(COALESCE(ls.glucometer_calibrated, 0)) AS calibrated,
            SUM(COALESCE(ls.capillary_sample_taken, 0)) AS sample,
            SUM(COALESCE(ls.consent_signed, 0)) AS consent,
            SUM(COALESCE(ls.result_recorded_within_5min, 0)) AS within5,
            SUM(CASE WHEN COALESCE(ls.fasted_ge_8h, 0) = 0
                      AND {_RISK} IN ('Moderate','High') THEN 1 ELSE 0 END) AS repeat_n
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        WHERE p.deleted_at IS NULL
    """).fetchone()
    m = conn.execute(f"""
        SELECT COUNT(*) AS total,
            SUM(CASE WHEN v.waist_cm IS NOT NULL THEN 1 ELSE 0 END) AS waist,
            SUM(CASE WHEN v.bp_systolic IS NOT NULL AND v.bp_diastolic IS NOT NULL THEN 1 ELSE 0 END) AS bp,
            SUM(CASE WHEN v.bmi IS NOT NULL THEN 1 ELSE 0 END) AS bmi,
            SUM(CASE WHEN v.smoking_status IS NOT NULL THEN 1 ELSE 0 END) AS smoking
        {_base_query()} AND v.id IS NOT NULL
    """).fetchone()
    conn.close()

    def rows(src, total, spec):
        out = []
        for label, key in spec:
            p = _pct(src[key], total)
            out.append({"label": label, "pct": p, "tone": _tone(p)})
        return out

    return {
        "total": c["total"] or 0,
        "repeat_n": c["repeat_n"] or 0,
        "checks": rows(c, c["total"], [
            ("Fasted at least 8 hours", "fasted"), ("Patient identity verified", "identity"),
            ("Glucometer calibrated", "calibrated"), ("Capillary sample taken", "sample"),
            ("Consent signed", "consent"), ("Result recorded within 5 minutes", "within5"),
        ]),
        "fields_total": m["total"] or 0,
        "fields": rows(m, m["total"], [
            ("Waist circumference", "waist"), ("Blood pressure", "bp"),
            ("BMI", "bmi"), ("Smoking status", "smoking"),
        ]),
    }


def get_daily_log(days: int = 14) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT DATE(ls.test_datetime) AS day, COUNT(*) AS screened,
            SUM(CASE WHEN {_RISK} = 'Low' THEN 1 ELSE 0 END) AS low,
            SUM(CASE WHEN {_RISK} = 'Moderate' THEN 1 ELSE 0 END) AS moderate,
            SUM(CASE WHEN {_RISK} = 'High' THEN 1 ELSE 0 END) AS high,
            SUM(CASE WHEN COALESCE(ls.fasted_ge_8h, 0) = 0 THEN 1 ELSE 0 END) AS not_fasted
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        WHERE p.deleted_at IS NULL AND ls.test_datetime IS NOT NULL
          AND DATE(ls.test_datetime) >= DATE('now', ?)
        GROUP BY day ORDER BY day DESC
    """, (f"-{int(days)} days",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_nurse_activity(days: int = 30) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT COALESCE(u.first_name || ' ' || u.last_name, 'Imported / unassigned') AS nurse,
               COUNT(*) AS screened,
               SUM(CASE WHEN {_RISK} = 'High' THEN 1 ELSE 0 END) AS high
        FROM lab_screenings ls
        JOIN visits v ON v.id = ls.visit_id
        JOIN patients p ON p.id = v.patient_id
        LEFT JOIN users u ON u.id = v.recorded_by_staff_id
        WHERE p.deleted_at IS NULL AND ls.test_datetime IS NOT NULL
          AND DATE(ls.test_datetime) >= DATE('now', ?)
        GROUP BY v.recorded_by_staff_id ORDER BY screened DESC
    """, (f"-{int(days)} days",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_red_flags(limit: int = 20) -> list[dict]:
    """Patients whose most recent visit *that has the CVD questionnaire* answered yes to
    severe chest pain (30+ min) or stroke/TIA symptoms. Using the latest visit that has
    answers (not just the latest visit) keeps a flag from vanishing when a follow-up visit
    is saved without the questionnaire. CSV-imported visits have no CVD answers."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT p.patient_code, p.first_name, p.last_name, b.name AS barangay,
               v.assessment_date, ls.fbs_mg_dl, {_RISK} AS risk,
               cr.q7_severe_pain_30min_plus AS q7, cr.q8_tia_stroke_symptoms AS q8
        FROM patients p
        LEFT JOIN barangays b ON b.id = p.barangay_id
        JOIN visits v ON v.id = (
            SELECT v2.id FROM visits v2
            JOIN cvd_responses c2 ON c2.visit_id = v2.id
            WHERE v2.patient_id = p.id ORDER BY v2.id DESC LIMIT 1
        )
        JOIN cvd_responses cr ON cr.visit_id = v.id
        LEFT JOIN lab_screenings ls ON ls.visit_id = v.id
        WHERE p.deleted_at IS NULL
          AND (cr.q7_severe_pain_30min_plus = 1 OR cr.q8_tia_stroke_symptoms = 1)
        ORDER BY (COALESCE({_RISK}, '') = 'High') DESC, v.assessment_date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["flags"] = (["Severe chest pain"] if d["q7"] else []) + (["Stroke / TIA symptoms"] if d["q8"] else [])
        result.append(d)
    return result