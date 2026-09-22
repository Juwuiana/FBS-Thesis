"""
Backwards-compatible shim.

The connection factory and the migration runner now live in app/db.py, which
is byte-identical to the file of the same name on the admin-data-management
branch. Keeping one implementation means the two branches cannot drift apart
on PRAGMAs, on where the sqlite file lives, or on how migrations are applied.

Every existing `from app.models.db import get_connection` / `run_migrations`
import keeps working, so no model or controller needed changing.
"""
from app.db import (  # noqa: F401  (re-exported for backwards compatibility)
    MIGRATIONS_DIR,
    applied_migrations,
    database_path,
    foreign_key_violations,
    get_connection,
    init_db,
    mark_applied,
    migration_files,
    pending_migrations,
    run_migrations,
)


def __getattr__(name):
    # The old module exposed DB_PATH as a module-level constant. It is now
    # resolved per call so config/env changes are respected; keep the old
    # name working but make it lazy rather than frozen at import time.
    if name == "DB_PATH":
        from pathlib import Path

        return Path(database_path())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
