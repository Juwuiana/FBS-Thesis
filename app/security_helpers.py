"""Shared password-verification para sa patient auth"""
import secrets
from werkzeug.security import check_password_hash, generate_password_hash

_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32))


def verify_password_or_dummy(stored_hash: str | None, password: str) -> bool:
    return check_password_hash(stored_hash or _DUMMY_PASSWORD_HASH, password)