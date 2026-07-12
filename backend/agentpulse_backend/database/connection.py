"""Database connection and session management.

All database operations flow through here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string with Z suffix."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DatabaseError(RuntimeError):
    """Raised for any database-level failure."""


class Connection:
    """Thread-unsafe SQLite connection wrapper.

    SQLite connections must be single-threaded; each request gets its own
    Connection instance from the store. This class deliberately does NOT
    pool or share connections — that is the caller's responsibility.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _open(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def open(self) -> None:
        """Acquire a connection."""
        if self._conn is None:
            self._conn = self._open()

    def close(self) -> None:
        """Release the connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.open()
        assert self._conn is not None
        return self._conn

    def execute(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> sqlite3.Cursor:
        """Execute a write statement and return the cursor."""
        try:
            return self.conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def executemany(
        self, sql: str, params_seq: List[Tuple[Any, ...]]
    ) -> sqlite3.Cursor:
        """Execute a write statement with a sequence of parameters."""
        try:
            return self.conn.executemany(sql, params_seq)
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def query(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> List[Dict[str, Any]]:
        """Execute a read-only statement and return all rows as dicts."""
        try:
            cur = self.conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def query_one(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> Optional[Dict[str, Any]]:
        """Execute a read-only statement and return one row or None."""
        try:
            cur = self.conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def commit(self) -> None:
        """Commit the current transaction."""
        try:
            self.conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(str(exc)) from exc

    def rollback(self) -> None:
        """Roll back the current transaction."""
        try:
            self.conn.rollback()
        except sqlite3.Error:
            pass  # no active transaction is fine


class _Transaction:
    """Internal context manager for a database transaction."""

    __slots__ = ("_conn", "_active")

    def __init__(self, conn: Connection) -> None:
        self._conn = conn
        self._active = True

    def __enter__(self) -> Connection:
        self._conn.open()
        return self._conn

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[bool]:
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._active = False
        return None


class Store:
    """Database store — owns a Connection and provides a transaction context.

    Usage:
        with store.transaction() as conn:
            conn.execute(sql, params)
        # committed automatically
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.connection = Connection(db_path)

    def transaction(self) -> _Transaction:
        """Return a transaction context manager."""
        return _Transaction(self.connection)

    def close(self) -> None:
        """Close the connection."""
        self.connection.close()

    def scalar(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> Any:
        """Return a single scalar value."""
        row = self.connection.query_one(sql, params)
        if row:
            return next(iter(row.values()))
        return None
