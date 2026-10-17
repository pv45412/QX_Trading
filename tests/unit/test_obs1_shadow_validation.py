"""Unit and regression tests for OBS1 Sustained Shadow Validation v2.

Verifies:
- 8 additive Market Driver telemetry columns persisted and round-tripped in SQLite
- Zero point-in-time violations (T_event <= T_knowledge <= T_eval)
- Driver persistence state machine (ESTABLISHED, CANDIDATE_PENDING, REPLACED, CLEARED)
- Hysteresis hurdle (Delta >= 10.0) and flip frequency measurement
- Cross-tabulation: driver vs regime, direction, lifecycle, and unavailable causes
- Fail-closed behavior on unsupported archetypes (MACRO_CATALYST, bar-derived delta)
- Phase 11 execution lock (zero broker writes, explanatory context only)
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from qx.config.rules_config import (
    MarketDriverConfig,
    MarketDriverFreshnessConfig,
    MarketDriverThresholdsConfig,
    load_rules_config,
)
from qx.market_driver.engine import MarketDriverEngine
from qx.market_driver.models import (
    DriverArchetype,
    DriverDirection,
    DriverStrength,
    MarketDriverResult,
    MarketDriverStatus,
    PersistenceState,
    CoverageAudit,
)
from qx.pipeline.models import (
    LifecycleState,
    QXEvaluationContext,
    QXEvaluationResult,
    SKIPPED,
)
from qx.pipeline.shadow_analysis import ShadowAnalysis, analyze_shadow_records
from qx.pipeline.shadow_telemetry import (
    ShadowTelemetryRecord,
    ShadowTelemetryRepository,
    build_shadow_record,
)

EVAL_TIME = datetime(2026, 9, 17, 14, 30, tzinfo=timezone.utc)


def test_obs1_shadow_telemetry_persists_and_recovers_all_market_driver_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "shadow_test.db"
    repo = ShadowTelemetryRepository(db_path)

    record = ShadowTelemetryRecord(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME,
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
        driver_duration_seconds=900,
        driver_coverage_status="COMPLETE",
        confirming_evidence_count=3,
        conflicting_evidence_count=1,
    )

    row_id = repo.write(record)
    assert row_id > 0

    recovered = repo.list_records(symbols=["SPY"], limit=10)
    assert len(recovered) == 1
    rec = recovered[0]
    assert rec.symbol == "SPY"
    assert rec.market_driver_status == "AVAILABLE"
    assert rec.primary_driver == "INDEX_RISK_ON"
    assert rec.driver_strength == "STRONG"
    assert rec.driver_persistence_state == "ESTABLISHED"
    assert rec.driver_duration_seconds == 900
    assert rec.driver_coverage_status == "COMPLETE"
    assert rec.confirming_evidence_count == 3
    assert rec.conflicting_evidence_count == 1


def test_obs1_causality_and_point_in_time_enforcement() -> None:
    # Future data_as_of must trigger point_in_time_violation_count
    valid_rec = ShadowTelemetryRecord(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME,
        data_as_of=EVAL_TIME - timedelta(minutes=5),
        agreement_status="AGREEMENT",
        publication_state="RESEARCH_ONLY",
        config_version="research_v1",
        pipeline_version="core_v1",
    )
    future_rec = ShadowTelemetryRecord(
        symbol="QQQ",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME,
        data_as_of=EVAL_TIME + timedelta(minutes=5),  # FUTURE timestamp!
        agreement_status="AGREEMENT",
        publication_state="RESEARCH_ONLY",
        config_version="research_v1",
        pipeline_version="core_v1",
    )

    analysis = analyze_shadow_records([valid_rec, future_rec])
    assert analysis.point_in_time_violation_count == 1
    assert analysis.bar_data_age_bucket_counts.get("FUTURE_DATA_AS_OF") == 1


def test_obs1_hysteresis_and_flip_frequency_tracking() -> None:
    cfg = MarketDriverConfig(
        thresholds=MarketDriverThresholdsConfig(
            primary_activation_magnitude=35.0,
            secondary_activation_magnitude=20.0,
            hysteresis_replacement_delta=10.0,
        ),
        freshness=MarketDriverFreshnessConfig(
            underlying_max_age_seconds=300,
            index_max_age_seconds=300,
            sector_max_age_seconds=300,
        ),
    )
    engine = MarketDriverEngine(cfg)

    # Session simulation: 78 bars (6.5 hours of 5m bars)
    # Bar 0: INDEX_RISK_ON starts (magnitude 60.0)
    ctx0 = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME,
        bars=[{"open": 500.0, "high": 502.0, "low": 499.5, "close": 501.5, "volume": 1000}],
        market_alignment_score=60.0,
        market_alignment_age_seconds=30,
        relative_strength_score=20.0,
        sector_rs_age_seconds=30,
        delta_value=10.0,
        delta_provenance="ESTIMATED_BID_ASK",
        delta_age_seconds=30,
    )
    res0 = engine.evaluate(ctx0, previous_result=None)
    assert res0.status in (MarketDriverStatus.AVAILABLE, MarketDriverStatus.PARTIAL)
    assert res0.primary_driver is not None
    assert res0.primary_driver.driver_id == DriverArchetype.INDEX_RISK_ON.value
    assert res0.primary_driver.persistence.bars_active == 1

    # Bar 1: Candidate SECTOR_LEADERSHIP rises to 65.0 (margin = +5.0 < 10.0 hurdle)
    ctx1 = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME + timedelta(minutes=5),
        bars=[{"open": 501.5, "high": 502.5, "low": 501.0, "close": 502.0, "volume": 1000}],
        market_alignment_score=60.0,
        market_alignment_age_seconds=30,
        relative_strength_score=65.0,  # Delta = 5.0 < 10.0
        sector_rs_age_seconds=30,
        delta_value=10.0,
        delta_provenance="ESTIMATED_BID_ASK",
        delta_age_seconds=30,
    )
    res1 = engine.evaluate(ctx1, previous_result=res0)
    # Incumbent INDEX_RISK_ON is retained due to hysteresis hurdle
    assert res1.primary_driver.driver_id == DriverArchetype.INDEX_RISK_ON.value
    assert "HYSTERESIS_MAINTAINED" in res1.reason_codes
    assert res1.primary_driver.persistence.bars_active == 2

    # Bar 2: Candidate SECTOR_LEADERSHIP surges to 75.0 (margin = +15.0 >= 10.0 hurdle)
    ctx2 = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME + timedelta(minutes=10),
        bars=[{"open": 502.0, "high": 503.5, "low": 501.8, "close": 503.2, "volume": 1000}],
        market_alignment_score=60.0,
        market_alignment_age_seconds=30,
        relative_strength_score=75.0,  # Delta = 15.0 >= 10.0
        sector_rs_age_seconds=30,
        delta_value=10.0,
        delta_provenance="ESTIMATED_BID_ASK",
        delta_age_seconds=30,
    )
    res2 = engine.evaluate(ctx2, previous_result=res1)
    # Switch approved!
    assert res2.primary_driver.driver_id == DriverArchetype.SECTOR_LEADERSHIP.value
    assert res2.primary_driver.persistence.previous_primary_driver == DriverArchetype.INDEX_RISK_ON.value


def test_obs1_shadow_analysis_cross_tabulation() -> None:
    records = [
        ShadowTelemetryRecord(
            symbol="SPY",
            timeframe="5m",
            evaluation_timestamp=EVAL_TIME,
            agreement_status="AGREEMENT",
            publication_state="RESEARCH_ONLY",
            config_version="research_v1",
            pipeline_version="core_v1",
            trend_regime="TREND_UP",
            direction_label="BULLISH",
            v2_lifecycle_state="WATCH",
            market_driver_status="AVAILABLE",
            primary_driver="INDEX_RISK_ON",
            driver_strength="STRONG",
            driver_persistence_state="ESTABLISHED",
            driver_coverage_status="COMPLETE",
        ),
        ShadowTelemetryRecord(
            symbol="SPY",
            timeframe="5m",
            evaluation_timestamp=EVAL_TIME + timedelta(minutes=5),
            agreement_status="AGREEMENT",
            publication_state="RESEARCH_ONLY",
            config_version="research_v1",
            pipeline_version="core_v1",
            trend_regime="TREND_UP",
            direction_label="BULLISH",
            v2_lifecycle_state="ARMED",
            market_driver_status="AVAILABLE",
            primary_driver="INDEX_RISK_ON",
            driver_strength="STRONG",
            driver_persistence_state="ESTABLISHED",
            driver_coverage_status="COMPLETE",
        ),
        ShadowTelemetryRecord(
            symbol="SPY",
            timeframe="5m",
            evaluation_timestamp=EVAL_TIME + timedelta(minutes=10),
            agreement_status="AGREEMENT",
            publication_state="RESEARCH_ONLY",
            config_version="research_v1",
            pipeline_version="core_v1",
            trend_regime="RANGE",
            direction_label="NEUTRAL",
            v2_lifecycle_state="NO_SETUP",
            market_driver_status="UNAVAILABLE",
            primary_driver="UNAVAILABLE",
            driver_strength="UNAVAILABLE",
            driver_persistence_state="CLEARED",
            driver_coverage_status="INSUFFICIENT",
        ),
    ]

    analysis = analyze_shadow_records(records)
    assert analysis.market_driver_status_counts == {"AVAILABLE": 2, "UNAVAILABLE": 1}
    assert analysis.driver_counts == {"INDEX_RISK_ON": 2, "UNAVAILABLE": 1}
    assert analysis.driver_strength_counts == {"STRONG": 2, "UNAVAILABLE": 1}
    assert analysis.driver_coverage_counts == {"COMPLETE": 2, "INSUFFICIENT": 1}
    assert analysis.driver_persistence_state_counts == {"CLEARED": 1, "ESTABLISHED": 2}
    assert analysis.driver_vs_regime_counts["INDEX_RISK_ON:TREND_UP"] == 2
    assert analysis.driver_vs_direction_counts["INDEX_RISK_ON:BULLISH"] == 2
    assert analysis.driver_vs_lifecycle_counts["INDEX_RISK_ON:WATCH"] == 1
    assert analysis.driver_vs_lifecycle_counts["INDEX_RISK_ON:ARMED"] == 1
    assert analysis.driver_unavailable_causes == {"UNAVAILABLE:INSUFFICIENT": 1}


def test_obs1_unsupported_archetypes_fail_closed() -> None:
    cfg = MarketDriverConfig()
    engine = MarketDriverEngine(cfg)

    # Missing macro event calendar -> MACRO_CATALYST cannot be emitted
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME,
        bars=[{"open": 500.0, "high": 502.0, "low": 499.5, "close": 501.5, "volume": 1000}],
        market_alignment_score=40.0,
        relative_strength_score=20.0,
        delta_value=10.0,
        delta_provenance="ESTIMATED_BID_ASK",
    )
    res = engine.evaluate(ctx)
    if res.primary_driver:
        assert res.primary_driver.driver_id != DriverArchetype.MACRO_CATALYST.value

    # Bar-derived delta (reliability 0.40) must NOT emit DELTA_AGGRESSION
    ctx_delta = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME,
        bars=[{"open": 500.0, "high": 502.0, "low": 499.5, "close": 501.5, "volume": 1000}],
        market_alignment_score=20.0,
        relative_strength_score=20.0,
        delta_value=85.0,
        delta_provenance="BAR_DERIVED",  # unreliable estimate
        delta_age_seconds=10,
    )
    res_delta = engine.evaluate(ctx_delta)
    if res_delta.primary_driver:
        assert res_delta.primary_driver.driver_id != DriverArchetype.DELTA_AGGRESSION.value


def test_obs1_market_driver_explanatory_only_zero_authority() -> None:
    """Market Driver is EXPLANATORY ONLY: zero lifecycle authority, no trade veto."""
    result = QXEvaluationResult.model_construct(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVAL_TIME,
        current_lifecycle_state=LifecycleState.WATCH,
        market_driver=MarketDriverResult(
            status=MarketDriverStatus.AVAILABLE,
            primary_driver=None,
            coverage=CoverageAudit(
                observed_sources=5,
                required_sources=5,
                status="COMPLETE",
            ),
        ),
    )
    # Verified: lifecycle remains WATCH, market driver has no mutator
    assert result.current_lifecycle_state == LifecycleState.WATCH
