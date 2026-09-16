"""Phase 5B Unit Test Suite: Direction Engine.

Verifies deterministic direction score calculation bounded between -100 and +100.
Ensures factor isolation (no RVOL, spread, or liquidity used), provenance reliability,
evidence coverage calculation with neutral quality terms (INSUFFICIENT, PARTIAL, ADEQUATE, STRONG, COMPLETE),
configuration-driven structure event scores, factor freshness handling, and independence from trade lifecycle states.
"""

from qx.config.rules_config import load_rules_config
from qx.direction.direction_engine import (
    DirectionEngineResult,
    compute_delta_factor,
    compute_ema_factor,
    compute_structure_factor,
    compute_vwap_factor,
    evaluate_direction_engine,
)
from qx.models.rules import DeltaProvenance, EvidenceCoverageStatus, GammaRegime, SignalState
from qx.regime.market_regime import evaluate_market_regime


def test_direction_score_bounded_minus100_plus100():
    # Maximum bullish scenario
    res_bull = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BULLISH",
        last_event_type="BULLISH_BOS",
        price=120.0,
        vwap=115.0,
        vwap_slope=1.2,
        fast_ema=120.0,
        medium_ema=118.0,
        slow_ema=115.0,
        fast_slope=0.5,
        medium_slope=0.3,
        slow_slope=0.2,
        delta_value=150.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=100.0,
        market_alignment_score=100.0,
        htf_structure_state="BULLISH",
    )
    assert res_bull.direction_score == 100.0
    assert res_bull.direction_label == "BULLISH"

    # Maximum bearish scenario
    res_bear = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BEARISH",
        last_event_type="BEARISH_BOS",
        price=100.0,
        vwap=110.0,
        vwap_slope=-1.5,
        fast_ema=100.0,
        medium_ema=105.0,
        slow_ema=110.0,
        fast_slope=-0.5,
        medium_slope=-0.3,
        slow_slope=-0.2,
        delta_value=-150.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=-100.0,
        market_alignment_score=-100.0,
        htf_structure_state="BEARISH",
    )
    assert res_bear.direction_score == -100.0
    assert res_bear.direction_label == "BEARISH"


def test_rvol_not_used_in_direction_score():
    res1 = evaluate_direction_engine(symbol="ES", structure_state="BULLISH", price=100.0, vwap=90.0, vwap_slope=1.0)
    factor_ids = [f.factor_id for f in res1.factors]
    assert "rvol" not in factor_ids
    assert "volume" not in factor_ids


def test_liquidity_not_used_in_direction_score():
    res = evaluate_direction_engine(symbol="ES", structure_state="BULLISH")
    factor_ids = [f.factor_id for f in res.factors]
    assert "liquidity" not in factor_ids
    assert "sweep" not in factor_ids


def test_spread_not_used_in_direction_score():
    res = evaluate_direction_engine(symbol="ES", structure_state="BULLISH")
    factor_ids = [f.factor_id for f in res.factors]
    assert "spread" not in factor_ids
    assert "bid_ask_spread" not in factor_ids


def test_missing_delta_not_redistributed_to_structure():
    res_with_delta = evaluate_direction_engine(
        symbol="ES",
        structure_state="BULLISH",
        delta_value=100.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
    )
    res_no_delta = evaluate_direction_engine(
        symbol="ES",
        structure_state="BULLISH",
        delta_value=None,
        delta_provenance=DeltaProvenance.UNAVAILABLE,
    )

    struct_factor_with = next(f for f in res_with_delta.factors if f.factor_id == "structure")
    struct_factor_no = next(f for f in res_no_delta.factors if f.factor_id == "structure")

    assert struct_factor_with.configured_weight == 0.30
    assert struct_factor_no.configured_weight == 0.30
    assert struct_factor_with.effective_weight == 0.30
    assert struct_factor_no.effective_weight == 0.30


def test_actual_delta_has_full_reliability():
    factor = compute_delta_factor(
        delta_value=100.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        configured_weight=0.15,
    )
    assert factor.reliability_multiplier == 1.00
    assert factor.effective_weight == 0.15


def test_bar_derived_delta_has_reduced_reliability():
    factor = compute_delta_factor(
        delta_value=100.0,
        delta_provenance=DeltaProvenance.BAR_DERIVED,
        configured_weight=0.15,
    )
    assert factor.reliability_multiplier == 0.40
    assert factor.effective_weight == 0.15 * 0.40


def test_unavailable_delta_contributes_zero_weight():
    factor = compute_delta_factor(
        delta_value=None,
        delta_provenance=DeltaProvenance.UNAVAILABLE,
        configured_weight=0.15,
    )
    assert factor.reliability_multiplier == 0.00
    assert factor.effective_weight == 0.00
    assert factor.weighted_contribution == 0.00


def test_evidence_coverage_decreases_when_factor_missing():
    res_full = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BULLISH",
        price=100.0,
        vwap=95.0,
        vwap_slope=1.0,
        fast_ema=100.0,
        medium_ema=95.0,
        slow_ema=90.0,
        fast_slope=0.1,
        medium_slope=0.1,
        slow_slope=0.1,
        delta_value=50.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=50.0,
        market_alignment_score=50.0,
        htf_structure_state="BULLISH",
    )
    assert res_full.direction_evidence_coverage == 1.00
    assert res_full.coverage_status == EvidenceCoverageStatus.COMPLETE.value

    res_partial = evaluate_direction_engine(
        symbol="UNKNOWN_SYM",
        structure_state="BULLISH",
        price=100.0,
        vwap=95.0,
        vwap_slope=1.0,
        delta_value=None,
        delta_provenance=DeltaProvenance.UNAVAILABLE,
        relative_strength_score=None,
    )
    assert res_partial.direction_evidence_coverage < 1.00


def test_high_score_low_coverage_remains_low_coverage():
    res = evaluate_direction_engine(
        symbol="UNKNOWN_SYM",
        structure_state="BULLISH",
        delta_provenance=DeltaProvenance.UNAVAILABLE,
    )
    assert res.direction_score == 100.0
    assert res.direction_evidence_coverage == 0.30
    assert res.coverage_status == EvidenceCoverageStatus.INSUFFICIENT.value


def test_direction_coverage_never_returns_executable_state():
    res = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BULLISH",
        price=120.0,
        vwap=115.0,
        vwap_slope=1.0,
        fast_ema=120.0,
        medium_ema=118.0,
        slow_ema=115.0,
        fast_slope=0.5,
        medium_slope=0.3,
        slow_slope=0.2,
        delta_value=100.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=100.0,
        market_alignment_score=100.0,
        htf_structure_state="BULLISH",
    )
    assert res.coverage_status != "EXECUTABLE"
    assert res.coverage_status == "COMPLETE"


def test_neutral_full_coverage_is_complete_not_executable():
    res = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="NEUTRAL",
        price=100.0,
        vwap=100.0,
        vwap_slope=0.0,
        fast_ema=100.0,
        medium_ema=100.0,
        slow_ema=100.0,
        delta_value=0.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=0.0,
        market_alignment_score=0.0,
        htf_structure_state="NEUTRAL",
    )
    assert res.direction_score == 0.0
    assert res.direction_label == "NEUTRAL"
    assert res.coverage_status == "COMPLETE"
    assert res.coverage_status != "EXECUTABLE"


def test_direction_coverage_status_is_independent_of_signal_state():
    res = evaluate_direction_engine(symbol="ES", structure_state="BULLISH")
    for signal_state in [SignalState.WATCH, SignalState.ARMED, SignalState.TRIGGERED, SignalState.EXECUTABLE]:
        assert res.coverage_status != signal_state.value


def test_direction_coverage_never_uses_signal_lifecycle_names():
    res = evaluate_direction_engine(symbol="ES", structure_state="BULLISH")
    disallowed_lifecycle_names = {"WATCH", "ARMED", "TRIGGERED", "EXECUTABLE"}
    assert res.coverage_status not in disallowed_lifecycle_names


def test_neutral_complete_evidence_does_not_imply_trade():
    res = evaluate_direction_engine(symbol="ES")
    assert res.trade_state == "NONE - PLAYBOOK NOT EVALUATED IN PHASE 5"
    assert not hasattr(res, "buy_signal")
    assert not hasattr(res, "sell_signal")


def test_stale_factor_does_not_receive_full_reliability():
    config = load_rules_config()
    res_stale = evaluate_direction_engine(
        symbol="NVDA",
        structure_state="BULLISH",
        structure_age_bars=50,  # Max bars is 25 for 5m
        vwap=100.0,
        price=105.0,
        vwap_age_seconds=120.0,  # Max quote age is 60s
        rules_config=config,
    )
    struct_f = next(f for f in res_stale.factors if f.factor_id == "structure")
    vwap_f = next(f for f in res_stale.factors if f.factor_id == "vwap")

    assert struct_f.freshness_status == "STALE"
    assert struct_f.reliability_multiplier < 1.00
    assert vwap_f.freshness_status == "STALE"
    assert vwap_f.reliability_multiplier < 1.00


def test_structure_event_scores_are_configuration_driven():
    config = load_rules_config()

    f_bos = compute_structure_factor(structure_state="BULLISH", last_event_type="BULLISH_BOS", config=config.direction_engine)
    f_choch = compute_structure_factor(structure_state="BULLISH", last_event_type="BULLISH_CHOCH", config=config.direction_engine)
    f_init = compute_structure_factor(structure_state="BULLISH", last_event_type="BULLISH_INITIAL_BREAK", config=config.direction_engine)

    assert f_bos.raw_score == config.direction_engine.structure_scores.bullish_bos
    assert f_choch.raw_score == config.direction_engine.structure_scores.bullish_choch
    assert f_init.raw_score == config.direction_engine.structure_scores.bullish_initial_break


def test_sector_rs_and_market_alignment_remain_independent_factor_records():
    res = evaluate_direction_engine(
        symbol="NVDA",
        relative_strength_score=90.0,
        market_alignment_score=80.0,
    )
    sec_f = next(f for f in res.factors if f.factor_id == "sector_rs")
    mkt_f = next(f for f in res.factors if f.factor_id == "market_alignment")

    assert sec_f.evidence_family == "sector_relative_strength"
    assert mkt_f.evidence_family == "broad_market_alignment"
    assert sec_f.raw_score == 90.0
    assert mkt_f.raw_score == 80.0
    # Independent scores, neither amplifies the other
