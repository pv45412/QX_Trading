"""Read-only operational status contracts for the consolidated System workspace."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from qx.automation.morning import AutomationTaskStatus, get_task_status
from qx.config.rules_config import load_rules_config
from qx.data.cache_status import list_bar_cache, summarize_bar_cache
from qx.ops import HealthChecker
from qx.pipeline.models import PIPELINE_VERSION


class OperationalComponent(BaseModel):
    name: str
    status: str
    detail: str | None = None


class CacheStatus(BaseModel):
    status: str
    freshness_status: str
    total_files: int = 0
    total_symbols: int = 0
    total_size_mb: float = 0.0
    periods: dict[str, int] = Field(default_factory=dict)
    latest_modified_at: str | None = None


class PipelineMetadata(BaseModel):
    pipeline_version: str
    rules_config_version: str | None = None
    status: str


class RunRecord(BaseModel):
    run_type: str
    run_id: int
    created_at: str
    status: str
    summary: str


class RunHistoryStatus(BaseModel):
    status: str
    records: list[RunRecord] = Field(default_factory=list)


class SystemOverview(BaseModel):
    generated_at: str
    status: str
    pipeline: PipelineMetadata
    components: list[OperationalComponent] = Field(default_factory=list)
    cache: CacheStatus
    run_history: RunHistoryStatus


class JobStatus(BaseModel):
    status: str
    configured: bool
    task_name: str
    scheduler_state: str
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_result: str | None = None
    last_result_label: str | None = None


def create_system_status_router(
    *,
    database: Path,
    cache_dir: Path,
    task_status_provider: Callable[[], AutomationTaskStatus] = get_task_status,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/system/overview", response_model=SystemOverview)
    def system_overview() -> SystemOverview:
        health = HealthChecker(cache_dir).audit_system_health()
        files = list_bar_cache(cache_dir)
        summary = summarize_bar_cache(cache_dir)
        latest_modified = max((item.modified_at for item in files), default=None)
        try:
            rules_version = load_rules_config().version
            rules_status = "AVAILABLE"
        except Exception:
            rules_version = None
            rules_status = "UNAVAILABLE"
        components = [_operational_component(item, summary.total_files) for item in health.components]
        if rules_status == "UNAVAILABLE":
            components.append(OperationalComponent(
                name="rules_config",
                status="DEGRADED",
                detail="Rules configuration metadata is unavailable.",
            ))
        overall = health.status
        if health.status == "ERROR" or any(item.status == "ERROR" for item in components):
            overall = "ERROR"
        elif rules_status == "UNAVAILABLE" or any(item.status != "OK" for item in components):
            overall = "DEGRADED"
        return SystemOverview(
            generated_at=datetime.now(timezone.utc).isoformat(),
            status=overall,
            pipeline=PipelineMetadata(
                pipeline_version=PIPELINE_VERSION,
                rules_config_version=rules_version,
                status=rules_status,
            ),
            components=components,
            cache=CacheStatus(
                status="AVAILABLE" if summary.total_files else "UNAVAILABLE",
                freshness_status="UNVERIFIED",
                total_files=summary.total_files,
                total_symbols=summary.total_symbols,
                total_size_mb=summary.total_size_mb,
                periods=summary.periods,
                latest_modified_at=latest_modified,
            ),
            run_history=_read_run_history(database),
        )

    @router.get("/api/system/jobs/status", response_model=JobStatus)
    def system_job_status() -> JobStatus:
        try:
            task = task_status_provider()
        except Exception:
            return JobStatus(
                status="UNAVAILABLE",
                configured=False,
                task_name="SCANNER Overnight Workflow",
                scheduler_state="UNAVAILABLE",
            )
        status = "AVAILABLE" if task.exists else "UNAVAILABLE"
        return JobStatus(
            status=status,
            configured=task.exists,
            task_name=task.task_name,
            scheduler_state=task.state,
            last_run_at=task.last_run_time or None,
            next_run_at=task.next_run_time or None,
            last_result=task.last_task_result or None,
            last_result_label=task.last_task_result_label or None,
        )

    return router


def _read_run_history(database: Path, limit: int = 12) -> RunHistoryStatus:
    if not database.exists():
        return RunHistoryStatus(status="UNAVAILABLE")
    try:
        connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
        try:
            records = [
                *_pipeline_records(connection, limit),
                *_workflow_records(connection, limit),
                *_snapshot_records(connection, limit),
            ]
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return RunHistoryStatus(status="UNAVAILABLE")
    records.sort(key=lambda item: (item.created_at, item.run_id), reverse=True)
    return RunHistoryStatus(status="AVAILABLE" if records else "EMPTY", records=records[:limit])


def _pipeline_records(connection: sqlite3.Connection, limit: int) -> list[RunRecord]:
    if not _table_exists(connection, "pipeline_runs"):
        return []
    rows = connection.execute(
        """
        SELECT id, created_at, universe, candidates, cache_failures, scan_failures, auth_warning
        FROM pipeline_runs ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    records = []
    for row in rows:
        issues = int(row[4]) + int(row[5])
        status = "DEGRADED" if (row[6] not in (None, "") or issues) else "COMPLETED"
        records.append(RunRecord(
            run_type="PIPELINE",
            run_id=int(row[0]),
            created_at=str(row[1]),
            status=status,
            summary=f"{row[2]} · {int(row[3])} candidates · {issues} data issues",
        ))
    return records


def _workflow_records(connection: sqlite3.Connection, limit: int) -> list[RunRecord]:
    if not _table_exists(connection, "workflow_runs"):
        return []
    rows = connection.execute(
        "SELECT id, created_at, regime_label, risk_level FROM workflow_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [RunRecord(
        run_type="WORKFLOW",
        run_id=int(row[0]),
        created_at=str(row[1]),
        status="RECORDED",
        summary=f"Regime {row[2]} · risk {row[3]}",
    ) for row in rows]


def _snapshot_records(connection: sqlite3.Connection, limit: int) -> list[RunRecord]:
    if not _table_exists(connection, "command_center_snapshots"):
        return []
    rows = connection.execute(
        """
        SELECT id, created_at, universe, watchlist_count, option_ideas_count
        FROM command_center_snapshots ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [RunRecord(
        run_type="SNAPSHOT",
        run_id=int(row[0]),
        created_at=str(row[1]),
        status="RECORDED",
        summary=f"{row[2]} · {int(row[3])} watchlist · {int(row[4])} option ideas",
    ) for row in rows]


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _operational_component(item: object, cache_file_count: int) -> OperationalComponent:
    name = str(getattr(item, "name", "unknown"))
    status = str(getattr(item, "status", "UNAVAILABLE"))
    detail = getattr(item, "details", None)
    if name == "bar_cache" and cache_file_count == 0:
        return OperationalComponent(
            name=name,
            status="UNAVAILABLE",
            detail="No local bar-cache files are available.",
        )
    if name == "process_memory" and detail == "Memory check initialized.":
        return OperationalComponent(
            name=name,
            status="UNAVAILABLE",
            detail="Process-memory verification is unavailable.",
        )
    return OperationalComponent(name=name, status=status, detail=detail)
