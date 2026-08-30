"""Shared SQLite connection and transaction mechanics for reference adapters."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class SqliteReferenceDatabase:
    """Mixin that gives reference stores consistent SQLite transaction behavior."""

    path: str
    _read_only: bool = False

    def _connect(self) -> sqlite3.Connection:
        if self._read_only:
            database_path = Path(self.path).resolve()
            database = sqlite3.connect(
                f"{database_path.as_uri()}?mode=ro",
                uri=True,
                timeout=30,
                isolation_level=None,
            )
            database.execute("PRAGMA query_only=ON")
        else:
            database = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA busy_timeout=30000")
        return database

    @contextmanager
    def _immediate(self, database: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        if self._read_only:
            raise sqlite3.OperationalError("read-only reference database cannot start a write transaction")
        database.execute("BEGIN IMMEDIATE")
        try:
            yield database
            database.execute("COMMIT")
        except BaseException:
            database.execute("ROLLBACK")
            raise
