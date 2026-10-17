"""Deterministic aggregate analysis for persisted canonical shadow observations."""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

from pydantic import BaseModel, Field

from qx.pipeline.performance import latency_distribution
from qx.pipeline.shadow_telemetry import ShadowTelemetryRecord


class ShadowAnalysis(BaseModel):
    total_observations: int
    lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    transition_counts: dict[str, int] = Field(default_factory=dict)
    playbook_counts: dict[str, int] = Field(default_factory=dict)
    trend_regime_counts: dict[str, int] = Field(default_factory=dict)
    direction_counts: dict[str, int] = Field(default_factory=dict)
    agreement_counts: dict[str, int] = Field(default_factory=dict)
    reason_code_counts: dict[str, int] = Field(default_factory=dict)
    evidence_coverage_counts: dict[str, int] = Field(default_factory=dict)
    freshness_counts: dict[str, int] = Field(default_factory=dict)
    bar_data_age_seconds: dict[str, float | int | None] = Field(default_factory=dict)
    bar_data_age_bucket_counts: dict[str, int] = Field(default_factory=dict)
    pipeline_versions: dict[str, int] = Field(default_factory=dict)
    stage_latency: dict[str, dict[str, float | int | None]] = Field(default_factory=dict)
    io_counter_totals: dict[str, float | int | None] = Field(default_factory=dict)
    point_in_time_violation_count: int = 0
    error_observations: int = 0
    market_driver_status_counts: dict[str, int] = Field(default_factory=dict)
    driver_counts: dict[str, int] = Field(default_factory=dict)
    driver_strength_counts: dict[str, int] = Field(default_factory=dict)
    driver_coverage_counts: dict[str, int] = Field(default_factory=dict)
    driver_persistence_state_counts: dict[str, int] = Field(default_factory=dict)
    driver_transitions: dict[str, int] = Field(default_factory=dict)
    driver_flips_count: int = 0
    driver_vs_regime_counts: dict[str, int] = Field(default_factory=dict)
    driver_vs_direction_counts: dict[str, int] = Field(default_factory=dict)
    driver_vs_lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    driver_unavailable_causes: dict[str, int] = Field(default_factory=dict)


def analyze_shadow_records(records: Sequence[ShadowTelemetryRecord]) -> ShadowAnalysis:
    ordered = sorted(
        records,
        key=lambda record: (
            record.symbol,
            record.timeframe,
            record.evaluation_timestamp,
            record.created_at,
        ),
    )
    lifecycle = Counter(_bucket(record.v2_lifecycle_state) for record in ordered)
    playbooks = Counter(_bucket(record.v2_primary_playbook) for record in ordered)
    regimes = Counter(_bucket(record.trend_regime) for record in ordered)
    directions = Counter(_bucket(record.direction_label) for record in ordered)
    agreements = Counter(record.agreement_status for record in ordered)
    reason_codes = Counter(code for record in ordered for code in record.v2_reason_codes)
    coverage = Counter(_bucket(record.coverage_status) for record in ordered)
    versions = Counter(record.pipeline_version for record in ordered)
    freshness = Counter()
    bar_ages: list[float] = []
    age_buckets = Counter()
    stage_samples: dict[str, list[float]] = {}
    stage_skipped: Counter[str] = Counter()
    io_counters: Counter[str] = Counter()
    point_in_time_violations = 0
    transitions = Counter()
    prior_by_series: dict[tuple[str, str], str] = {}

    md_statuses = Counter(_bucket(record.market_driver_status) for record in ordered)
    driver_counts = Counter(_bucket(record.primary_driver) for record in ordered)
    strength_counts = Counter(_bucket(record.driver_strength) for record in ordered)
    driver_coverage_counts = Counter(_bucket(record.driver_coverage_status) for record in ordered)
    persistence_counts = Counter(_bucket(record.driver_persistence_state) for record in ordered)
    driver_transitions = Counter()
    driver_flips = 0
    prior_driver_by_series: dict[tuple[str, str], str] = {}
    driver_vs_regime = Counter()
    driver_vs_direction = Counter()
    driver_vs_lifecycle = Counter()
    driver_unavailable_causes = Counter()

    for record in ordered:
        series = (record.symbol, record.timeframe)
        state = _bucket(record.v2_lifecycle_state)
        prior = prior_by_series.get(series)
        if prior is not None and prior != state:
            transitions[f"{prior}->{state}"] += 1
        prior_by_series[series] = state

        drv = _bucket(record.primary_driver)
        prior_drv = prior_driver_by_series.get(series)
        if prior_drv is not None and prior_drv != drv:
            driver_transitions[f"{prior_drv}->{drv}"] += 1
            if prior_drv != "UNAVAILABLE" and drv != "UNAVAILABLE":
                driver_flips += 1
        prior_driver_by_series[series] = drv

        driver_vs_regime[f"{drv}:{_bucket(record.trend_regime)}"] += 1
        driver_vs_direction[f"{drv}:{_bucket(record.direction_label)}"] += 1
        driver_vs_lifecycle[f"{drv}:{state}"] += 1

        md_stat = _bucket(record.market_driver_status)
        if md_stat in {"UNAVAILABLE", "BLOCKED"}:
            cause = _bucket(record.driver_coverage_status)
            driver_unavailable_causes[f"{md_stat}:{cause}"] += 1

        for name, dependency in record.data_freshness.items():
            if isinstance(dependency, dict) and not dependency.get("available", False):
                value = "UNAVAILABLE"
            else:
                value = dependency.get("freshness") if isinstance(dependency, dict) else dependency
            freshness[f"{name}:{_bucket(value)}"] += 1
        if record.data_as_of is not None:
            age_seconds = (
                record.evaluation_timestamp - record.data_as_of
            ).total_seconds()
            if age_seconds < 0:
                point_in_time_violations += 1
                age_buckets["FUTURE_DATA_AS_OF"] += 1
            else:
                bar_ages.append(age_seconds)
                age_buckets[_age_bucket(age_seconds)] += 1
        for stage, value in record.stage_latencies.items():
            if stage in {"cache_hits", "cache_misses"}:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    io_counters[stage] += value
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                stage_samples.setdefault(stage, []).append(float(value))
            else:
                stage_skipped[stage] += 1

    stage_names = sorted(set(stage_samples) | set(stage_skipped))
    stage_latency = {}
    for stage in stage_names:
        summary = latency_distribution(stage_samples.get(stage, ()))
        summary["skipped"] = stage_skipped[stage]
        stage_latency[stage] = summary

    return ShadowAnalysis(
        total_observations=len(ordered),
        lifecycle_counts=dict(sorted(lifecycle.items())),
        transition_counts=dict(sorted(transitions.items())),
        playbook_counts=dict(sorted(playbooks.items())),
        trend_regime_counts=dict(sorted(regimes.items())),
        direction_counts=dict(sorted(directions.items())),
        agreement_counts=dict(sorted(agreements.items())),
        reason_code_counts=dict(sorted(reason_codes.items())),
        evidence_coverage_counts=dict(sorted(coverage.items())),
        freshness_counts=dict(sorted(freshness.items())),
        bar_data_age_seconds=_seconds_distribution(bar_ages),
        bar_data_age_bucket_counts=dict(sorted(age_buckets.items())),
        pipeline_versions=dict(sorted(versions.items())),
        stage_latency=stage_latency,
        io_counter_totals=dict(sorted(io_counters.items())),
        point_in_time_violation_count=point_in_time_violations,
        error_observations=sum(
            1 for record in ordered if record.legacy_error or record.v2_error
        ),
        market_driver_status_counts=dict(sorted(md_statuses.items())),
        driver_counts=dict(sorted(driver_counts.items())),
        driver_strength_counts=dict(sorted(strength_counts.items())),
        driver_coverage_counts=dict(sorted(driver_coverage_counts.items())),
        driver_persistence_state_counts=dict(sorted(persistence_counts.items())),
        driver_transitions=dict(sorted(driver_transitions.items())),
        driver_flips_count=driver_flips,
        driver_vs_regime_counts=dict(sorted(driver_vs_regime.items())),
        driver_vs_direction_counts=dict(sorted(driver_vs_direction.items())),
        driver_vs_lifecycle_counts=dict(sorted(driver_vs_lifecycle.items())),
        driver_unavailable_causes=dict(sorted(driver_unavailable_causes.items())),
    )


def _bucket(value: Any) -> str:
    if value is None or value == "":
        return "UNAVAILABLE"
    return str(getattr(value, "value", value))


def _age_bucket(seconds: float) -> str:
    if seconds <= 300:
        return "LE_5_MINUTES"
    if seconds <= 3600:
        return "LE_1_HOUR"
    if seconds <= 86_400:
        return "LE_1_DAY"
    if seconds <= 604_800:
        return "LE_7_DAYS"
    return "GT_7_DAYS"


def _seconds_distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    latency = latency_distribution(values)
    return {
        key.replace("_ms", "_seconds"): value
        for key, value in latency.items()
    }
