from tests.conftest import active_session, add_user


def test_admin_dashboard_compact_markup(app):
    client = app.test_client()
    uid = add_user(app, "ui-admin@example.com", role="medical_officer")
    active_session(client, uid, role="medical_officer")
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "admin-dash" in html
    assert html.count('class="admin-chart-box"') == 3
    for label in (
        "Total Screened",
        "Risk Distribution",
        "Screenings Over Time",
        "Barangay List by At-Risk Count",
        "Recent Screenings",
        "Model Performance (Current Model)",
    ):
        assert label in html
