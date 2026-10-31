import csv
import io
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.db import get_connection
from conftest import active_session, add_user


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed(app, rows):
    """rows: dicts with user_name, action, ip_address, role, severity, created_at."""
    with app.app_context():
        conn = get_connection()
        for r in rows:
            conn.execute(
                "INSERT INTO audit_log (user_id, user_name, role, action, ip_address, severity, created_at) "
                "VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                (r["user_name"], r["role"], r["action"], r["ip_address"], r["severity"], r["created_at"]),
            )
        conn.commit()
        conn.close()


def row(i, **kw):
    base = datetime.now(timezone.utc) - timedelta(minutes=100 - i)
    data = {
        "user_name": f"user{i:02d}", "role": "health_worker", "action": f"Viewed page {i:02d}",
        "ip_address": f"10.0.0.{i}", "severity": "Info", "created_at": _ts(base),
    }
    data.update(kw)
    return data


@pytest.fixture
def client(app):
    admin_id = add_user(app, "audit-filter-admin@example.com")
    c = app.test_client()
    active_session(c, admin_id)
    return c


def actions_on_page(html):
    return re.findall(r'<span class="audit-action">(.*?)</span>', html)


def get(client, **params):
    return client.get("/admin/audit-trails", query_string=params)


def test_default_lists_everything_newest_first(app, client):
    seed(app, [row(i) for i in range(30)])
    html = get(client).get_data(as_text=True)
    acts = actions_on_page(html)
    assert len(acts) == 12
    assert acts[0] == "Viewed page 29"
    assert "of 30 events" in html
    assert "(filtered)" not in html
    assert "All Time" in html


def test_filter_matches_rows_from_page_three_on_page_one(app, client):
    seed(app, [row(i, action=f"Exported report {i}") if i < 5 else row(i) for i in range(30)])
    html = get(client, type="export").get_data(as_text=True)
    assert len(actions_on_page(html)) == 5
    assert "Showing 1–5 of 5 events (filtered)" in html
    assert "5 events (filtered)" in html


def test_filtered_pagination_count_and_links(app, client):
    seed(app, [row(i, severity="Warning") if i % 2 == 0 else row(i) for i in range(30)])  # 15 warnings
    html = get(client, severity="warning").get_data(as_text=True)
    assert "of 15 events (filtered)" in html
    assert len(actions_on_page(html)) == 12
    assert "severity=warning" in html and "page=2" in html
    html2 = get(client, severity="warning", page=2).get_data(as_text=True)
    assert len(actions_on_page(html2)) == 3
    assert "Showing 13–15 of 15" in html2
    assert "page=1" in html2 and "severity=warning" in html2
    assert 'value="warning" selected' in html2


def test_search_case_insensitive_across_fields(app, client):
    seed(app, [
        row(0, user_name="Alice Cooper"),
        row(1, action="Changed PASSWORD"),
        row(2, ip_address="192.168.9.9"),
        row(3),
    ])
    assert len(actions_on_page(get(client, q="alice").get_data(as_text=True))) == 1
    assert len(actions_on_page(get(client, q="password").get_data(as_text=True))) == 1
    assert len(actions_on_page(get(client, q="192.168").get_data(as_text=True))) == 1
    assert 'value="alice"' in get(client, q="alice").get_data(as_text=True)


def test_search_wildcards_match_literally(app, client):
    seed(app, [
        row(0, action="Discount 50% applied"),
        row(1, action="Discount 500 applied"),
        row(2, action="snake_case thing"),
        row(3, action="snakeXcase thing"),
        row(4, action="path a\\b"),
    ])
    assert actions_on_page(get(client, q="50%").get_data(as_text=True)) == ["Discount 50% applied"]
    assert actions_on_page(get(client, q="snake_case").get_data(as_text=True)) == ["snake_case thing"]
    assert actions_on_page(get(client, q="a\\b").get_data(as_text=True)) == ["path a\\b"]


def test_role_filter_including_unknown(app, client):
    seed(app, [
        row(0, role="medical_officer", action="A admin"),
        row(1, role="health_worker", action="B nurse"),
        row(2, role="Unknown", action="C unknown"),
        row(3, role="weird", action="D weird"),
    ])
    assert actions_on_page(get(client, role="admin").get_data(as_text=True)) == ["A admin"]
    assert actions_on_page(get(client, role="nurse").get_data(as_text=True)) == ["B nurse"]
    assert set(actions_on_page(get(client, role="unknown").get_data(as_text=True))) == {"C unknown", "D weird"}


def test_severity_and_type_filters(app, client):
    seed(app, [
        row(0, action="Login ok", severity="Success"),
        row(1, action="Failed login", severity="Critical"),
        row(2, action="Deleted patient", severity="Warning"),
    ])
    assert actions_on_page(get(client, severity="Success").get_data(as_text=True)) == ["Login ok"]
    assert actions_on_page(get(client, severity="warning").get_data(as_text=True)) == ["Deleted patient"]
    assert set(actions_on_page(get(client, type="login").get_data(as_text=True))) == {"Login ok", "Failed login"}
    assert actions_on_page(get(client, type="delete").get_data(as_text=True)) == ["Deleted patient"]


def test_date_filters_use_manila_days(app, client):
    now = datetime.now(timezone.utc)
    seed(app, [
        row(0, action="now", created_at=_ts(now)),
        row(1, action="3 days", created_at=_ts(now - timedelta(days=3))),
        row(2, action="10 days", created_at=_ts(now - timedelta(days=10))),
        row(3, action="40 days", created_at=_ts(now - timedelta(days=40))),
    ])
    assert actions_on_page(get(client, date="today").get_data(as_text=True)) == ["now"]
    assert set(actions_on_page(get(client, date="7d").get_data(as_text=True))) == {"now", "3 days"}
    assert set(actions_on_page(get(client, date="30d").get_data(as_text=True))) == {"now", "3 days", "10 days"}
    assert len(actions_on_page(get(client, date="").get_data(as_text=True))) == 4


def test_filters_combine_with_and(app, client):
    seed(app, [
        row(0, action="Login ok", severity="Success", role="medical_officer"),
        row(1, action="Login ok", severity="Info", role="medical_officer"),
        row(2, action="Login ok", severity="Success", role="health_worker"),
        row(3, action="Export", severity="Success", role="medical_officer"),
    ])
    html = get(client, type="login", severity="success", role="admin").get_data(as_text=True)
    assert len(actions_on_page(html)) == 1
    html = get(client, type="login", severity="success", role="admin", q="nomatch").get_data(as_text=True)
    assert actions_on_page(html) == []


def test_invalid_values_are_ignored(app, client):
    seed(app, [row(i) for i in range(5)])
    r = get(client, type="bogus", role="root", severity="nope", date="yesterday")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert len(actions_on_page(html)) == 5
    assert "(filtered)" not in html
    assert get(client, page="abc").status_code == 200


def test_page_clamped_and_empty_state(app, client):
    seed(app, [row(i) for i in range(30)])
    html = get(client, page=999).get_data(as_text=True)
    assert "Showing 25–30 of 30" in html
    assert get(client, page=-4).status_code == 200
    html = get(client, q="zzz-no-such-thing").get_data(as_text=True)
    assert "No events match these filters." in html
    assert "0 events (filtered)" in html


def test_many_pages_use_window(app, client):
    seed(app, [row(i % 100) for i in range(12 * 25)])
    html = get(client, page=12).get_data(as_text=True)
    assert "…" in html


def export_rows(client, **params):
    r = client.get("/admin/audit-trails/export", query_string=params)
    assert r.status_code == 200
    return list(csv.reader(io.StringIO(r.get_data(as_text=True))))[1:]


def test_export_respects_filters_across_all_pages(app, client):
    seed(app, [row(i, severity="Critical") if i % 2 == 0 else row(i) for i in range(30)])
    rows = export_rows(client, severity="critical")
    assert len(rows) == 15
    assert all(r[6] == "Critical" for r in rows)


def test_export_without_filters_is_unchanged(app, client):
    seed(app, [row(i) for i in range(30)])
    rows = export_rows(client)
    assert len(rows) >= 30
    with app.app_context():
        conn = get_connection()
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'Exported CSV: audit trails'"
        ).fetchone()[0] == 1
        conn.close()
