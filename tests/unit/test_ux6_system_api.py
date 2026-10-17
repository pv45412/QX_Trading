from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qx.automation.morning import AutomationTaskStatus
from qx.interfaces.system_status import create_system_status_router
from qx.interfaces import system_status


def _client(
    tmp_path: Path,
    *,
    task_status_provider=lambda: AutomationTaskStatus(
        exists=True,
        task_name="SCANNER Overnight Workflow",
        state="Ready",
        last_run_time="2026-09-16T08:30:00Z",
        next_run_time="2026-09-17T08:30:00Z",
        last_task_result="0",
        last_task_result_label="Success",
        message="",
    ),
) -> TestClient:
    app = FastAPI()
    app.include_router(create_system_status_router(
        database=tmp_path / "qx.sqlite3",
        cache_dir=tmp_path / "cache",
        task_status_provider=task_status_provider,
    ))
    return TestClient(app)


def test_system_overview_reports_measured_cache_without_claiming_freshness(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "SPY_1y.csv").write_text("date,open,high,low,close,volume\n", encoding="utf-8")
    (cache / "QQQ_2y.csv").write_text("date,open,high,low,close,volume\n", encoding="utf-8")

    payload = _client(tmp_path).get("/api/system/overview").json()

    assert payload["pipeline"]["pipeline_version"] == "core_v1"
    assert payload["cache"]["status"] == "AVAILABLE"
    assert payload["cache"]["freshness_status"] == "UNVERIFIED"
    assert payload["cache"]["total_files"] == 2
    assert payload["cache"]["total_symbols"] == 2
    assert payload["cache"]["periods"] == {"1y": 1, "2y": 1}
    assert payload["run_history"] == {"status": "UNAVAILABLE", "records": []}


def test_empty_cache_cannot_report_healthy_overall_status(tmp_path: Path) -> None:
    (tmp_path / "cache").mkdir()

    payload = _client(tmp_path).get("/api/system/overview").json()

    cache_component = next(item for item in payload["components"] if item["name"] == "bar_cache")
    assert payload["status"] == "DEGRADED"
    assert payload["cache"]["status"] == "UNAVAILABLE"
    assert cache_component["status"] == "UNAVAILABLE"


def test_unverified_memory_check_is_not_reported_as_healthy(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "SPY_1y.csv").write_text("date,open,high,low,close,volume\n", encoding="utf-8")
    report = SimpleNamespace(
        status="OK",
        components=[SimpleNamespace(
            name="process_memory",
            status="OK",
            details="Memory check initialized.",
        )],
    )
    monkeypatch.setattr(system_status, "HealthChecker", lambda _cache_dir: SimpleNamespace(
        audit_system_health=lambda: report,
    ))

    payload = _client(tmp_path).get("/api/system/overview").json()

    assert payload["status"] == "DEGRADED"
    assert payload["components"][0]["status"] == "UNAVAILABLE"


def test_system_overview_reads_whitelisted_run_summaries_only(tmp_path: Path) -> None:
    database = tmp_path / "qx.sqlite3"
    secret = "must-not-leak"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE pipeline_runs (
                id INTEGER PRIMARY KEY, created_at TEXT, universe TEXT, candidates INTEGER,
                cache_failures INTEGER, scan_failures INTEGER, auth_warning TEXT, payload_json TEXT
            );
            CREATE TABLE workflow_runs (
                id INTEGER PRIMARY KEY, created_at TEXT, regime_label TEXT, risk_level TEXT,
                payload_json TEXT
            );
            CREATE TABLE command_center_snapshots (
                id INTEGER PRIMARY KEY, created_at TEXT, universe TEXT,
                watchlist_count INTEGER, option_ideas_count INTEGER, payload_json TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO pipeline_runs VALUES (1, ?, ?, 3, 0, 0, '', ?)",
            ("2026-09-16T15:00:00Z", "S&P 500", secret),
        )
        connection.execute(
            "INSERT INTO workflow_runs VALUES (2, ?, ?, ?, ?)",
            ("2026-09-16T14:00:00Z", "RANGE", "NORMAL", secret),
        )
        connection.execute(
            "INSERT INTO command_center_snapshots VALUES (3, ?, ?, 4, 2, ?)",
            ("2026-09-16T13:00:00Z", "SPY", secret),
        )

    response = _client(tmp_path).get("/api/system/overview")
    serialized = response.text
    payload = response.json()

    assert response.status_code == 200
    assert payload["run_history"]["status"] == "AVAILABLE"
    assert [record["run_type"] for record in payload["run_history"]["records"]] == [
        "PIPELINE", "WORKFLOW", "SNAPSHOT",
    ]
    assert secret not in serialized
    assert "payload_json" not in serialized


def test_null_auth_warning_does_not_degrade_completed_pipeline_run(tmp_path: Path) -> None:
    database = tmp_path / "qx.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE pipeline_runs (
                id INTEGER PRIMARY KEY, created_at TEXT, universe TEXT, candidates INTEGER,
                cache_failures INTEGER, scan_failures INTEGER, auth_warning TEXT, payload_json TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO pipeline_runs VALUES (1, ?, ?, 0, 0, 0, NULL, '{}')",
            ("2026-09-16T15:00:00Z", "SPY"),
        )

    payload = _client(tmp_path).get("/api/system/overview").json()

    assert payload["run_history"]["records"][0]["status"] == "COMPLETED"


def test_system_job_status_uses_existing_scheduler_provider(tmp_path: Path) -> None:
    payload = _client(tmp_path).get("/api/system/jobs/status").json()

    assert payload == {
        "status": "AVAILABLE",
        "configured": True,
        "task_name": "SCANNER Overnight Workflow",
        "scheduler_state": "Ready",
        "last_run_at": "2026-09-16T08:30:00Z",
        "next_run_at": "2026-09-17T08:30:00Z",
        "last_result": "0",
        "last_result_label": "Success",
    }


def test_system_job_status_fails_closed_without_fabricated_state(tmp_path: Path) -> None:
    def unavailable() -> AutomationTaskStatus:
        raise OSError("scheduler unavailable")

    payload = _client(tmp_path, task_status_provider=unavailable).get("/api/system/jobs/status").json()

    assert payload["status"] == "UNAVAILABLE"
    assert payload["configured"] is False
    assert payload["scheduler_state"] == "UNAVAILABLE"
    assert payload["last_run_at"] is None


def test_system_contract_never_exposes_sensitive_field_names(tmp_path: Path) -> None:
    serialized = _client(tmp_path).get("/api/system/overview").text.lower()

    for forbidden in ("client_secret", "access_token", "refresh_token", "account_number", "oauth_code"):
        assert forbidden not in serialized
