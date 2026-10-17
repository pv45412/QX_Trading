from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from qx.models.rules import PublicationState
from qx.pipeline.models import (
    DataDependencyStatus,
    LifecycleState,
    QXEvaluationResult,
    SKIPPED,
)
from qx.pipeline.performance import (
    latency_distribution,
    replay_throughput,
    summarize_io_operations,
    summarize_stage_counters,
    summarize_stage_latencies,
)
from qx.pipeline.shadow_analysis import analyze_shadow_records
from qx.pipeline.shadow_telemetry import (
    ShadowTelemetryRecord,
    ShadowTelemetryRepository,
    build_shadow_record,
)


NOW = datetime(2026, 9, 16, 14, 30, tzinfo=timezone.utc)


def _result(state: LifecycleState = LifecycleState.NO_SETUP) -> QXEvaluationResult:
    return QXEvaluationResult.model_construct(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=NOW,
        request_started_at=NOW - timedelta(milliseconds=25),
        publication_state=PublicationState.RESEARCH_ONLY,
        structure=SimpleNamespace(regime="BULLISH"),
        market_regime=SimpleNamespace(
            trend="TRENDING",
            volatility="NORMAL",
            gamma="UNAVAILABLE",
            session="RTH",
        ),
        direction=SimpleNamespace(
            direction_label="LONG",
            direction_score=0.7,
            direction_evidence_coverage=0.8,
            coverage_status="SUFFICIENT",
        ),
        playbooks=[],
        primary_playbook_candidate=SimpleNamespace(
            playbook_id="BREAKOUT",
            state="WATCH",
        ),
        trigger=None,
        tradeability=None,
        options_expression=SimpleNamespace(state="UNAVAILABLE"),
        portfolio_risk=SimpleNamespace(state="UNAVAILABLE"),
        current_lifecycle_state=state,
        evidence_summary=[],
        reason_codes=["OBSERVATION_ONLY"],
        config_version="research_v1",
        pipeline_version="core_v1",
        engine_versions={"structure": "v3"},
        stage_latencies={
            "structure_ms": 2.0,
            "trigger_ms": SKIPPED,
            "total_ms": 5.0,
            "cache_hits": 1,
            "cache_misses": 0,
        },
        data_dependencies={
            "bars": DataDependencyStatus(
                name="bars",
                available=True,
                source="local_bar_cache",
                data_as_of=NOW - timedelta(minutes=5),
                freshness="POINT_IN_TIME",
                publication_state="RESEARCH_ONLY",
                sync_status="SYNCED",
                cache_status="HIT",
            )
        },
        io_metrics=[],
    )


def test_latency_distribution_reports_linear_percentiles() -> None:
    summary = latency_distribution([1, 2, 3, 4, 5])

    assert summary["p50_ms"] == 3.0
    assert summary["p95_ms"] == pytest.approx(4.8)
    assert summary["p99_ms"] == pytest.approx(4.96)


def test_stage_summary_marks_skipped_without_zero_latency() -> None:
    first = _result()
    second = _result()
    second.stage_latencies = {"structure_ms": 4.0, "trigger_ms": SKIPPED, "total_ms": 8.0}

    summary = summarize_stage_latencies([first, second])

    assert summary["trigger_ms"]["count"] == 0
    assert summary["trigger_ms"]["skipped"] == 2
    assert summary["trigger_ms"]["p50_ms"] is None
    assert summary["structure_ms"]["p50_ms"] == 3.0
    assert "cache_hits" not in summary
    assert summarize_stage_counters([first, second])["cache_hits"]["total"] == 1.0


def test_io_summary_and_replay_throughput_are_observational() -> None:
    result = _result()
    result.io_metrics = [
        SimpleNamespace(
            source="schwab",
            operation="acquire_option_chain",
            elapsed_ms=10.0,
            calls=1,
            status="UNAVAILABLE",
        )
    ]

    summary = summarize_io_operations([result])

    assert summary["operations"]["schwab:acquire_option_chain"]["calls"] == 1
    assert summary["operations"]["schwab:acquire_option_chain"]["p50_ms"] == 10.0
    assert replay_throughput(10, 2.0)["observations_per_second"] == 5.0


def test_shadow_record_preserves_canonical_observation_fields() -> None:
    record = build_shadow_record(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=NOW,
        legacy_result=None,
        legacy_latency_ms=None,
        v2_result=_result(LifecycleState.WATCH),
        v2_latency_ms=12.0,
        config_version="research_v1",
    )

    assert record.pipeline_version == "core_v1"
    assert record.v2_lifecycle_state == "WATCH"
    assert record.structure_state == "BULLISH"
    assert record.trend_regime == "TRENDING"
    assert record.direction_label == "LONG"
    assert record.playbook_state == "WATCH"
    assert record.evidence_coverage == 0.8
    assert record.data_as_of == NOW - timedelta(minutes=5)
    assert record.stage_latencies["trigger_ms"] == SKIPPED


def test_shadow_repository_migrates_and_round_trips_observation_fields(tmp_path) -> None:
    repository = ShadowTelemetryRepository(tmp_path / "shadow.db")
    record = build_shadow_record(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=NOW,
        legacy_result=None,
        legacy_latency_ms=None,
        v2_result=_result(),
        v2_latency_ms=12.0,
        config_version="research_v1",
    )

    repository.write(record)
    stored = repository.list_records(symbols=["spy"], limit=10)

    assert len(stored) == 1
    assert stored[0].data_freshness["bars"]["freshness"] == "POINT_IN_TIME"
    assert stored[0].stage_latencies["trigger_ms"] == SKIPPED
    assert stored[0].pipeline_version == "core_v1"


def test_shadow_analysis_counts_lifecycle_transitions_without_manufacturing_states() -> None:
    states = [LifecycleState.NO_SETUP, LifecycleState.WATCH, LifecycleState.ARMED]
    records = []
    for index, state in enumerate(states):
        result = _result(state)
        result.evaluation_timestamp = NOW + timedelta(minutes=index * 5)
        records.append(
            build_shadow_record(
                symbol="SPY",
                timeframe="5m",
                evaluation_timestamp=result.evaluation_timestamp,
                legacy_result=None,
                legacy_latency_ms=None,
                v2_result=result,
                v2_latency_ms=10.0,
                config_version="research_v1",
            )
        )

    analysis = analyze_shadow_records(records)

    assert analysis.total_observations == 3
    assert analysis.transition_counts == {"NO_SETUP->WATCH": 1, "WATCH->ARMED": 1}
    assert analysis.lifecycle_counts == {"ARMED": 1, "NO_SETUP": 1, "WATCH": 1}
    assert analysis.pipeline_versions == {"core_v1": 3}
    assert analysis.bar_data_age_seconds["p50_seconds"] == 600.0
    assert analysis.bar_data_age_bucket_counts == {"LE_1_HOUR": 2, "LE_5_MINUTES": 1}
    assert analysis.io_counter_totals == {"cache_hits": 3.0, "cache_misses": 0.0}


def test_shadow_analysis_exposes_unavailable_and_future_bar_data() -> None:
    unavailable = build_shadow_record(
        symbol="SPX",
        timeframe="1d",
        evaluation_timestamp=NOW,
        legacy_result=None,
        legacy_latency_ms=None,
        v2_result=_result(LifecycleState.BLOCKED),
        v2_latency_ms=1.0,
        config_version="research_v1",
    )
    unavailable.data_as_of = None
    unavailable.data_freshness["bars"]["available"] = False
    future = unavailable.model_copy(
        update={
            "symbol": "SPY",
            "data_as_of": NOW + timedelta(minutes=1),
            "data_freshness": {
                "bars": {
                    "available": True,
                    "freshness": "POINT_IN_TIME",
                }
            },
        }
    )

    analysis = analyze_shadow_records([unavailable, future])

    assert analysis.freshness_counts["bars:UNAVAILABLE"] == 1
    assert analysis.bar_data_age_bucket_counts == {"FUTURE_DATA_AS_OF": 1}
    assert analysis.point_in_time_violation_count == 1
    assert analysis.bar_data_age_seconds["count"] == 0


def test_shadow_analysis_aggregates_market_driver_telemetry() -> None:
    rec1 = ShadowTelemetryRecord(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=NOW,
        agreement_status="AGREEMENT",
        publication_state="RESEARCH_ONLY",
        config_version="research_v1",
        pipeline_version="core_v1",
        trend_regime="TRENDING",
        direction_label="LONG",
        v2_lifecycle_state="WATCH",
        market_driver_status="AVAILABLE",
        primary_driver="INDEX_RISK_ON",
        driver_strength="STRONG",
        driver_persistence_state="ESTABLISHED",
        driver_coverage_status="COMPLETE",
    )
    rec2 = ShadowTelemetryRecord(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=NOW + timedelta(minutes=5),
        agreement_status="AGREEMENT",
        publication_state="RESEARCH_ONLY",
        config_version="research_v1",
        pipeline_version="core_v1",
        trend_regime="TRENDING",
        direction_label="LONG",
        v2_lifecycle_state="ARMED",
        market_driver_status="AVAILABLE",
        primary_driver="SECTOR_LEADERSHIP",
        driver_strength="MODERATE",
        driver_persistence_state="REPLACED",
        driver_coverage_status="COMPLETE",
    )
    rec3 = ShadowTelemetryRecord(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=NOW + timedelta(minutes=10),
        agreement_status="AGREEMENT",
        publication_state="RESEARCH_ONLY",
        config_version="research_v1",
        pipeline_version="core_v1",
        trend_regime="TRENDING",
        direction_label="LONG",
        v2_lifecycle_state="ARMED",
        market_driver_status="UNAVAILABLE",
        primary_driver="UNAVAILABLE",
        driver_strength="UNAVAILABLE",
        driver_persistence_state="CLEARED",
        driver_coverage_status="INSUFFICIENT",
    )

    analysis = analyze_shadow_records([rec1, rec2, rec3])

    assert analysis.market_driver_status_counts == {"AVAILABLE": 2, "UNAVAILABLE": 1}
    assert analysis.driver_counts == {"INDEX_RISK_ON": 1, "SECTOR_LEADERSHIP": 1, "UNAVAILABLE": 1}
    assert analysis.driver_strength_counts == {"MODERATE": 1, "STRONG": 1, "UNAVAILABLE": 1}
    assert analysis.driver_coverage_counts == {"COMPLETE": 2, "INSUFFICIENT": 1}
    assert analysis.driver_flips_count == 1
    assert analysis.driver_transitions == {"INDEX_RISK_ON->SECTOR_LEADERSHIP": 1, "SECTOR_LEADERSHIP->UNAVAILABLE": 1}
    assert analysis.driver_vs_regime_counts["INDEX_RISK_ON:TRENDING"] == 1
    assert analysis.driver_vs_direction_counts["SECTOR_LEADERSHIP:LONG"] == 1
    assert analysis.driver_vs_lifecycle_counts["INDEX_RISK_ON:WATCH"] == 1
    assert analysis.driver_unavailable_causes == {"UNAVAILABLE:INSUFFICIENT": 1}

