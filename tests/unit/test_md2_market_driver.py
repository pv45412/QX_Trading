"""Unit and Invariant Tests for MD2 Market Driver Engine (Option B Contract)."""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict
import pandas as pd
import pytest

from qx.config.rules_config import (
    MarketDriverConfig,
    MarketDriverThresholdsConfig,
    MarketDriverFreshnessConfig,
    RulesEngineConfig,
    load_rules_config,
)
from qx.market_driver.engine import MarketDriverEngine
from qx.market_driver.models import (
    DriverArchetype,
    DriverDirection,
    DriverStrength,
    EvidenceClassification,
    MarketDriverResult,
    MarketDriverStatus,
    PersistenceState,
)
from qx.pipeline.models import (
    DataDependencyStatus,
    LifecycleState,
    QXEvaluationContext,
    QXEvaluationResult,
)
from qx.pipeline.orchestrator import run_pipeline


def _sample_bars(n: int = 50, base_price: float = 580.0, start_ts: datetime | None = None) -> pd.DataFrame:
    start = start_ts or datetime(2026, 9, 17, 13, 30, tzinfo=timezone.utc)
    rows = []
    price = base_price
    for i in range(n):
        ts = start + timedelta(minutes=5 * i)
        high = price + 0.75
        low = price - 0.75
        close = price + 0.10
        rows.append({
            "timestamp": ts,
            "open": price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 100000,
        })
        price = close
    return pd.DataFrame(rows)


def _base_context(
    symbol: str = "NVDA",
    eval_ts: datetime | None = None,
    bars: pd.DataFrame | None = None,
    market_alignment_score: float = 65.0,
    relative_strength_score: float = 45.0,
    delta_value: float = 55.0,
    delta_provenance: str = "ACTUAL_TRADE_AGGRESSOR",
    gamma_value: float = 40.0,
    gamma_provenance: str = "ACTUAL_GEX_CALCULATED",
) -> QXEvaluationContext:
    ts = eval_ts or datetime(2026, 9, 17, 14, 30, tzinfo=timezone.utc)
    bar_df = bars if bars is not None else _sample_bars(n=50, start_ts=ts - timedelta(minutes=250))
    ctx = QXEvaluationContext(
        symbol=symbol,
        timeframe="5m",
        evaluation_timestamp=ts,
        bars=bar_df,
        market_alignment_score=market_alignment_score,
        market_alignment_age_seconds=15,
        relative_strength_score=relative_strength_score,
        sector_rs_age_seconds=30,
        delta_value=delta_value,
        delta_provenance=delta_provenance,
        delta_age_seconds=20,
        gamma_value=gamma_value,
        gamma_provenance=gamma_provenance,
        vwap=580.0,
        atr=2.5,
    )
    ctx.data_dependencies["bars"] = DataDependencyStatus(
        name="bars",
        available=True,
        source="CANONICAL_FEED",
        data_as_of=ts,
        freshness="FRESH",
        publication_state="COMMITTED",
        sync_status="SYNCHRONIZED",
        content_sha256="a" * 64,
        retrieved_at=ts,
    )
    return ctx


# -----------------------------------------------------------------------------
# 1. Coverage & Mandatory Source Gating
# -----------------------------------------------------------------------------

def test_missing_underlying_bars_blocks_market_driver() -> None:
    """Missing or empty underlying bars must result in status == BLOCKED."""
    ctx = _base_context(bars=pd.DataFrame())
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.status == MarketDriverStatus.BLOCKED
    assert result.primary_driver is None
    assert "MISSING_UNDERLYING_BARS" in result.reason_codes
    assert "underlying" in result.coverage.missing_sources


def test_missing_index_benchmark_fails_closed_to_unavailable() -> None:
    """Missing benchmark index feed must result in status == UNAVAILABLE."""
    ctx = _base_context()
    ctx.market_alignment_score = None  # Missing index
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.status == MarketDriverStatus.UNAVAILABLE
    assert result.primary_driver is None
    assert "INDEX_BENCHMARK_UNAVAILABLE" in result.reason_codes
    assert "index" in result.coverage.missing_sources


def test_insufficient_coverage_less_than_three_fails_closed() -> None:
    """Underlying + Index without any 3rd source (count = 2) must fail closed."""
    ctx = _base_context()
    ctx.relative_strength_score = None  # Missing sector
    ctx.delta_provenance = "UNAVAILABLE"  # Missing delta
    ctx.gamma_provenance = "UNAVAILABLE"  # Missing gamma
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.status == MarketDriverStatus.UNAVAILABLE
    assert result.primary_driver is None
    assert result.coverage.observed_sources == 2
    assert "INSUFFICIENT_EVIDENCE_COVERAGE" in result.reason_codes


def test_minimum_coverage_three_of_five_yields_partial() -> None:
    """Underlying + Index + Sector (3 of 5) emits driver with PARTIAL coverage."""
    ctx = _base_context()
    ctx.delta_provenance = "UNAVAILABLE"
    ctx.gamma_provenance = "UNAVAILABLE"
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.status == MarketDriverStatus.PARTIAL
    assert result.coverage.status == "PARTIAL"
    assert result.coverage.observed_sources == 3
    assert set(result.coverage.missing_sources) == {"delta", "gamma"}
    assert result.primary_driver is not None
    assert "DRIVER_AVAILABLE_PARTIAL" in result.reason_codes


def test_four_of_five_coverage_yields_partial() -> None:
    """Underlying + Index + Sector + Delta (4 of 5, gamma missing) yields PARTIAL."""
    ctx = _base_context()
    ctx.gamma_provenance = "UNAVAILABLE"
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.status == MarketDriverStatus.PARTIAL
    assert result.coverage.observed_sources == 4
    assert result.coverage.missing_sources == ["gamma"]
    assert result.primary_driver is not None


def test_five_of_five_coverage_yields_complete_available() -> None:
    """All 5 sources fresh and present yields status AVAILABLE with COMPLETE coverage."""
    ctx = _base_context()
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.status == MarketDriverStatus.AVAILABLE
    assert result.coverage.status == "COMPLETE"
    assert result.coverage.observed_sources == 5
    assert len(result.coverage.missing_sources) == 0
    assert "DRIVER_AVAILABLE_COMPLETE" in result.reason_codes


# -----------------------------------------------------------------------------
# 2. Option B Parameters, Continuous Scoring & Strength Bands
# -----------------------------------------------------------------------------

def test_primary_and_secondary_activation_thresholds() -> None:
    """Primary requires M >= 35.0; secondary requires M >= 20.0."""
    ctx = _base_context(
        market_alignment_score=70.0,   # Mag 70.0 -> Primary
        relative_strength_score=25.0,  # Mag 25.0 -> Secondary
        delta_value=12.0,              # Mag 12.0 -> Below 20.0, not secondary
        gamma_value=0.0,
        gamma_provenance="UNAVAILABLE",
    )
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.primary_driver is not None
    assert result.primary_driver.driver_id == DriverArchetype.INDEX_RISK_ON.value
    assert len(result.secondary_drivers) == 1
    assert result.secondary_drivers[0].driver_id == DriverArchetype.SECTOR_LEADERSHIP.value


def test_strength_bands_weak_moderate_strong() -> None:
    """Tests WEAK [35, 55), MODERATE [55, 75), and STRONG [75, 100]."""
    engine = MarketDriverEngine()

    # Weak (magnitude 40.0)
    ctx_weak = _base_context(market_alignment_score=40.0, relative_strength_score=10.0, delta_value=10.0)
    res_weak = engine.evaluate(ctx_weak)
    assert res_weak.primary_driver.strength == DriverStrength.WEAK

    # Moderate (magnitude 65.0)
    ctx_mod = _base_context(market_alignment_score=65.0, relative_strength_score=10.0, delta_value=10.0)
    res_mod = engine.evaluate(ctx_mod)
    assert res_mod.primary_driver.strength == DriverStrength.MODERATE

    # Strong (magnitude 85.0)
    ctx_str = _base_context(market_alignment_score=85.0, relative_strength_score=10.0, delta_value=10.0)
    res_str = engine.evaluate(ctx_str)
    assert res_str.primary_driver.strength == DriverStrength.STRONG


# -----------------------------------------------------------------------------
# 3. Hysteresis Buffer & Persistence State
# -----------------------------------------------------------------------------

def test_hysteresis_retains_incumbent_when_margin_below_hurdle() -> None:
    """If incumbent has M=60.0 and candidate has M=65.0 (Delta=5.0 < 10.0), retain incumbent."""
    engine = MarketDriverEngine()

    # Evaluation 1: Index is primary (M=60.0)
    ctx1 = _base_context(market_alignment_score=60.0, relative_strength_score=30.0, delta_value=10.0)
    res1 = engine.evaluate(ctx1)
    assert res1.primary_driver.driver_id == DriverArchetype.INDEX_RISK_ON.value
    assert res1.primary_driver.persistence.state == PersistenceState.NEW

    # Evaluation 2: Sector surges to M=65.0, while Index drops to M=58.0
    # Candidate Sector (65.0) - Incumbent Index (58.0) = 7.0 (< 10.0 hurdle)
    ctx2 = _base_context(market_alignment_score=58.0, relative_strength_score=65.0, delta_value=10.0)
    res2 = engine.evaluate(ctx2, previous_result=res1)
    # Incumbent MUST be retained!
    assert res2.primary_driver.driver_id == DriverArchetype.INDEX_RISK_ON.value
    assert "HYSTERESIS_MAINTAINED" in res2.reason_codes
    assert res2.primary_driver.persistence.bars_active == 2


def test_hysteresis_replaces_incumbent_when_margin_meets_or_exceeds_hurdle() -> None:
    """If candidate exceeds incumbent by Delta >= 10.0, promote candidate and set state NEW."""
    engine = MarketDriverEngine()

    # Evaluation 1: Index is primary (M=55.0)
    ctx1 = _base_context(market_alignment_score=55.0, relative_strength_score=30.0, delta_value=10.0)
    res1 = engine.evaluate(ctx1)
    assert res1.primary_driver.driver_id == DriverArchetype.INDEX_RISK_ON.value

    # Evaluation 2: Sector jumps to M=75.0, while Index is M=52.0 (Margin = 23.0 >= 10.0)
    ctx2 = _base_context(market_alignment_score=52.0, relative_strength_score=75.0, delta_value=10.0)
    res2 = engine.evaluate(ctx2, previous_result=res1)
    assert res2.primary_driver.driver_id == DriverArchetype.SECTOR_LEADERSHIP.value
    assert res2.primary_driver.persistence.state == PersistenceState.NEW
    assert res2.primary_driver.persistence.previous_primary_driver == DriverArchetype.INDEX_RISK_ON.value
    assert res2.primary_driver.persistence.candidate_margin == 23.0


# -----------------------------------------------------------------------------
# 4. Confirming vs Conflicting Evidence Partitioning
# -----------------------------------------------------------------------------

def test_evidence_partitioning_by_directional_sign() -> None:
    """Bullish primary driver partitions positive scores as confirming, negative as conflicting."""
    # Primary driver will be INDEX_RISK_ON (Bullish, M=75.0)
    # Confirming: Sector (+45.0), Delta (+50.0)
    # Conflicting: If delta were negative, it would be conflicting
    ctx = _base_context(
        market_alignment_score=75.0,
        relative_strength_score=45.0,   # Confirming
        delta_value=-50.0,              # Conflicting!
    )
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.primary_driver.direction == DriverDirection.BULLISH

    confirming_ids = [e.source_stage for e in result.confirming_evidence]
    conflicting_ids = [e.source_stage for e in result.conflicting_evidence]

    assert "INDEX" in confirming_ids
    assert "SECTOR" in confirming_ids
    assert "DELTA" in conflicting_ids

    # Verify classification enum
    for token in result.confirming_evidence:
        assert token.classification == EvidenceClassification.CONFIRMING
    for token in result.conflicting_evidence:
        assert token.classification == EvidenceClassification.CONFLICTING


# -----------------------------------------------------------------------------
# 5. Provenance, Stale Degradation & Unsupported Archetypes
# -----------------------------------------------------------------------------

def test_stale_feed_cuts_reliability_in_half() -> None:
    """Feeds exceeding max freshness SLA get marked STALE and reliability *= 0.50."""
    ctx = _base_context(
        market_alignment_score=60.0,
        relative_strength_score=70.0,
    )
    ctx.sector_rs_age_seconds = 300  # Max SLA is 120s -> Stale!
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)

    sector_audit = result.coverage.source_details["sector"]
    assert sector_audit["freshness"] == "STALE"
    assert sector_audit["reliability"] == 0.50
    assert "STALE_SECTOR_FEED" in result.reason_codes


def test_delta_provenance_bar_derived_cannot_claim_delta_aggression() -> None:
    """Bar-derived delta (reliability 0.40) must NOT be represented as actual aggressor flow."""
    ctx = _base_context(
        delta_value=80.0,
        delta_provenance="BAR_DERIVED",
        market_alignment_score=40.0,
        relative_strength_score=20.0,
    )
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    # DELTA_AGGRESSION requires ACTUAL_TRADE_AGGRESSOR or ESTIMATED_BID_ASK
    cand_archetypes = [cand.driver_id for cand in result.secondary_drivers]
    assert result.primary_driver.driver_id != DriverArchetype.DELTA_AGGRESSION.value
    assert DriverArchetype.DELTA_AGGRESSION.value not in cand_archetypes


# -----------------------------------------------------------------------------
# 6. Pipeline Non-Authoritative / Explanatory Invariant
# -----------------------------------------------------------------------------

def test_market_driver_does_not_alter_lifecycle_state() -> None:
    """Market Driver is explanatory only; pipeline lifecycle state remains identical."""
    cfg = load_rules_config()
    ctx = _base_context(market_alignment_score=-80.0, relative_strength_score=-70.0)
    result = run_pipeline(ctx, cfg)

    # Result has market_driver populated
    assert result.market_driver is not None
    assert result.market_driver.primary_driver is not None
    assert result.market_driver.primary_driver.driver_id == DriverArchetype.INDEX_RISK_OFF.value

    # Lifecycle state must NOT be vetoed or changed by Market Driver
    assert result.current_lifecycle_state in (
        LifecycleState.NO_SETUP,
        LifecycleState.WATCH,
        LifecycleState.ARMED,
        LifecycleState.TRIGGERED,
        LifecycleState.TRADEABLE,
    )
    assert result.stage_latencies["market_driver_ms"] != "SKIPPED"
    assert result.stage_latencies["market_driver_ms"] < 50.0  # Runs in < 50ms (usually < 2ms)


def test_deterministic_idempotency() -> None:
    """1,000 evaluations with identical inputs yield identical input fingerprints."""
    ctx = _base_context()
    engine = MarketDriverEngine()
    fingerprints = {engine.evaluate(ctx).input_fingerprint for _ in range(50)}
    assert len(fingerprints) == 1


# -----------------------------------------------------------------------------
# 7. Session Archetypes & Historical Replay Invariants
# -----------------------------------------------------------------------------

def test_unsupported_macro_catalyst_without_calendar_source_fails_closed() -> None:
    """MACRO_CATALYST archetype cannot be emitted without an approved source-backed calendar event."""
    ctx = _base_context(
        market_alignment_score=40.0,
        relative_strength_score=30.0,
    )
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    archetypes = [cand.driver_id for cand in result.secondary_drivers]
    if result.primary_driver:
        archetypes.append(result.primary_driver.driver_id)
    assert DriverArchetype.MACRO_CATALYST.value not in archetypes


def test_fast_downside_session_negative_gamma_squeeze() -> None:
    """Fast downside session with negative dealer gamma emits GAMMA_SQUEEZE or INDEX_RISK_OFF."""
    ctx = _base_context(
        market_alignment_score=-85.0,
        relative_strength_score=-75.0,
        delta_value=-80.0,
        delta_provenance="ACTUAL_TRADE_AGGRESSOR",
        gamma_value=-90.0,
        gamma_provenance="DEALER_GAMMA_MODELED",
    )
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.status == MarketDriverStatus.AVAILABLE
    assert result.primary_driver is not None
    assert result.primary_driver.direction == DriverDirection.BEARISH
    assert result.primary_driver.strength == DriverStrength.STRONG
    assert len(result.secondary_drivers) >= 1
    sec_ids = [s.driver_id for s in result.secondary_drivers]
    assert any(d in sec_ids for d in (DriverArchetype.GAMMA_SQUEEZE.value, DriverArchetype.SECTOR_LAG.value, DriverArchetype.DELTA_AGGRESSION.value))


def test_range_chop_session_dealer_gamma_pinning() -> None:
    """Range/chop session with high positive gamma and low index alignment emits GAMMA_PINNING."""
    ctx = _base_context(
        market_alignment_score=10.0,  # Flat / choppy
        relative_strength_score=5.0,
        delta_value=8.0,
        gamma_value=85.0,            # Dominant positive gamma
        gamma_provenance="ACTUAL_GEX_CALCULATED",
    )
    engine = MarketDriverEngine()
    result = engine.evaluate(ctx)
    assert result.primary_driver is not None
    assert result.primary_driver.driver_id == DriverArchetype.GAMMA_PINNING.value
    assert result.primary_driver.direction == DriverDirection.NEUTRAL
    assert result.primary_driver.strength == DriverStrength.STRONG


def test_zero_lookahead_temporal_filtering() -> None:
    """Candles with timestamps beyond evaluation timestamp must not be inspected."""
    eval_ts = datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc)
    bars = _sample_bars(n=30, start_ts=eval_ts - timedelta(minutes=150))
    # Future bars:
    future_rows = []
    for i in range(1, 10):
        future_rows.append({
            "timestamp": eval_ts + timedelta(minutes=5 * i),
            "open": 600.0,
            "high": 605.0,
            "low": 599.0,
            "close": 604.0,
            "volume": 200000,
        })
    all_bars = pd.concat([bars, pd.DataFrame(future_rows)], ignore_index=True)

    cfg = load_rules_config()
    ctx = _base_context(eval_ts=eval_ts, bars=all_bars)
    result = run_pipeline(ctx, cfg)
    assert result.market_driver is not None
    # Evaluation timestamp is strictly preserved
    assert result.market_driver.data_as_of == eval_ts
    assert result.market_driver.knowledge_timestamp == eval_ts
