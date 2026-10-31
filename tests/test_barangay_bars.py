import re

from app.db import get_connection
from app.models import health_analytics_model as ham
from tests.conftest import active_session, add_user


def _pcts(counts):
    return [b["pct"] for b in ham.barangay_bars(counts)]


def _admin(app):
    client = app.test_client()
    uid = add_user(app, "bb-admin@example.com", role="medical_officer")
    active_session(client, uid, role="medical_officer")
    return client


def _barangay_html(html):
    start = html.index("Barangay List by At-Risk Count")
    return html[start:html.index("ROW 3", start)]


def _add(conn, code, barangay, risk, when="2026-02-01 08:00:00", deleted=False):
    bid = None
    if barangay:
        conn.execute("INSERT OR IGNORE INTO barangays (name) VALUES (?)", (barangay,))
        bid = conn.execute("SELECT id FROM barangays WHERE name = ? LIMIT 1", (barangay,)).fetchone()[0]
    pid = conn.execute(
        "INSERT INTO patients (patient_code, last_name, first_name, birthdate, sex, barangay_id, deleted_at) "
        "VALUES (?, 'Zed', 'Pat', '1990-01-01', 'Male', ?, ?)",
        (code, bid, "2026-01-01 00:00:00" if deleted else None),
    ).lastrowid
    _screen(conn, pid, risk, when)
    return pid


def _screen(conn, pid, risk, when):
    vid = conn.execute(
        "INSERT INTO visits (patient_id, visit_type, assessment_date) VALUES (?, 'intake', '2026-01-01')", (pid,)
    ).lastrowid
    conn.execute(
        "INSERT INTO lab_screenings (visit_id, fbs_mg_dl, test_datetime, final_risk_level) VALUES (?,?,?,?)",
        (vid, 120, when, risk),
    )


def test_proportional_pcts():
    counts = {"A": 574, "B": 556, "C": 418, "D": 416, "E": 391}
    assert _pcts(counts) == [100.0, 96.9, 72.8, 72.5, 68.1]


def test_all_equal_and_single():
    assert _pcts({"A": 5, "B": 5, "C": 5}) == [100.0] * 3
    assert _pcts({"A": 7}) == [100.0]


def test_empty_and_zero_max():
    assert ham.barangay_bars({}) == []
    assert _pcts({"A": 0, "B": 0}) == [0.0, 0.0]


def test_tiny_count_visible_and_limit_not_hardcoded():
    assert _pcts({"A": 1000, "B": 1}) == [100.0, 3.0]
    assert len(ham.barangay_bars({str(i): i + 1 for i in range(8)}, limit=3)) == 3


def test_ordering_ties_by_name():
    assert [b["name"] for b in ham.barangay_bars({"B": 2, "A": 2, "C": 3})] == ["C", "A", "B"]


def test_empty_db_shows_message_no_demo_names(app):
    html = _admin(app).get("/admin/dashboard").get_data(as_text=True)
    section = _barangay_html(html)
    assert "No screenings recorded yet." in section
    assert "Kanluran" not in section and "Market Area" not in section
    assert "/ 60" not in html


def test_rendered_widths_and_titles(app):
    with app.app_context():
        conn = get_connection()
        for i in range(4):
            _add(conn, f"BB-A{i}", "Alpha", "High")
        for i in range(2):
            _add(conn, f"BB-B{i}", "Beta", "Moderate")
        conn.commit()
        conn.close()
    section = _barangay_html(_admin(app).get("/admin/dashboard").get_data(as_text=True))
    widths = re.findall(r"width:([\d.]+)%", section)
    assert widths == ["100.0", "50.0"]
    assert 'title="Alpha: 4"' in section


def test_counts_patients_at_risk_and_sum_matches_card(app):
    with app.app_context():
        conn = get_connection()
        for i in range(7):
            _add(conn, f"BB-S{i}", f"Brgy{i}", "High" if i % 2 else "Moderate")
        _add(conn, "BB-LOW", "Brgy0", "Low")
        _add(conn, "BB-DEL", "Brgy0", "High", deleted=True)
        _add(conn, "BB-UNK", None, "High")
        # several screenings, latest is Low -> not at risk; earlier High must not count
        multi = _add(conn, "BB-MULTI", "Brgy1", "High", when="2026-01-01 08:00:00")
        _screen(conn, multi, "Low", "2026-03-01 08:00:00")
        # several screenings, latest at-risk -> counts once
        again = _add(conn, "BB-ONCE", "Brgy2", "High", when="2026-01-01 08:00:00")
        _screen(conn, again, "High", "2026-03-01 08:00:00")
        conn.commit()
        conn.close()
        snap = ham.get_current_risk_snapshot()
    by = snap["at_risk_by_barangay"]
    assert sum(by.values()) == snap["at_risk"]
    assert len(by) > 5
    assert by["Brgy0"] == 1          # deleted + Low excluded
    assert by["Brgy1"] == 1          # latest screening is Low -> only the seeded one
    assert by["Brgy2"] == 2          # BB-S2 + BB-ONCE, ONCE counted once
    assert by["Unknown"] == 1
    assert len(ham.barangay_bars(by)) == 5
