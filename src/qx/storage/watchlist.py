from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StoredWatchlistSymbol:
    id: int
    list_name: str
    symbol: str
    source: str
    status: str
    notes: str
    context: dict[str, Any]
    created_at: str
    updated_at: str


class SQLiteWatchlistRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def add_symbol(
        self,
        symbol: str,
        *,
        list_name: str = "scanner_review",
        source: str = "qx",
        status: str | None = None,
        notes: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        now = _utc_now()
        status_value = (status or "").strip()
        context_json = _context_json(context)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO watchlist_symbols (
                    list_name, symbol, source, status, notes, context_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(list_name, symbol) DO UPDATE SET
                    source = excluded.source,
                    status = CASE
                        WHEN excluded.status != '' THEN excluded.status
                        ELSE watchlist_symbols.status
                    END,
                    notes = excluded.notes,
                    context_json = CASE
                        WHEN excluded.context_json != '{}' THEN excluded.context_json
                        ELSE watchlist_symbols.context_json
                    END,
                    updated_at = excluded.updated_at
                """,
                (list_name, normalized_symbol, source, status_value, notes, context_json, now, now),
            )

    def list_symbols(self, *, list_name: str = "scanner_review", limit: int = 250) -> list[str]:
        return [entry.symbol for entry in self.list_entries(list_name=list_name, limit=limit)]

    def list_entries(self, *, list_name: str = "scanner_review", limit: int = 250) -> list[StoredWatchlistSymbol]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, list_name, symbol, source, status, notes, context_json, created_at, updated_at
                FROM watchlist_symbols
                WHERE list_name = ?
                ORDER BY updated_at DESC, symbol ASC
                LIMIT ?
                """,
                (list_name, limit),
            ).fetchall()
        return [
            StoredWatchlistSymbol(
                id=int(row[0]),
                list_name=str(row[1]),
                symbol=str(row[2]),
                source=str(row[3]),
                status=str(row[4]),
                notes=str(row[5]),
                context=_parse_context(str(row[6])),
                created_at=str(row[7]),
                updated_at=str(row[8]),
            )
            for row in rows
        ]

    def _init_schema(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist_symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    context_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(list_name, symbol)
                )
                """,
            )
            _ensure_column(connection, "watchlist_symbols", "status", "TEXT NOT NULL DEFAULT ''")
            _ensure_column(connection, "watchlist_symbols", "context_json", "TEXT NOT NULL DEFAULT '{}'")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _context_json(context: dict[str, Any] | None) -> str:
    if not context:
        return "{}"
    return json.dumps(context, sort_keys=True, default=str)


def _parse_context(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
