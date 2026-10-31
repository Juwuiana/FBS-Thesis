import re

import pytest

from conftest import active_session, add_user

FIELDS = ('name="current_password"', 'name="new_password"', 'name="confirm_password"')


@pytest.fixture
def admin_client(app):
    uid = add_user(app, "pw-ui-admin@example.com")
    c = app.test_client()
    active_session(c, uid)
    return c


@pytest.fixture
def nurse_client(app):
    uid = add_user(app, "pw-ui-nurse@example.com", role="health_worker")
    c = app.test_client()
    active_session(c, uid, role="health_worker")
    return c


def assert_shared_form(html):
    for field in FIELDS:
        assert field in html
    assert "js/change_password.js" in html
    assert 'data-cp-form' in html
    assert html.count('data-pw-toggle=') == 3
    for fid in re.findall(r'<input class="form-input"[^>]* id="(\w+)"', html):
        assert f'for="{fid}"' in html


def test_admin_privacy_page_uses_shared_form_and_roles_colgroup(admin_client):
    r = admin_client.get("/admin/privacy-security")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert_shared_form(html)
    table = re.search(r'<table[^>]*ps-roles-table.*?</table>', html, re.S).group(0)
    colgroup = re.search(r'<colgroup>(.*?)</colgroup>', table, re.S).group(1)
    assert colgroup.count("<col ") == 4
    assert table.count("<tbody>") == 1
    body = table.split("<tbody>")[1]
    assert body.count("<tr>") == 2


def test_nurse_privacy_page_uses_shared_form_without_fake_logins(nurse_client):
    r = nurse_client.get("/nurse/privacy_security")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert_shared_form(html)
    assert "Jun 10, 08:12 AM" not in html
