"""
Thin sqlite3 connection layer -- no ORM.

Everything here is plain `sqlite3` from the standard library. Queries
elsewhere in the app (app/models/user.py) are written as raw, parameterized
SQL strings executed against the connection returned by get_db().
"""
import sqlite3

from flask import current_app, g


def get_db():
    """Return a request-scoped sqlite3 connection, creating it if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        # Rows behave like dicts (row["email"]) instead of plain tuples.
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """Close the connection at the end of the request, if one was opened."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables from schema.sql if they don't already exist."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


def init_app(app):
    app.teardown_appcontext(close_db)
