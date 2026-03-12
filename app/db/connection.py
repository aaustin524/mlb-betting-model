from __future__ import annotations

import sqlite3

from app.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """
    Return a connection to the project's SQLite database.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)