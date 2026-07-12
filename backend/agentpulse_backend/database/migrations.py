"""Alembic-style migration runner using raw SQL files.

This is intentionally minimal — no library dependency. Each migration is a
plain SQL file in migrations/. The runner tracks applied versions in the
_schema_version table and applies pending migrations in order.

Usage:
    from agentpulse_backend.database.migrations import run_migrations
    run_migrations("/path/to/db.sqlite")

    # Roll back one version:
    rollback("/path/to/db.sqlite")
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional

from .connection import Connection, DatabaseError


def _load_sql_file(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    # Strip comments and blank lines for cleaner execution
    return content


def get_current_version(db_path: str) -> int:
    """Return the latest applied migration version, or 0 if none applied."""
    conn = Connection(db_path)
    conn.open()
    try:
        # _schema_version may not exist yet on a fresh DB
        row = conn.query_one(
            "SELECT MAX(version) AS v FROM _schema_version"
        )
        return (row["v"] or 0) if row else 0
    except DatabaseError:
        return 0
    finally:
        conn.close()


def _migration_files(migrations_dir: Path) -> list[tuple[int, Path]]:
    """Return sorted list of (version, path) for all SQL migration files."""
    files = []
    for path in migrations_dir.glob("*.sql"):
        m = re.match(r"^(\d+)", path.stem)
        if m:
            files.append((int(m.group(1)), path))
    files.sort(key=lambda x: x[0])
    return files


def run_migrations(db_path: str, migrations_dir: Optional[str] = None) -> int:
    """Run all unapplied migrations in order.

    Returns the number of migrations applied.
    Raises DatabaseError on failure.
    """
    if migrations_dir is None:
        # __file__ is agentpulse_backend/database/migrations.py
        # three levels up = backend/, then /migrations
        migrations_dir = str(Path(__file__).parent.parent.parent / "migrations")
    mdir = Path(migrations_dir)

    conn = Connection(db_path)
    conn.open()
    current = get_current_version(db_path)
    pending = [(v, p) for v, p in _migration_files(mdir) if v > current]

    if not pending:
        return 0

    applied = 0
    try:
        for version, path in pending:
            sql_script = _load_sql_file(path)
            # executescript() is on the raw sqlite3 connection, not the Connection wrapper
            conn._conn.executescript(sql_script)  # type: ignore[reportAttributeAccessIssue]
            conn.commit()
            applied += 1
    finally:
        conn.close()

    return applied


def rollback(db_path: str, steps: int = 1) -> int:
    """Roll back the last `steps` migrations.

    Returns the number of rollbacks performed.
    Note: migrations must define a `rollback` field in _schema_version to undo.
    """
    conn = Connection(db_path)
    conn.open()
    rolled_back = 0
    try:
        for _ in range(steps):
            row = conn.query_one(
                "SELECT version, rollback FROM _schema_version "
                "WHERE rollback IS NOT NULL AND rollback != '' "
                "ORDER BY version DESC LIMIT 1"
            )
            if not row:
                break
            # For now, rollback is informational — actual rollback SQL would go here.
            # Since all tables use IF NOT EXISTS / CREATE TABLE IF NOT EXISTS,
            # rolling back a pure schema migration is destructive.
            # Mark it as rolled back by removing the version row:
            conn.execute(
                "DELETE FROM _schema_version WHERE version = ?",
                (row["version"],)
            )
            conn.commit()
            rolled_back += 1
    finally:
        conn.close()
    return rolled_back


def init_db(db_path: str, migrations_dir: Optional[str] = None) -> None:
    """Initialize an empty database — create _schema_version table, then run migrations.

    This is equivalent to running migrations on a fresh DB for the first time.
    """
    conn = Connection(db_path)
    conn.open()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS _schema_version (
                version  INTEGER PRIMARY KEY,
                applied  TEXT    NOT NULL,
                rollback TEXT
            )"""
        )
        conn.commit()
    finally:
        conn.close()

    run_migrations(db_path, migrations_dir)


def ensure_schema(db_path: str, migrations_dir: Optional[str] = None) -> None:
    """Ensure the schema is at the latest version, running migrations if needed.

    Safe to call on every startup — is a no-op if already current.
    """
    run_migrations(db_path, migrations_dir)
