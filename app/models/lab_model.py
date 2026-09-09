"""
reads/writes to `lab_screenings`

"""
from app.models.db import get_connection


def classify_fbs_preliminary(fbs_mg_dl: float) -> dict:
    if fbs_mg_dl < 100:
        return {"level": "Low", "score": 20}
    if fbs_mg_dl < 126:
        return {"level": "Moderate", "score": 60}
    return {"level": "High", "score": 90}


def create_lab_screening(visit_id: int, data: dict, staff_id: int | None = None) -> int:
    prelim = classify_fbs_preliminary(data["fbs_mg_dl"])
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO lab_screenings (
                visit_id, fbs_mg_dl, test_method, glucometer_id, test_datetime,
                preliminary_risk_level, preliminary_score,
                final_risk_level, override_by_staff_id,
                fasted_ge_8h, identity_verified, glucometer_calibrated,
                capillary_sample_taken, consent_signed, result_recorded_within_5min,
                referral_action, follow_up_date, referred_to
            ) VALUES (?,?,?,?,?, ?,?, ?,?, ?,?,?,?,?,?, ?,?,?)
            ON CONFLICT(visit_id) DO UPDATE SET
                fbs_mg_dl = excluded.fbs_mg_dl,
                test_method = excluded.test_method,
                glucometer_id = excluded.glucometer_id,
                test_datetime = excluded.test_datetime,
                preliminary_risk_level = excluded.preliminary_risk_level,
                preliminary_score = excluded.preliminary_score,
                final_risk_level = excluded.final_risk_level,
                override_by_staff_id = excluded.override_by_staff_id,
                fasted_ge_8h = excluded.fasted_ge_8h,
                identity_verified = excluded.identity_verified,
                glucometer_calibrated = excluded.glucometer_calibrated,
                capillary_sample_taken = excluded.capillary_sample_taken,
                consent_signed = excluded.consent_signed,
                result_recorded_within_5min = excluded.result_recorded_within_5min,
                referral_action = excluded.referral_action,
                follow_up_date = excluded.follow_up_date,
                referred_to = excluded.referred_to
        """, (
            visit_id, data["fbs_mg_dl"], data.get("test_method", "Capillary (Fingerprick)"),
            data.get("glucometer_id"), data["test_datetime"],
            prelim["level"], prelim["score"],
            data.get("final_risk_level"), staff_id,
            int(bool(data.get("fasted_ge_8h"))), int(bool(data.get("identity_verified"))),
            int(bool(data.get("glucometer_calibrated"))), int(bool(data.get("capillary_sample_taken"))),
            int(bool(data.get("consent_signed"))), int(bool(data.get("result_recorded_within_5min"))),
            data.get("referral_action"), data.get("follow_up_date"), data.get("referred_to"),
        ))
        conn.commit()
        row = conn.execute("SELECT id FROM lab_screenings WHERE visit_id = ?", (visit_id,)).fetchone()
        return row["id"]
    finally:
        conn.close()


def get_lab_screening_for_visit(visit_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM lab_screenings WHERE visit_id = ?", (visit_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_model_prediction(visit_id: int, risk_level: str, confidence: float) -> None:
    conn = get_connection()
    conn.execute("""
        UPDATE lab_screenings
        SET model_predicted_risk_level = ?, model_confidence = ?
        WHERE visit_id = ?
    """, (risk_level, confidence, visit_id))
    conn.commit()
    conn.close()
