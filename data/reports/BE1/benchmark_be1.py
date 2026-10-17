from __future__ import annotations

import json
import statistics
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qx.interfaces.opportunities import _deterministic_response
from qx.opportunities.identity import (
    command_identity,
    command_payload_hash,
    sha256_digest,
    stream_key,
)
from qx.opportunities.models import OpportunityRecord
from qx.opportunities.repository import OpportunityRepository
from qx.pipeline.models import LifecycleState


BASE = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(statistics.median(values), 4),
        "p95_ms": round(percentile(values, 0.95), 4),
        "p99_ms": round(percentile(values, 0.99), 4),
        "max_ms": round(max(values), 4),
    }


with tempfile.TemporaryDirectory() as directory:
    repository = OpportunityRepository(Path(directory) / "runtime.db")
    latest_id = ""
    for symbol_index in range(50):
        symbol = f"S{symbol_index:03d}"
        for observation_index in range(10):
            number = symbol_index * 10 + observation_index + 1
            evaluated_at = BASE + timedelta(minutes=observation_index)
            producer_run_id = f"benchmark-{number}"
            identity_values = {
                "environment_id": "benchmark",
                "producer_id": "benchmark",
                "producer_run_id": producer_run_id,
                "symbol": symbol,
                "timeframe": "5m",
            }
            key = command_identity(**identity_values)
            repository.reserve_command(
                idempotency_key=key,
                payload_hash=command_payload_hash(**identity_values),
                producer_id="benchmark",
                producer_run_id=producer_run_id,
                now=evaluated_at - timedelta(seconds=1),
            )
            request_started_at = evaluated_at - timedelta(seconds=2)
            dependencies = {
                "bars": {
                    "data_as_of": evaluated_at.isoformat(),
                    "retrieved_at": (evaluated_at - timedelta(seconds=1)).isoformat(),
                    "content_sha256": "b" * 64,
                }
            }
            decision = {
                "symbol": symbol,
                "timeframe": "5m",
                "evaluation_timestamp": evaluated_at.isoformat(),
                "request_started_at": request_started_at.isoformat(),
                "publication_state": "RESEARCH_ONLY",
                "current_lifecycle_state": "ARMED",
                "evidence_summary": [],
                "reason_codes": [],
                "config_version": "research_v1",
                "pipeline_version": "core_v1",
                "engine_versions": {},
                "stage_latencies": {},
                "data_dependencies": dependencies,
            }
            latest_id = f"qxev1_{number:032x}"
            repository.commit_record(
                OpportunityRecord(
                    evaluation_id=latest_id,
                    idempotency_key=key,
                    environment_id="benchmark",
                    producer_id="benchmark",
                    producer_run_id=producer_run_id,
                    symbol=symbol,
                    timeframe="5m",
                    evaluation_timestamp=evaluated_at,
                    request_started_at=request_started_at,
                    recorded_at=evaluated_at + timedelta(seconds=1),
                    expires_at=BASE + timedelta(days=1),
                    freshness_policy_version="benchmark_v1",
                    publication_state="RESEARCH_ONLY",
                    lifecycle_state=LifecycleState.ARMED,
                    pipeline_version="core_v1",
                    config_version="research_v1",
                    direction="BULLISH",
                    reason_codes=[],
                    data_dependencies=dependencies,
                    decision_payload=decision,
                    input_fingerprint=sha256_digest({"input": number}),
                    bar_window_sha256=sha256_digest({"bars": number}),
                    result_sha256=sha256_digest(
                        {"schema_version": "qx.opportunity-decision.v1", "decision": decision}
                    ),
                    stream_key=stream_key(
                        environment_id="benchmark",
                        observation_mode="LIVE",
                        symbol=symbol,
                        timeframe="5m",
                        pipeline_version="core_v1",
                        config_version="research_v1",
                    ),
                )
            )

    query_as_of = BASE + timedelta(minutes=30)
    list_samples = []
    detail_samples = []
    serialization_samples = []
    for _ in range(300):
        started = time.perf_counter()
        response = repository.list_latest(
            environment_id="benchmark",
            query_as_of=query_as_of,
            limit=25,
        )
        list_samples.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        detail = repository.get_detail(latest_id, environment_id="benchmark")
        detail_samples.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        _deterministic_response(response.model_dump(mode="json"), None)
        serialization_samples.append((time.perf_counter() - started) * 1000)

    report = {
        "schema_version": "qx.be1-performance.v1",
        "records": 500,
        "streams": 50,
        "iterations": 300,
        "list_latest_25": summarize(list_samples),
        "detail_by_id": summarize(detail_samples),
        "list_response_serialization_etag": summarize(serialization_samples),
        "result": "OBSERVATIONAL_ONLY",
    }
    Path("data/reports/BE1/performance.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
