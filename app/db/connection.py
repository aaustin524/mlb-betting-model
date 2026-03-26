from __future__ import annotations

import sqlite3

from app.runtime_env import resolve_database_path


def get_connection() -> sqlite3.Connection:
    """
    Return a connection to the project's SQLite database.
    """
    DB_PATH = resolve_database_path()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)
