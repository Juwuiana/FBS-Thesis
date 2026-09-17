"""
Thin sqlite3 layer -- no ORM -- plus the numbered-migration runner.

Everything here is plain `sqlite3` from the standard library. Queries
elsewhere in the app (app/models/*.py) are written as raw, parameterized
SQL strings executed against a connection handed out from here.

Two ways to get a connection:

    get_db()          request-scoped, cached on flask.g, closed by
                      close_db() at the end of the request. Use this from
                      views/controllers/models running inside a request.

    get_connection()  a fresh standalone connection with the same PRAGMAs.
                      Use this from CLI scripts, one-off maintenance
                      scripts, and the migration runner -- i.e. anywhere
                      there is no Flask request to hang a connection off.
                      This is the same entry point the nurse/patient branch
                      uses, so model code written against it ports over
                      unchanged.

Schema changes live in app/models/migrations/NNNN_description.sql and are
applied in filename order exactly once each; applied filenames are recorded
in the schema_migrations table. There is no schema.sql any more -- to change
the schema, add the next numbered file, never edit an applied one.
"""
import os
import sqlite3
from pathlib import Path

from flask import current_app, g

# app/models/migrations/ -- same path the nurse/patient branch uses, so the
# two migration sets are a clean union when the branches merge.
MIGRATIONS_DIR = Path(__file__).resolve().parent / "models" / "migrations"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "instance" / "fbs_thesis.sqlite3"

# Both branches historically used a different filename: the admin branch
# created instance/fbs_thesis.sqlite3, the nurse/patient branch created
# fbs_thesis.db in the repo root. Rather than force either one to move its
# working database, fall back to whichever of these already exists (first
# match wins). A fresh checkout with neither file present gets DEFAULT_DB_PATH.
LEGACY_DB_CANDIDATES = (
    DEFAULT_DB_PATH,
    PROJECT_ROOT / "fbs_thesis.db",
)


def database_path():
    """Single source of truth for where the sqlite file lives.

    Order: Flask config["DATABASE"] -> $DATABASE_PATH -> an existing file
    from LEGACY_DB_CANDIDATES -> instance/fbs_thesis.sqlite3.

    Nothing else in the codebase should hardcode a .db/.sqlite3 path. If you
    want to be unambiguous, set DATABASE_PATH in .env and the candidate
    search never runs.
    """
    try:
        configured = current_app.config.get("DATABASE")
        if configured:
            return str(configured)
    except RuntimeError:
        # No application context (CLI script, `python reset_data.py`, etc.)
        pass

    from_env = os.environ.get("DATABASE_PATH")
    if from_env:
        return from_env

    for candidate in LEGACY_DB_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return str(DEFAULT_DB_PATH)


def _connect(path):
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    # Rows behave like dicts (row["email"]) instead of plain tuples.
    conn.row_factory = sqlite3.Row
    # FKs are off by default in sqlite and are per-connection, so this has
    # to be set on every single connection or the REFERENCES clauses in the
    # migrations are decorative.
    conn.execute("PRAGMA foreign_keys = ON")
    # Wait instead of instantly raising "database is locked" when the dev
    # server has two requests in flight.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_connection():
    """A fresh standalone connection. Caller is responsible for closing it."""
    path = database_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return _connect(path)


def get_db():
    """Return a request-scoped sqlite3 connection, creating it if needed."""
    if "db" not in g:
        g.db = _connect(database_path())
    return g.db


def close_db(e=None):
    """Close the connection at the end of the request, if one was opened."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --------------------------------------------------------------------------
# Migration runner
# --------------------------------------------------------------------------

def _ensure_migrations_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    TEXT PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def migration_files():
    """Every migration on disk, in filename (= numeric) order."""
    if not MIGRATIONS_DIR.is_dir():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)


def applied_migrations(conn):
    """Set of filenames already recorded as applied."""
    _ensure_migrations_table(conn)
    return {
        row["filename"]
        for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
    }


def pending_migrations(conn):
    """Migrations on disk that haven't been applied yet, in order."""
    applied = applied_migrations(conn)
    return [f for f in migration_files() if f.name not in applied]


def mark_applied(filenames, conn=None):
    """Record migrations as applied WITHOUT running them ("baseline"/fake).

    Use this when a database already has the tables a migration would create
    -- e.g. an old instance/fbs_thesis.sqlite3 built by the retired
    schema.sql -- so the runner doesn't try to re-apply them.
    """
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        _ensure_migrations_table(conn)
        for name in filenames:
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (filename) VALUES (?)",
                (name,),
            )
        conn.commit()
    finally:
        if own_conn:
            conn.close()
    return list(filenames)


def run_migrations(conn=None):
    """Apply every pending migration in filename order.

    Returns the list of filenames applied (empty if already up to date).

    Caveat, same as any sqlite migration runner built on executescript():
    a script with several statements that fails halfway can leave the
    earlier statements applied, and the file is NOT recorded, so the next
    run retries it from the top. Keep each migration small, prefer
    CREATE TABLE IF NOT EXISTS, and if one does wedge, fix the .sql and
    use `flask db-baseline` to skip the part that already landed.
    """
    own_conn = conn is None
    conn = conn or get_connection()
    applied_now = []
    try:
        for path in pending_migrations(conn):
            try:
                conn.executescript(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (?)",
                    (path.name,),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise RuntimeError(
                    f"Migration {path.name} failed: {exc}. "
                    f"Database left at {applied_now[-1] if applied_now else 'its previous state'}."
                ) from exc
            applied_now.append(path.name)
        # A migration that rebuilds tables has to run with
        # PRAGMA foreign_keys = OFF, and a PRAGMA inside a script can leave
        # the connection that way. Put it back so a caller-supplied
        # connection isn't silently left with FK enforcement disabled.
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        if own_conn:
            conn.close()
    return applied_now


def foreign_key_violations(conn=None):
    """Rows reported by PRAGMA foreign_key_check, as a list of dicts.

    Empty list means every FK in the database resolves. Worth running after
    any migration that rebuilds tables.
    """
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        return [
            {
                "table": row[0],
                "rowid": row[1],
                "references": row[2],
                "fk_index": row[3],
            }
            for row in conn.execute("PRAGMA foreign_key_check").fetchall()
        ]
    finally:
        if own_conn:
            conn.close()


def init_db():
    """Bring the database up to date by running pending migrations in order.

    Safe to call on every startup: already-applied migrations are skipped by
    filename, so this is a no-op once the schema is current.
    """
    return run_migrations()


def init_app(app):
    app.teardown_appcontext(close_db)
