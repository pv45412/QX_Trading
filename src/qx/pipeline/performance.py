"""Observational latency summaries for the canonical QX pipeline."""

from __future__ import annotations

import math
from collections import Counter
from statistics import fmean
from typing import Any, Iterable, Sequence

from qx.pipeline.models import QXEvaluationResult, SKIPPED


_COUNTER_KEYS = {"cache_hits", "cache_misses"}


def latency_distribution(values: Iterable[float | int]) -> dict[str, float | int | None]:
    samples = sorted(float(value) for value in values if _finite_number(value))
    if not samples:
        return {
            "count": 0,
            "min_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
            "mean_ms": None,
        }
    return {
        "count": len(samples),
        "min_ms": samples[0],
        "p50_ms": _percentile(samples, 0.50),
        "p95_ms": _percentile(samples, 0.95),
        "p99_ms": _percentile(samples, 0.99),
        "max_ms": samples[-1],
        "mean_ms": fmean(samples),
    }


def summarize_stage_latencies(
    results: Sequence[QXEvaluationResult],
) -> dict[str, dict[str, float | int | None]]:
    stage_names = sorted(
        {
            stage
            for result in results
            for stage in result.stage_latencies
            if stage not in _COUNTER_KEYS
        }
    )
    summary: dict[str, dict[str, float | int | None]] = {}
    for stage in stage_names:
        values: list[float] = []
        skipped = 0
        for result in results:
            value = result.stage_latencies.get(stage, SKIPPED)
            if value == SKIPPED or value is None:
                skipped += 1
            elif _finite_number(value):
                values.append(float(value))
        distribution = latency_distribution(values)
        distribution["skipped"] = skipped
        summary[stage] = distribution
    return summary


def summarize_stage_counters(results: Sequence[QXEvaluationResult]) -> dict[str, Any]:
    summary = {}
    for name in sorted(_COUNTER_KEYS):
        values = [
            float(result.stage_latencies[name])
            for result in results
            if _finite_number(result.stage_latencies.get(name))
        ]
        summary[name] = {
            "samples": len(values),
            "total": sum(values),
            "mean_per_evaluation": fmean(values) if values else None,
        }
    return summary


def summarize_io_operations(results: Sequence[QXEvaluationResult]) -> dict[str, Any]:
    operation_samples: dict[str, list[float]] = {}
    calls: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    for result in results:
        for metric in result.io_metrics:
            key = f"{metric.source}:{metric.operation}"
            operation_samples.setdefault(key, []).append(metric.elapsed_ms)
            calls[key] += metric.calls
            statuses[f"{key}:{metric.status}"] += 1
    return {
        "operations": {
            key: {
                **latency_distribution(values),
                "calls": calls[key],
            }
            for key, values in sorted(operation_samples.items())
        },
        "status_counts": dict(sorted(statuses.items())),
    }


def replay_throughput(
    observation_count: int,
    elapsed_seconds: float,
) -> dict[str, float | int | None]:
    return {
        "observations": observation_count,
        "elapsed_seconds": elapsed_seconds,
        "observations_per_second": (
            observation_count / elapsed_seconds if elapsed_seconds > 0 else None
        ),
    }


def _percentile(sorted_values: Sequence[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("A percentile requires at least one value")
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("Percentile must be between zero and one")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
