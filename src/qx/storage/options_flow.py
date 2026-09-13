import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from qx.options_flow.models import OptionFlowAnalysis, OptionFlowTrade


class SQLiteOptionFlowRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS qx_option_flow_event (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    option_symbol TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS qx_option_flow_signal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    call_buy_score REAL NOT NULL,
                    put_buy_score REAL NOT NULL,
                    no_trade_risk REAL NOT NULL,
                    final_signal TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save_analysis(self, analysis: OptionFlowAnalysis) -> int:
        self.initialize()
        created_at = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO qx_option_flow_event
                    (created_at, ticker, option_symbol, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        created_at,
                        trade.ticker,
                        trade.option_symbol,
                        trade.model_dump_json(),
                    )
                    for trade in analysis.trades
                ],
            )
            cursor = connection.execute(
                """
                INSERT INTO qx_option_flow_signal
                    (
                        created_at,
                        ticker,
                        call_buy_score,
                        put_buy_score,
                        no_trade_risk,
                        final_signal,
                        payload_json
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    analysis.ticker,
                    analysis.call_buy_score,
                    analysis.put_buy_score,
                    analysis.no_trade_risk,
                    analysis.final_signal,
                    analysis.model_dump_json(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an option flow signal id")
            return int(cursor.lastrowid)

    def latest_trades(self, ticker: str, *, limit: int = 100) -> list[OptionFlowTrade]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM qx_option_flow_event
                WHERE ticker = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (ticker.upper(), limit),
            ).fetchall()
        return [OptionFlowTrade.model_validate_json(str(row[0])) for row in rows]
