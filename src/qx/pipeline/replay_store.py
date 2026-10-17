"""Persistent canonical replay observations and outcome analytics."""

from __future__ import annotations

from pathlib import Path

from qx.pipeline.replay_analysis import ReplayReport
from qx.storage.connection import connect_sqlite


class ReplayRepository:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect_sqlite(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS replay_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    observation_count INTEGER NOT NULL,
                    transition_count INTEGER NOT NULL,
                    outcome_count INTEGER NOT NULL
                )
                """
            )
            for table in (
                "replay_observations",
                "replay_transitions",
                "replay_outcomes",
                "replay_segments",
            ):
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        replay_run_id INTEGER NOT NULL,
                        record_index INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        FOREIGN KEY(replay_run_id) REFERENCES replay_runs(id)
                    )
                    """
                )

    def save(self, report: ReplayReport) -> int:
        self.initialize()
        with connect_sqlite(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO replay_runs (
                    symbol, timeframe, started_at, completed_at, pipeline_version,
                    observation_count, transition_count, outcome_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.symbol,
                    report.timeframe,
                    report.started_at.isoformat(),
                    report.completed_at.isoformat(),
                    report.pipeline_version,
                    len(report.observations),
                    len(report.transitions),
                    len(report.outcomes),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a replay run id")
            run_id = int(cursor.lastrowid)
            self._save_records(connection, "replay_observations", run_id, report.observations)
            self._save_records(connection, "replay_transitions", run_id, report.transitions)
            self._save_records(connection, "replay_outcomes", run_id, report.outcomes)
            self._save_records(connection, "replay_segments", run_id, report.segments)
            return run_id

    @staticmethod
    def _save_records(connection, table: str, run_id: int, records: list) -> None:
        connection.executemany(
            f"INSERT INTO {table} (replay_run_id, record_index, payload_json) VALUES (?, ?, ?)",
            [
                (run_id, index, record.model_dump_json())
                for index, record in enumerate(records)
            ],
        )
