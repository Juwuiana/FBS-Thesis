import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app.controllers import auth_controller
from app.controllers.auth_controller import PASSWORD_REGEX, validate_password_strength
from app.db import get_connection
from app.models import user as user_model

# One shared list; signup.js documents the same examples next to its regex.
ACCEPTED = ["Tr0ub4dor&3xYz!", "Blue-Horse-Battery-7!", "Under_score9Xyzq"]
REJECTED = [
    "000000000000",
    "aaaaaaaaaaaa",
    "Password1234",       # no special character
    "password123!",       # no uppercase
    "PASSWORD123!",       # no lowercase
    "Password!!!!!!",     # no digit (and repeats)
    "Passw0rd!   x",      # whitespace
    "Passsword1!x1",      # 3 repeated characters
    "Short1!aBcd",        # 11 characters
    "Aa1!" + "bcdE" * 32,  # 132 characters
    "A" + "b1!" * 42 + "Cd",  # 129 characters
]


@pytest.mark.parametrize("pw", ACCEPTED)
def test_regex_and_validator_accept(pw):
    assert PASSWORD_REGEX.fullmatch(pw)
    assert validate_password_strength(pw) == []


@pytest.mark.parametrize("pw", REJECTED)
def test_regex_and_validator_reject(pw):
    assert not PASSWORD_REGEX.fullmatch(pw)
    assert validate_password_strength(pw)


def test_129_char_password_rejected():
    pw = "Aa1!" + "bcdefghijk" * 12 + "xyzab"
    assert len(pw) == 129
    assert not PASSWORD_REGEX.fullmatch(pw)
    assert "Password must be at most 128 characters." in validate_password_strength(pw)
    assert PASSWORD_REGEX.fullmatch(pw[:128])


def test_trailing_newline_rejected():
    assert not PASSWORD_REGEX.fullmatch("Tr0ub4dor&3xYz!\n")


def test_specific_messages():
    assert "Password must include an uppercase letter." in validate_password_strength("password123!x")
    assert "Password must include a special character." in validate_password_strength("Password1234x")
    assert "Password must not repeat the same character 3 times in a row." in validate_password_strength("Passsword1!xyz")
    assert any("at least 12" in e for e in validate_password_strength("Ab1!"))


def test_rejects_personal_info():
    kw = dict(first_name="Jocelyn", last_name="Javier", email="jo.calma@example.com")
    assert "Password must not contain your name or email." in validate_password_strength("Xx-jocelyn-9Zq!", **kw)
    assert "Password must not contain your name or email." in validate_password_strength("Xx-JAVIER-9Zq!k", **kw)
    assert "Password must not contain your name or email." in validate_password_strength("Xx-jo.calma-9Zq!", **kw)
    assert validate_password_strength("Tr0ub4dor&3xYz!", **kw) == []
    # parts shorter than 3 characters are ignored
    assert validate_password_strength("Tr0ub4dor&3xYz!", first_name="Yz", last_name="", email="") == []


def _form(password, **over):
    data = {
        "first_name": "Maria", "last_name": "Santos", "birthday": "1990-01-01", "sex": "female",
        "email": "maria.s@example.com", "phone": "9171234567", "role": "health_worker",
        "facility": "lhui", "barangay_name": "Aplaya", "password": password,
        "confirm_password": password, "terms": "on",
    }
    data.update(over)
    return data


def _count_users(app, email):
    with app.app_context():
        conn = get_connection()
        n = conn.execute("SELECT COUNT(*) FROM users WHERE email = ?", (email,)).fetchone()[0]
        conn.close()
        return n


def test_signup_weak_password_returns_400_and_creates_nothing(app):
    client = app.test_client()
    resp = client.post("/signup", data=_form("Password1234"))
    assert resp.status_code == 400
    assert "Password must include a special character." in resp.get_data(as_text=True)
    assert _count_users(app, "maria.s@example.com") == 0


def test_signup_strong_password_creates_pending_user(app):
    client = app.test_client()
    resp = client.post("/signup", data=_form("Tr0ub4dor&3xYz!"))
    assert resp.status_code == 302
    assert _count_users(app, "maria.s@example.com") == 1


def test_signup_password_with_name_rejected(app):
    resp = app.test_client().post("/signup", data=_form("Xx-maria-9Zq!k"))
    assert resp.status_code == 400
    assert "must not contain your name or email" in resp.get_data(as_text=True)


def _make_user(app, password="OldPassword123!"):
    with app.app_context():
        return user_model.create_user(
            {"first_name": "Maria", "middle_name": None, "last_name": "Santos", "birthday": "1990-01-01",
             "sex": "female", "email": "maria.s@example.com", "phone": "9171234567",
             "role": "medical_officer", "facility": "lhui", "barangay": "aplaya"},
            generate_password_hash(password), status="approved",
        )


def _change(app, uid, **form):
    base = {"current_password": "OldPassword123!", "new_password": "Tr0ub4dor&3xYz!",
            "confirm_password": "Tr0ub4dor&3xYz!"}
    base.update(form)
    with app.test_request_context():
        from flask import session
        session["user_id"] = uid
        return auth_controller.change_own_password(uid, base)


def test_change_password_rules(app):
    uid = _make_user(app)
    assert any("uppercase" in e for e in _change(app, uid, new_password="weakpassword1!x", confirm_password="weakpassword1!x"))
    assert any("name or email" in e for e in _change(app, uid, new_password="Xx-santos-9Zq!k", confirm_password="Xx-santos-9Zq!k"))
    assert "Current password is incorrect." in _change(app, uid, current_password="nope")
    assert "Passwords do not match." in _change(app, uid, confirm_password="Different-9Zq!kk")
    assert "New password must be different from your current password." in _change(
        app, uid, new_password="OldPassword123!", confirm_password="OldPassword123!")
    with app.app_context():
        assert check_password_hash(user_model.get_user_by_id(uid)["password_hash"], "OldPassword123!")
    assert _change(app, uid) == []
    with app.app_context():
        assert check_password_hash(user_model.get_user_by_id(uid)["password_hash"], "Tr0ub4dor&3xYz!")


def test_signup_page_markup(app):
    html = app.test_client().get("/signup").get_data(as_text=True)
    for label in ("First Name", "Last Name", "Birthday", "Sex", "Email Address", "Phone Number",
                  "Role / Position", "Health Facility", "Region", "City / Municipality",
                  "Assigned Barangay", "Password", "Confirm Password"):
        assert f'>{label} <span class="req-star" aria-hidden="true">*</span></label>' in html, label
    assert '>Middle Name</label>' in html
    assert 'Middle Name <span class="req-star"' not in html
    assert 'Health System <span class="req-star"' in html  # Terms label
    for rule in ("length", "upper", "lower", "number", "special", "repeat", "name"):
        assert f'id="rule-{rule}"' in html
    assert 'id="rule-match"' in html
