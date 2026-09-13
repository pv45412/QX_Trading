import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from qx.processing.overnight_workflow import OvernightWorkflowResult


@dataclass(frozen=True)
class PipelineRunMetadata:
    universe: str
    period: str
    profile: str
    data_source: str
    lookback: int
    max_range_pct: float
    refresh: bool


@dataclass(frozen=True)
class StoredPipelineRun:
    id: int
    created_at: str
    universe: str
    period: str
    profile: str
    data_source: str
    scan_run_id: int
    workflow_run_id: int
    cached_symbols: int
    cache_failures: int
    scanned_symbols: int
    candidates: int
    scan_failures: int
    regime_label: str
    risk_level: str
    auth_warning: str
    payload: dict[str, Any]


class SQLitePipelineRepository:
    """Stores operational pipeline runs so scan/report history can be audited."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    universe TEXT NOT NULL,
                    period TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    scan_run_id INTEGER NOT NULL,
                    workflow_run_id INTEGER NOT NULL,
                    cached_symbols INTEGER NOT NULL,
                    cache_failures INTEGER NOT NULL,
                    scanned_symbols INTEGER NOT NULL,
                    candidates INTEGER NOT NULL,
                    scan_failures INTEGER NOT NULL,
                    regime_label TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    auth_warning TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, result: OvernightWorkflowResult, metadata: PipelineRunMetadata) -> int:
        self.initialize()
        payload = _pipeline_payload(result, metadata)
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_runs
                    (
                        created_at, universe, period, profile, data_source,
                        scan_run_id, workflow_run_id, cached_symbols, cache_failures,
                        scanned_symbols, candidates, scan_failures, regime_label,
                        risk_level, auth_warning, payload_json
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    metadata.universe,
                    metadata.period,
                    metadata.profile,
                    metadata.data_source,
                    result.scan_run_id,
                    result.workflow_run_id,
                    result.cache_refresh.refreshed_symbols,
                    result.cache_refresh.failed_symbols,
                    result.scan_result.total_symbols,
                    len(result.scan_result.candidates),
                    result.scan_result.failed_symbols,
                    result.workflow_report.regime.label,
                    result.workflow_report.regime.risk_level,
                    result.auth_warning,
                    json.dumps(payload),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a pipeline run id")
            return int(cursor.lastrowid)

    def list_runs(self, limit: int = 10) -> list[StoredPipelineRun]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    id, created_at, universe, period, profile, data_source,
                    scan_run_id, workflow_run_id, cached_symbols, cache_failures,
                    scanned_symbols, candidates, scan_failures, regime_label,
                    risk_level, auth_warning, payload_json
                FROM pipeline_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_pipeline_run(row) for row in rows]


def pipeline_runs_frame(runs: list[StoredPipelineRun]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": run.id,
                "created_at": run.created_at,
                "universe": run.universe,
                "period": run.period,
                "profile": run.profile,
                "data_source": run.data_source,
                "cached_symbols": run.cached_symbols,
                "cache_failures": run.cache_failures,
                "scanned_symbols": run.scanned_symbols,
                "candidates": run.candidates,
                "scan_failures": run.scan_failures,
                "regime": run.regime_label,
                "risk": run.risk_level,
                "auth_warning": run.auth_warning or "None",
                "health": _run_health(run),
            }
            for run in runs
        ]
    )


def _run_health(run: StoredPipelineRun) -> str:
    if run.auth_warning:
        return "Auth Warning"
    if run.cache_failures or run.scan_failures:
        return "Data Issues"
    if run.candidates == 0:
        return "No Candidates"
    return "Ready"


def _pipeline_payload(
    result: OvernightWorkflowResult,
    metadata: PipelineRunMetadata,
) -> dict[str, Any]:
    return {
        "metadata": asdict(metadata),
        "scan_run_id": result.scan_run_id,
        "workflow_run_id": result.workflow_run_id,
        "metadata_symbols": result.metadata_symbols,
        "cache_refresh": {
            "total_symbols": result.cache_refresh.total_symbols,
            "refreshed_symbols": result.cache_refresh.refreshed_symbols,
            "failed_symbols": result.cache_refresh.failed_symbols,
            "failures": [asdict(failure) for failure in result.cache_refresh.failures[:100]],
        },
        "scan": {
            "total_symbols": result.scan_result.total_symbols,
            "passed_symbols": result.scan_result.passed_symbols,
            "failed_symbols": result.scan_result.failed_symbols,
            "candidates": len(result.scan_result.candidates),
        },
        "workflow": {
            "regime_label": result.workflow_report.regime.label,
            "risk_level": result.workflow_report.regime.risk_level,
            "top_symbols": [
                candidate.symbol for candidate in result.workflow_report.morning_report.top_candidates
            ],
            "top_sectors": [row.sector for row in result.workflow_report.sector_rotation.leaders],
            "action_plan": result.workflow_report.action_plan,
        },
        "auth_warning": result.auth_warning,
    }


def _row_to_pipeline_run(row: tuple[object, ...]) -> StoredPipelineRun:
    return StoredPipelineRun(
        id=int(str(row[0])),
        created_at=str(row[1]),
        universe=str(row[2]),
        period=str(row[3]),
        profile=str(row[4]),
        data_source=str(row[5]),
        scan_run_id=int(str(row[6])),
        workflow_run_id=int(str(row[7])),
        cached_symbols=int(str(row[8])),
        cache_failures=int(str(row[9])),
        scanned_symbols=int(str(row[10])),
        candidates=int(str(row[11])),
        scan_failures=int(str(row[12])),
        regime_label=str(row[13]),
        risk_level=str(row[14]),
        auth_warning=str(row[15]),
        payload=dict(json.loads(str(row[16]))),
    )
