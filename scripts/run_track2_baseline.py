"""Measure the canonical V2 pipeline without changing runtime behavior."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from qx.config.rules_config import load_rules_config
from qx.data.cache import _read_cached_bars
from qx.data.dashboard_refresh import DashboardRefresh
from qx.interfaces.web import create_app
from qx.pipeline.adapters import HistoricalReplayAdapter
from qx.pipeline.models import PIPELINE_VERSION, QXEvaluationResult
from qx.pipeline.performance import (
    latency_distribution,
    replay_throughput,
    summarize_io_operations,
    summarize_stage_counters,
    summarize_stage_latencies,
)
from qx.pipeline.replay_analysis import analyze_historical_replay
from qx.pipeline.snapshot_store import CanonicalSnapshotRepository
from qx.storage.connection import connect_sqlite


DEFAULT_SYMBOLS = ("SPY", "QQQ", "SPX", "NVDA", "AAPL", "MSFT", "TSLA", "AMD", "JPM", "XOM")
DEFAULT_TIMEFRAMES = ("1m", "5m", "15m", "1d")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/scanner_history.db"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/bars"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/reports/track2c_performance.json")
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframes", nargs="+", default=list(DEFAULT_TIMEFRAMES))
    parser.add_argument("--cached-repetitions", type=int, default=3)
    parser.add_argument("--live-provider-repetitions", type=int, default=1)
    parser.add_argument(
        "--replay-bars",
        type=Path,
        default=Path("data/cache/bars/intraday/SPY_10d_5m.csv"),
    )
    parser.add_argument("--replay-max-bars", type=int, default=60)
    parser.add_argument(
        "--frontend-artifact",
        type=Path,
        default=Path("data/reports/track2c_frontend.json"),
    )
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    cached = _measure_api(
        database=args.database,
        cache_dir=args.cache_dir,
        symbols=args.symbols,
        timeframes=args.timeframes,
        repetitions=args.cached_repetitions,
        configure_providers=False,
    )
    live_workloads = [(symbol, "1d") for symbol in args.symbols]
    if "SPY" in {symbol.upper() for symbol in args.symbols}:
        live_workloads.append(("SPY", "5m"))
    live = _measure_api(
        database=args.database,
        cache_dir=args.cache_dir,
        symbols=[],
        timeframes=[],
        repetitions=args.live_provider_repetitions,
        configure_providers=True,
        workloads=live_workloads,
    )
    replay = _measure_replay(args.replay_bars, args.replay_max_bars)
    snapshot_store = _measure_snapshot_store(args.database, args.symbols)
    frontend = _summarize_frontend(_load_json(args.frontend_artifact))
    payload = {
        "track": "2C",
        "measurement_only": True,
        "pipeline_version": PIPELINE_VERSION,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "cached_api": _summarize_samples(cached),
        "live_provider_api": _summarize_samples(live),
        "replay": replay,
        "snapshot_store": snapshot_store,
        "frontend": frontend or {
            "status": "UNAVAILABLE",
            "reason": "FRONTEND_PERFORMANCE_ARTIFACT_NOT_FOUND",
        },
        "provisional_budgets_ms": {
            "cached_api_p95": 300.0,
            "live_api_p95": 1000.0,
            "frontend_interaction": 100.0,
            "gating": False,
        },
        "measurement_limitations": [
            "Python API latency uses in-process FastAPI TestClient and excludes network/server transport overhead.",
            "Successful external-provider latency is unavailable when configured read-only providers fail authentication.",
            "Intraday API samples backed by daily cache files are excluded as TIMEFRAME_SOURCE_MISMATCH.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cached_samples": len(cached),
                "live_samples": len(live),
            },
            indent=2,
        )
    )


def _measure_api(
    *,
    database: Path,
    cache_dir: Path,
    symbols: list[str],
    timeframes: list[str],
    repetitions: int,
    configure_providers: bool,
    workloads: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    if repetitions < 0:
        raise ValueError("Repetitions cannot be negative")
    app = create_app(
        database=database,
        cache_dir=cache_dir,
        configure_canonical_providers=configure_providers,
    )
    samples: list[dict[str, Any]] = []
    active_cache = DashboardRefresh(cache_dir, lambda: None).active_cache()
    selected = workloads or [(symbol, timeframe) for symbol in symbols for timeframe in timeframes]
    with TestClient(app) as client:
        for symbol, timeframe in selected:
            for repetition in range(repetitions):
                started = time.perf_counter()
                response = client.post(
                    f"/api/v2/qx/evaluate/{symbol}",
                    params={"timeframe": timeframe},
                )
                api_latency_ms = (time.perf_counter() - started) * 1000.0
                sample: dict[str, Any] = {
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                    "repetition": repetition + 1,
                    "api_latency_ms": api_latency_ms,
                    "status_code": response.status_code,
                    "source_semantics": _source_semantics(
                        cache_dir, active_cache, symbol, timeframe
                    ),
                }
                if response.status_code == 200:
                    result = QXEvaluationResult.model_validate(response.json())
                    sample["result"] = result
                else:
                    sample["error"] = response.text[:500]
                samples.append(sample)
    return samples


def _summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    results = [sample["result"] for sample in samples if "result" in sample]
    available_results = [
        sample["result"]
        for sample in samples
        if "result" in sample and _valid_input_sample(sample)
    ]
    workload_status: dict[str, str] = {}
    for sample in samples:
        key = f"{sample['symbol']}:{sample['timeframe']}"
        result = sample.get("result")
        bars = result.data_dependencies.get("bars") if result else None
        if not getattr(bars, "available", False):
            workload_status[key] = "UNAVAILABLE"
        elif sample["source_semantics"]["status"] != "MATCHED":
            workload_status[key] = sample["source_semantics"]["status"]
        else:
            workload_status[key] = "AVAILABLE"
    state_counts = Counter(
        result.current_lifecycle_state.value for result in results
    )
    api_values = [sample["api_latency_ms"] for sample in samples]
    available_api_values = [
        sample["api_latency_ms"]
        for sample in samples
        if "result" in sample and _valid_input_sample(sample)
    ]
    return {
        "sample_count": len(samples),
        "successful_responses": len(results),
        "available_input_samples": len(available_results),
        "api_latency_all": latency_distribution(api_values),
        "api_latency_available_inputs": latency_distribution(available_api_values),
        "pipeline_stages_available_inputs": summarize_stage_latencies(available_results),
        "pipeline_counters_available_inputs": summarize_stage_counters(available_results),
        "io_available_inputs": summarize_io_operations(available_results),
        "io_all_responses": summarize_io_operations(results),
        "successful_external_provider_samples": sum(
            1
            for result in results
            for metric in result.io_metrics
            if metric.source != "local_bar_cache" and metric.status == "OK"
        ),
        "lifecycle_counts": dict(sorted(state_counts.items())),
        "workload_status": dict(sorted(workload_status.items())),
        "data_quality_findings": sorted(
            {
                sample["source_semantics"]["status"]
                for sample in samples
                if sample["source_semantics"]["status"] != "MATCHED"
            }
        ),
        "samples": [
            {
                **{key: value for key, value in sample.items() if key != "result"},
                "lifecycle_state": (
                    sample["result"].current_lifecycle_state.value
                    if "result" in sample
                    else None
                ),
                "pipeline_version": (
                    sample["result"].pipeline_version if "result" in sample else None
                ),
                "stage_latencies": (
                    sample["result"].stage_latencies if "result" in sample else {}
                ),
                "io_metrics": (
                    [metric.model_dump(mode="json") for metric in sample["result"].io_metrics]
                    if "result" in sample
                    else []
                ),
            }
            for sample in samples
        ],
    }


def _measure_replay(path: Path, max_bars: int) -> dict[str, Any]:
    if not path.exists():
        return {"status": "UNAVAILABLE", "reason": "REPLAY_BARS_NOT_FOUND", "source": str(path)}
    bars = _read_cached_bars(path)
    if max_bars > 0 and len(bars) > max_bars:
        bars = bars.iloc[-max_bars:].copy()
    started = time.perf_counter()
    report = analyze_historical_replay(
        HistoricalReplayAdapter(load_rules_config(), "SPY", "5m"),
        bars,
        warmup_bars=min(50, max(len(bars) - 1, 0)),
    )
    elapsed = time.perf_counter() - started
    return {
        "status": "MEASURED",
        "source": str(path),
        "input_bars": len(bars),
        "transitions": len(report.transitions),
        "outcomes": len(report.outcomes),
        **replay_throughput(len(report.observations), elapsed),
    }


def _measure_snapshot_store(database: Path, symbols: list[str]) -> dict[str, Any]:
    repository = CanonicalSnapshotRepository(database)
    measured_at = datetime.now(timezone.utc)
    operations: list[dict[str, Any]] = []

    def measure(name: str, operation: Any) -> Any:
        started = time.perf_counter()
        try:
            value = operation()
            operations.append(
                {
                    "operation": name,
                    "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                    "status": "OK",
                    "sqlite_busy": False,
                }
            )
            return value
        except sqlite3.OperationalError as exc:
            busy = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            operations.append(
                {
                    "operation": name,
                    "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                    "status": "SQLITE_BUSY" if busy else "SQLITE_ERROR",
                    "sqlite_busy": busy,
                    "error_type": type(exc).__name__,
                }
            )
            return []

    measure("initialize_snapshot_store", repository.initialize)
    option_counts = {}
    for symbol in symbols:
        snapshots = measure(
            f"list_option_chains:{symbol.upper()}",
            lambda symbol=symbol: repository.list_option_chains(symbol, measured_at),
        )
        option_counts[symbol.upper()] = len(snapshots)
    accounts = measure("list_accounts", lambda: repository.list_accounts(measured_at))
    sqlite_settings: dict[str, Any] = {}
    started = time.perf_counter()
    try:
        with connect_sqlite(database) as connection:
            sqlite_settings = {
                "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
                "busy_timeout_ms": connection.execute("PRAGMA busy_timeout").fetchone()[0],
                "synchronous": connection.execute("PRAGMA synchronous").fetchone()[0],
            }
        operations.append(
            {
                "operation": "inspect_sqlite_settings",
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "status": "OK",
                "sqlite_busy": False,
            }
        )
    except sqlite3.OperationalError as exc:
        busy = "locked" in str(exc).lower() or "busy" in str(exc).lower()
        operations.append(
            {
                "operation": "inspect_sqlite_settings",
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "status": "SQLITE_BUSY" if busy else "SQLITE_ERROR",
                "sqlite_busy": busy,
                "error_type": type(exc).__name__,
            }
        )
    return {
        "operations": operations,
        "latency": latency_distribution(
            operation["elapsed_ms"] for operation in operations
        ),
        "sqlite_busy_observations": sum(
            1 for operation in operations if operation["sqlite_busy"]
        ),
        "sqlite_error_observations": sum(
            1 for operation in operations if operation["status"] == "SQLITE_ERROR"
        ),
        "option_snapshot_counts": option_counts,
        "account_snapshot_count": len(accounts),
        "sqlite_settings": sqlite_settings,
    }


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _summarize_frontend(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    result["v2_api_latency"] = latency_distribution(payload.get("v2_api_ms", ()))
    result["interaction_latency"] = latency_distribution(
        item["elapsed_ms"]
        for item in payload.get("interactions", ())
        if isinstance(item, dict) and "elapsed_ms" in item
    )
    result["fixture_render_latency"] = latency_distribution(
        item["actualDuration"]
        for item in payload.get("lifecycle_renders", ())
        if isinstance(item, dict) and "actualDuration" in item
    )
    result["live_render_latency"] = latency_distribution(
        item["actualDuration"]
        for item in payload.get("live_lifecycle_renders", ())
        if isinstance(item, dict) and "actualDuration" in item
    )
    return result


def _valid_input_sample(sample: dict[str, Any]) -> bool:
    result = sample["result"]
    return (
        getattr(result.data_dependencies.get("bars"), "available", False)
        and sample["source_semantics"]["status"] == "MATCHED"
    )


def _source_semantics(
    cache_dir: Path,
    active_cache_dir: Path,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    canonical_symbol = symbol.upper().replace("/", "_").replace("=", "_")
    directories = [active_cache_dir, cache_dir] if active_cache_dir != cache_dir else [cache_dir]
    selected = None
    for directory in directories:
        candidates = []
        if timeframe.endswith("m"):
            candidates.extend(
                [
                    directory / "intraday" / f"{canonical_symbol}_10d_{timeframe}.csv",
                    directory / "intraday" / f"{canonical_symbol}_5d_{timeframe}.csv",
                ]
            )
            candidates.extend(
                sorted((directory / "intraday").glob(f"{canonical_symbol}_*_{timeframe}.csv"))
            )
        candidates.extend(
            [
                directory / f"{canonical_symbol}_1y.csv",
                directory / f"{canonical_symbol}_year.csv",
                directory / f"{canonical_symbol}_2y.csv",
            ]
        )
        selected = next(
            (candidate for candidate in dict.fromkeys(candidates) if candidate.exists()),
            None,
        )
        if selected is not None:
            break
    if selected is None:
        return {"status": "SOURCE_UNAVAILABLE", "source": None}
    if timeframe.endswith("m"):
        return {
            "status": (
                "MATCHED"
                if selected.parent.name == "intraday" and selected.stem.endswith(f"_{timeframe}")
                else "TIMEFRAME_SOURCE_MISMATCH"
            ),
            "source": str(selected),
        }
    return {"status": "MATCHED", "source": str(selected)}


if __name__ == "__main__":
    main()
