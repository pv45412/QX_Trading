import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qx.reports.daily_workflow import DailyWorkflowReport


@dataclass(frozen=True)
class StoredWorkflowRun:
    id: int
    created_at: str
    regime_label: str
    risk_level: str
    top_sectors: str
    top_symbols: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class WorkflowComparison:
    current: StoredWorkflowRun | None
    previous: StoredWorkflowRun | None
    regime_changed: bool
    risk_changed: bool
    new_symbols: list[str]
    removed_symbols: list[str]
    new_top_sectors: list[str]
    removed_top_sectors: list[str]


class SQLiteWorkflowRepository:
    """Stores daily workflow snapshots separately from raw scanner runs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    regime_label TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    top_sectors TEXT NOT NULL,
                    top_symbols TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, report: DailyWorkflowReport) -> int:
        self.initialize()
        payload = workflow_report_payload(report)
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO workflow_runs
                    (created_at, regime_label, risk_level, top_sectors, top_symbols, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    report.regime.label,
                    report.regime.risk_level,
                    ",".join(payload["top_sectors"]),
                    ",".join(payload["top_symbols"]),
                    json.dumps(payload),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a workflow run id")
            return int(cursor.lastrowid)

    def list_runs(self, limit: int = 10) -> list[StoredWorkflowRun]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, regime_label, risk_level, top_sectors, top_symbols, payload_json
                FROM workflow_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            StoredWorkflowRun(
                id=int(row[0]),
                created_at=str(row[1]),
                regime_label=str(row[2]),
                risk_level=str(row[3]),
                top_sectors=str(row[4]),
                top_symbols=str(row[5]),
                payload=dict(json.loads(str(row[6]))),
            )
            for row in rows
        ]

    def compare_latest(self) -> WorkflowComparison:
        runs = self.list_runs(limit=2)
        current = runs[0] if runs else None
        previous = runs[1] if len(runs) > 1 else None
        if current is None:
            return WorkflowComparison(None, None, False, False, [], [], [], [])
        if previous is None:
            return WorkflowComparison(current, None, False, False, [], [], [], [])

        current_symbols = _split_csv(current.top_symbols)
        previous_symbols = _split_csv(previous.top_symbols)
        current_sectors = _split_csv(current.top_sectors)
        previous_sectors = _split_csv(previous.top_sectors)
        return WorkflowComparison(
            current=current,
            previous=previous,
            regime_changed=current.regime_label != previous.regime_label,
            risk_changed=current.risk_level != previous.risk_level,
            new_symbols=sorted(set(current_symbols) - set(previous_symbols)),
            removed_symbols=sorted(set(previous_symbols) - set(current_symbols)),
            new_top_sectors=sorted(set(current_sectors) - set(previous_sectors)),
            removed_top_sectors=sorted(set(previous_sectors) - set(current_sectors)),
        )


def workflow_report_payload(report: DailyWorkflowReport) -> dict[str, Any]:
    return {
        "regime": asdict(report.regime),
        "sector_rotation": [asdict(row) for row in report.sector_rotation.rows],
        "sector_failures": report.sector_rotation.failures,
        "top_sectors": [row.sector for row in report.sector_rotation.leaders],
        "top_symbols": [candidate.symbol for candidate in report.morning_report.top_candidates],
        "near_breakout_symbols": [
            candidate.symbol for candidate in report.morning_report.near_breakout_candidates
        ],
        "extended_symbols": [candidate.symbol for candidate in report.morning_report.extended_leaders],
        "action_plan": report.action_plan,
        "scan_run_id": report.morning_report.run.id if report.morning_report.run else None,
    }


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
