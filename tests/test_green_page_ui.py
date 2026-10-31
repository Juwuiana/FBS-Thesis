from tests.conftest import active_session, add_user

TITLES = [
    "Energy &amp; Carbon Tracker", "Offline &amp; Sync Status", "Green Score",
    "Live Inference Log", "Embedded Screening Display", "Connectivity Timeline",
    "Energy Breakdown",
]
STAT_LABELS = ["Energy Today", "Carbon Footprint", "Green Score", "Sync Queue", "Uptime Today"]


def test_green_page_markup(app):
    client = app.test_client()
    uid = add_user(app, "gc-admin@example.com", role="medical_officer")
    active_session(client, uid, role="medical_officer")
    resp = client.get("/admin/green-computing")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for marker in ("gc-page", "gc-chart-box", "gc-scroll"):
        assert marker in html
    for text in TITLES + STAT_LABELS:
        assert text in html, text
    assert 'id="energyChart" height' not in html
    assert 'id="energyDonut" height' not in html
