"""Shared SQLite connection and transaction mechanics for reference adapters."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator


class SqliteReferenceDatabase:
    """Mixin that gives reference stores consistent SQLite transaction behavior."""

    path: str

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA busy_timeout=30000")
        return database

    @contextmanager
    def _immediate(self, database: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        database.execute("BEGIN IMMEDIATE")
        try:
            yield database
            database.execute("COMMIT")
        except BaseException:
            database.execute("ROLLBACK")
            raise
