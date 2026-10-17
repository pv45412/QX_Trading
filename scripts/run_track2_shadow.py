"""Collect and persist non-executing canonical live shadow observations."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from qx.config.rules_config import load_rules_config
from qx.interfaces.web import create_app
from qx.pipeline.models import PIPELINE_VERSION, QXEvaluationResult
from qx.pipeline.shadow_analysis import analyze_shadow_records
from qx.pipeline.shadow_telemetry import (
    ShadowTelemetryRecord,
    ShadowTelemetryRepository,
    build_shadow_record,
)


DEFAULT_SYMBOLS = ("SPY", "QQQ", "SPX", "NVDA", "AAPL", "MSFT", "TSLA", "AMD", "JPM", "XOM")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/scanner_history.db"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/bars"))
    parser.add_argument("--output", type=Path, default=Path("data/reports/track2e_shadow.json"))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--history-limit", type=int, default=5000)
    args = parser.parse_args()
    if args.cycles < 1:
        raise ValueError("At least one observation cycle is required")

    config = load_rules_config()
    approved_symbols = [
        symbol.upper() for symbol in args.symbols if config.shadow_mode.includes(symbol)
    ]
    repository = ShadowTelemetryRepository(args.database)
    app = create_app(database=args.database, cache_dir=args.cache_dir)
    batch: list[ShadowTelemetryRecord] = []
    started_at = datetime.now(timezone.utc)

    with TestClient(app) as client:
        for cycle in range(args.cycles):
            for symbol in approved_symbols:
                batch.append(_observe(client, repository, symbol, "1d", config.version))

    persisted = repository.list_records(symbols=approved_symbols, limit=args.history_limit)
    cumulative = [record for record in persisted if record.timeframe == "1d"]
    payload: dict[str, Any] = {
        "track": "2E",
        "execution_enabled": False,
        "pipeline_version": PIPELINE_VERSION,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "approved_symbols": approved_symbols,
        "observation_timeframes": ["1d"],
        "cycles": args.cycles,
        "excluded_non_daily_persisted_records": len(persisted) - len(cumulative),
        "batch_analysis": analyze_shadow_records(batch).model_dump(mode="json"),
        "cumulative_analysis": analyze_shadow_records(cumulative).model_dump(mode="json"),
        "batch_observations": [record.model_dump(mode="json") for record in batch],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "observations": len(batch)}, indent=2))


def _observe(
    client: TestClient,
    repository: ShadowTelemetryRepository,
    symbol: str,
    timeframe: str,
    config_version: str,
) -> ShadowTelemetryRecord:
    started = time.perf_counter()
    response = client.post(f"/api/v2/qx/evaluate/{symbol}", params={"timeframe": timeframe})
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    result = None
    error = None
    evaluation_timestamp = datetime.now(timezone.utc)
    if response.status_code == 200:
        result = QXEvaluationResult.model_validate(response.json())
        evaluation_timestamp = result.evaluation_timestamp
    else:
        error = f"HTTP_{response.status_code}: {response.text[:300]}"
    record = build_shadow_record(
        symbol=symbol,
        timeframe=timeframe,
        evaluation_timestamp=evaluation_timestamp,
        legacy_result=None,
        legacy_latency_ms=None,
        v2_result=result,
        v2_latency_ms=elapsed_ms,
        config_version=config_version,
        v2_error=error,
    )
    repository.write(record)
    return record


if __name__ == "__main__":
    main()
