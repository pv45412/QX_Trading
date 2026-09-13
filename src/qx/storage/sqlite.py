import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from qx.models.scan import ScanCandidate, ScanRunResult


@dataclass(frozen=True)
class StoredScanRun:
    id: int
    created_at: str
    total_symbols: int
    passed_symbols: int
    failed_symbols: int


@dataclass(frozen=True)
class CandidateChange:
    symbol: str
    current_score: float
    previous_score: float | None
    score_change: float | None
    current_quality: str
    previous_quality: str | None


class SQLiteScanRepository:
    """Stores scan runs and candidate payloads in SQLite."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    total_symbols INTEGER NOT NULL,
                    passed_symbols INTEGER NOT NULL,
                    failed_symbols INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_run_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    score REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id)
                )
                """
            )

    def save_scan_run(self, result: ScanRunResult) -> int:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO scan_runs (created_at, total_symbols, passed_symbols, failed_symbols)
                VALUES (?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    result.total_symbols,
                    result.passed_symbols,
                    result.failed_symbols,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a scan run id")
            run_id = cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO scan_candidates
                    (scan_run_id, symbol, passed, score, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        candidate.symbol,
                        int(candidate.passed),
                        candidate.setup_score,
                        candidate.model_dump_json(),
                    )
                    for candidate in result.candidates
                ],
            )
            return run_id

    def list_scan_runs(self, limit: int = 20) -> list[StoredScanRun]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, total_symbols, passed_symbols, failed_symbols
                FROM scan_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            StoredScanRun(
                id=int(row[0]),
                created_at=str(row[1]),
                total_symbols=int(row[2]),
                passed_symbols=int(row[3]),
                failed_symbols=int(row[4]),
            )
            for row in rows
        ]

    def load_candidates(self, scan_run_id: int) -> list[ScanCandidate]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM scan_candidates
                WHERE scan_run_id = ?
                ORDER BY score DESC
                """,
                (scan_run_id,),
            ).fetchall()
        return [ScanCandidate.model_validate_json(str(row[0])) for row in rows]

    def latest_candidates(self) -> list[ScanCandidate]:
        runs = self.list_scan_runs(limit=1)
        if not runs:
            return []
        return self.load_candidates(runs[0].id)

    def compare_latest_runs(self) -> list[CandidateChange]:
        runs = self.list_scan_runs(limit=2)
        if not runs:
            return []

        current = self.load_candidates(runs[0].id)
        previous = self.load_candidates(runs[1].id) if len(runs) > 1 else []
        previous_by_symbol = {candidate.symbol: candidate for candidate in previous}

        changes: list[CandidateChange] = []
        for candidate in current:
            prior = previous_by_symbol.get(candidate.symbol)
            prior_score = prior.setup_score if prior else None
            changes.append(
                CandidateChange(
                    symbol=candidate.symbol,
                    current_score=candidate.setup_score,
                    previous_score=prior_score,
                    score_change=(
                        candidate.setup_score - prior_score if prior_score is not None else None
                    ),
                    current_quality=candidate.quality_label,
                    previous_quality=prior.quality_label if prior else None,
                )
            )
        return changes
