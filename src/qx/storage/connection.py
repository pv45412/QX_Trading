"""SQLite WAL Mode Connection Factory for QX Platform Storage Layer."""

import sqlite3
from pathlib import Path


def connect_sqlite(database_path: Path | str, timeout: float = 10.0) -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode, busy timeout, and normal sync enabled.

    :param database_path: Path to SQLite database file
    :param timeout: Connection timeout in seconds
    :return: Configured sqlite3.Connection object
    """
    path_str = str(database_path)
    connection = sqlite3.connect(path_str, timeout=timeout)
    try:
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA busy_timeout=10000;")
        connection.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.Error:
        # Ignore pragma failures on memory/temp databases if any
        pass
    return connection
