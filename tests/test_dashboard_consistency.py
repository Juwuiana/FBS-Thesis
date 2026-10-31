import json
import re

import pytest

from app.db import get_connection
from app.models import health_analytics_model as ham
from tests.conftest import active_session, add_user


def _patient(conn, code, first="Pat", deleted=False):
    return conn.execute(
        "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex, deleted_at) "
        "VALUES (?, 'Zed', ?, '1990-01-01', 'Male', ?)",
        (code, first, "2026-01-01 00:00:00" if deleted else None),
    ).lastrowid


def _screening(conn, pid, fbs, when, final=None, prelim=None, model=None):
    vid = conn.execute(
        "INSERT INTO visits (patient_id, visit_type, assessment_date) VALUES (?, 'intake', '2026-01-01')", (pid,)
    ).lastrowid
    conn.execute(
        "INSERT INTO lab_screenings (visit_id, fbs_mg_dl, test_datetime, final_risk_level, "
        "preliminary_risk_level, model_predicted_risk_level) VALUES (?,?,?,?,?,?)",
        (vid, fbs, when, final, prelim, model),
    )


@pytest.fixture
def seeded(app):
    with app.app_context():
        conn = get_connection()
        a = _patient(conn, "DC-A", "Normal")
        _screening(conn, a, 90, "2026-02-01 08:00:00", final="Low")
        b = _patient(conn, "DC-B", "Deleted", deleted=True)
        _screening(conn, b, 150, "2026-02-01 08:00:00", final="High")
        # Later visit id has the EARLIER date: latest-by-date (High) must win.
        c = _patient(conn, "DC-C", "TwoScreens")
        _screening(conn, c, 140, "2026-03-01 08:00:00", final="High")
        _screening(conn, c, 85, "2026-01-01 08:00:00", final="Low")
        # fbs_mg_dl is NOT NULL in the schema, so a NULL-FBS screening can't be seeded;
        # the snapshot's IS NOT NULL filter is only a safeguard.
        e = _patient(conn, "DC-E", "ModelOnly")
        _screening(conn, e, 110, "2026-02-01 08:00:00", model="Pre-Diabetic")
        conn.commit()
        conn.close()
    return app


def _admin(app):
    client = app.test_client()
    uid = add_user(app, "dc-admin@example.com", role="medical_officer")
    active_session(client, uid, role="medical_officer")
    return client


def _nurse(app):
    client = app.test_client()
    uid = add_user(app, "dc-nurse@example.com", role="health_worker")
    active_session(client, uid, role="health_worker")
    return client


def _cards(html):
    return [int(x) for x in re.findall(r'class="stat-value[^"]*"[^>]*>\s*(\d+)', html)[:3]]


def _donut(html):
    return json.loads(re.search(r"riskData:\s*(\[[^\]]*\])", html).group(1))


def test_snapshot_rules(seeded):
    with seeded.app_context():
        s = ham.get_current_risk_snapshot()
    assert s["total_screened"] == 3  # A, C, E (B is in the Recycle Bin)
    # C = High by date (not by visit id). E only has a model label (Normal/Pre-Diabetic/
    # Diabetic), which is not a Low/Moderate/High level, so it is reported as unclassified.
    assert s["risk_counts"] == {"Low": 1, "Moderate": 0, "High": 1}
    assert s["unclassified"] == 1
    assert s["at_risk"] == 1 and s["high_risk"] == 1


def test_invariants(seeded):
    with seeded.app_context():
        s = ham.get_current_risk_snapshot()
    c = s["risk_counts"]
    assert sum(c.values()) == s["risk_total"]
    assert s["at_risk"] == c["Moderate"] + c["High"]
    assert s["high_risk"] == c["High"]
    assert s["total_screened"] == s["risk_total"] + s["unclassified"]
    assert round(sum(s["risk_pct"].values())) == 100


def test_admin_and_nurse_pages_match(seeded):
    admin_html = _admin(seeded).get("/admin/dashboard").get_data(as_text=True)
    nurse_html = _nurse(seeded).get("/nurse/dashboard").get_data(as_text=True)
    assert _cards(admin_html) == _cards(nurse_html) == [3, 1, 1]
    assert _donut(admin_html) == _donut(nurse_html) == [50.0, 0.0, 50.0]
    counts = lambda h: json.loads(re.search(r"riskCounts:\s*(\[[^\]]*\])", h).group(1))
    assert counts(admin_html) == counts(nurse_html) == [1, 0, 1]


def test_admin_has_no_fake_numbers(seeded):
    html = _admin(seeded).get("/admin/dashboard").get_data(as_text=True)
    assert "+1.2% vs last week" not in html
    assert "1,392" not in html
    assert "At Risk (Moderate + High)" in html


def test_deleted_patient_not_in_recent_screenings(seeded):
    html = _admin(seeded).get("/admin/dashboard").get_data(as_text=True)
    assert "Deleted Zed" not in html
    assert "Normal Zed" in html


def test_dashboard_changes_runs(seeded):
    with seeded.app_context():
        assert isinstance(ham.get_dashboard_changes(), dict)


def test_as_of_uses_same_definition(seeded):
    with seeded.app_context():
        # On 2026-02-15 patient C's latest screening is the Jan one (Low).
        past = ham._summary_as_of("2026-02-15")
        assert past["total_screened"] == 3 and past["high_risk"] == 0
        assert ham._summary_as_of("2025-01-01")["total_screened"] == 0
