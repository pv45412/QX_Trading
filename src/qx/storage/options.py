import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from qx.models.market import BarDataRequest
from qx.options.ideas import OptionIdea
from qx.data.providers import MarketDataProvider
from qx.storage.connection import connect_sqlite


@dataclass(frozen=True)
class StoredOptionIdea:
    id: int
    created_at: str
    symbol: str
    action: str
    direction: str
    strategy: str
    idea_score: float
    status: str
    entry_underlying_price: float
    latest_underlying_price: float | None
    latest_return_pct: float | None
    payload: dict[str, object]


@dataclass(frozen=True)
class StoredOptionIdeaPerformance:
    id: int
    option_idea_id: int
    created_at: str
    underlying_price: float
    return_pct: float
    note: str


class SQLiteOptionIdeaRepository:
    """Stores generated options ideas and simple underlying performance snapshots."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS option_ideas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    idea_score REAL NOT NULL,
                    status TEXT NOT NULL,
                    entry_underlying_price REAL NOT NULL,
                    latest_underlying_price REAL,
                    latest_return_pct REAL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS option_idea_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    option_idea_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    underlying_price REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(option_idea_id) REFERENCES option_ideas(id)
                )
                """
            )

    def save_ideas(self, ideas: list[OptionIdea], *, status: str = "Watch") -> int:
        self.initialize()
        created_at = datetime.now(UTC).isoformat()
        with connect_sqlite(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO option_ideas (
                    created_at, symbol, action, direction, strategy, idea_score, status,
                    entry_underlying_price, latest_underlying_price, latest_return_pct, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        created_at,
                        idea.symbol,
                        idea.action,
                        idea.direction,
                        idea.strategy,
                        idea.idea_score,
                        status,
                        idea.underlying_price,
                        None,
                        None,
                        json.dumps(asdict(idea)),
                    )
                    for idea in ideas
                ],
            )
            return len(ideas)

    def tracking_counts(self) -> dict[str, int]:
        """Count saved IDs and snapshots independently of the displayed page."""
        self.initialize()
        with connect_sqlite(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT (SELECT COUNT(*) FROM option_ideas),
                       (SELECT COUNT(*) FROM option_idea_performance),
                       (SELECT COUNT(DISTINCT p.option_idea_id)
                        FROM option_idea_performance p
                        JOIN option_ideas i ON i.id = p.option_idea_id)
                """
            ).fetchone()
        return dict(zip(("saved_ideas", "performance_snapshots", "tracked_ideas"), map(int, row)))

    def list_ideas(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[StoredOptionIdea]:
        self.initialize()
        query = """
            SELECT id, created_at, symbol, action, direction, strategy, idea_score, status,
                   entry_underlying_price, latest_underlying_price, latest_return_pct, payload_json
            FROM option_ideas
        """
        params: tuple[object, ...]
        if status:
            query += " WHERE status = ?"
            params = (status, limit, offset)
        else:
            params = (limit, offset)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            StoredOptionIdea(
                id=int(row[0]),
                created_at=str(row[1]),
                symbol=str(row[2]),
                action=str(row[3]),
                direction=str(row[4]),
                strategy=str(row[5]),
                idea_score=float(row[6]),
                status=str(row[7]),
                entry_underlying_price=float(row[8]),
                latest_underlying_price=float(row[9]) if row[9] is not None else None,
                latest_return_pct=float(row[10]) if row[10] is not None else None,
                payload=json.loads(str(row[11])),
            )
            for row in rows
        ]

    def mark_status(self, idea_id: int, status: str) -> None:
        self.initialize()
        with connect_sqlite(self.database_path) as connection:
            connection.execute("UPDATE option_ideas SET status = ? WHERE id = ?", (status, idea_id))

    def update_performance(
        self,
        provider: MarketDataProvider,
        *,
        status: str = "Watch",
        max_workers: int = 8,
    ) -> int:
        ideas = self.list_ideas(status=status, limit=500)

        def fetch_latest_price(idea: StoredOptionIdea) -> tuple[StoredOptionIdea, float] | None:
            if idea.entry_underlying_price <= 0:
                return None
            try:
                bars = provider.get_daily_bars(BarDataRequest(symbol=idea.symbol, period="1mo"))
                return idea, float(bars["close"].iloc[-1])
            except Exception:
                return None

        price_results: list[tuple[StoredOptionIdea, float]] = []
        workers = max(1, min(max_workers, len(ideas) or 1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_latest_price, idea): idea.id for idea in ideas}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    price_results.append(result)

        updated = 0
        with connect_sqlite(self.database_path) as connection:
            for idea, latest_price in price_results:
                return_pct = (latest_price / idea.entry_underlying_price) - 1.0
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    """
                    UPDATE option_ideas
                    SET latest_underlying_price = ?, latest_return_pct = ?
                    WHERE id = ?
                    """,
                    (latest_price, return_pct, idea.id),
                )
                connection.execute(
                    """
                    INSERT INTO option_idea_performance
                        (option_idea_id, created_at, underlying_price, return_pct, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (idea.id, now, latest_price, return_pct, "underlying close snapshot"),
                )
                updated += 1
        return updated

    def list_performance(
        self,
        *,
        option_idea_id: int | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[StoredOptionIdeaPerformance]:
        self.initialize()
        query = """
            SELECT id, option_idea_id, created_at, underlying_price, return_pct, note
            FROM option_idea_performance
        """
        params: tuple[object, ...]
        if option_idea_id is not None:
            query += " WHERE option_idea_id = ?"
            params = (option_idea_id, limit, offset)
        else:
            params = (limit, offset)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        with connect_sqlite(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            StoredOptionIdeaPerformance(
                id=int(row[0]),
                option_idea_id=int(row[1]),
                created_at=str(row[2]),
                underlying_price=float(row[3]),
                return_pct=float(row[4]),
                note=str(row[5]),
            )
            for row in rows
        ]


def stored_option_ideas_frame(ideas: list[StoredOptionIdea]) -> pd.DataFrame:
    return pd.DataFrame([asdict(idea) for idea in ideas])


def option_idea_performance_frame(performance: list[StoredOptionIdeaPerformance]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in performance])
