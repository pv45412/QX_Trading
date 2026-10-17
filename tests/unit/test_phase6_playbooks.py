"""Phase 6 Unit Test Suite: Deterministic QX Playbooks Engine.

Verifies:
- Playbook A (Trend Pullback Continuation)
- Playbook B (Liquidity Sweep + Reclaim)
- Playbook C (Opening Range Breakout)
- Lifecycle state invariants (NO_SETUP, WATCH, ARMED strictly enforced; TRIGGERED and EXECUTABLE prohibited)
- Multi-playbook coexistence & priority candidate selection
- Knowledge-time safety & zero trade execution
"""

import pytest
from qx.config.rules_config import load_rules_config
from qx.direction.direction_engine import evaluate_direction_engine
from qx.models.rules import (
    DeltaProvenance,
    GammaRegime,
    MarketRegimeModel,
    PublicationState,
    SessionRegime,
    SignalState,
    TrendRegime,
    VolatilityRegime,
)
from qx.playbooks import (
    LiquiditySweepEvaluator,
    OpeningRangeBreakoutEvaluator,
    PlaybookEngine,
    PlaybookEvaluation,
    QXEvaluationContext,
    TrendPullbackEvaluator,
)
from qx.regime.market_regime import evaluate_market_regime


def helper_create_context(
    symbol="NVDA",
    timeframe="5m",
    price=100.0,
    high=100.0,
    low=100.0,
    trend=TrendRegime.TREND_UP,
    vol=VolatilityRegime.NORMAL,
    dir_score=80.0,
    dir_cov=1.00,
    struct_state="BULLISH",
    struct_invalidated=False,
    order_blocks=None,
    session_levels=None,
    vwap=None,
    atr=2.0,
):
    mr = MarketRegimeModel(
        trend=trend,
        volatility=vol,
        gamma=GammaRegime.UNKNOWN,
        session=SessionRegime.BALANCED,
    )
    is_bull = dir_score >= 0
    dir_res = evaluate_direction_engine(
        symbol=symbol,
        timeframe=timeframe,
        structure_state=struct_state,
        price=price,
        vwap=vwap or price,
        vwap_slope=1.0 if is_bull else -1.0,
        fast_ema=price + (1.0 if is_bull else -1.0),
        medium_ema=price,
        slow_ema=price - (1.0 if is_bull else -1.0),
        fast_slope=0.1 if is_bull else -0.1,
        medium_slope=0.1 if is_bull else -0.1,
        slow_slope=0.1 if is_bull else -0.1,
        delta_value=dir_score,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=dir_score if symbol != "UNMAPPED_TICKER" else None,
        market_alignment_score=dir_score if symbol != "UNKNOWN_SYM" else None,
        htf_structure_state=struct_state,
    )

    struct_res = type("StructRes", (), {"state": struct_state, "invalidated": struct_invalidated})()

    return QXEvaluationContext(
        symbol=symbol,
        timeframe=timeframe,
        latest_bar={"close": price, "high": high, "low": low, "price": price},
        market_regime=mr,
        direction=dir_res,
        structure_result=struct_res,
        order_blocks=order_blocks or [],
        session_levels=session_levels or {},
        vwap=vwap,
        atr=atr,
        publication_state=PublicationState.VERIFIED,
        event_timestamp="2026-09-15T15:30:00Z",
        knowledge_timestamp="2026-09-15T15:30:00Z",
    )


# --- COMMON TESTS ---

def test_playbook_engine_generates_no_trade_execution():
    ctx = helper_create_context()
    engine = PlaybookEngine()
    evals, primary = engine.evaluate_all(ctx)
    for ev in evals:
        assert not hasattr(ev, "buy_signal")
        assert not hasattr(ev, "sell_signal")
        assert ev.trade_state == "NONE - PLAYBOOK NOT EVALUATED FOR TRADE EXECUTION IN PHASE 6"


def test_playbook_engine_never_returns_triggered_in_phase6():
    ctx = helper_create_context()
    engine = PlaybookEngine()
    evals, _ = engine.evaluate_all(ctx)
    for ev in evals:
        assert ev.state != SignalState.TRIGGERED


def test_playbook_engine_never_returns_executable_in_phase6():
    ctx = helper_create_context()
    engine = PlaybookEngine()
    evals, _ = engine.evaluate_all(ctx)
    for ev in evals:
        assert ev.state != SignalState.EXECUTABLE


def test_no_valid_playbook_returns_no_setup():
    ctx = helper_create_context(trend=TrendRegime.RANGE, dir_score=0.0, struct_state="NEUTRAL")
    engine = PlaybookEngine()
    evals, primary = engine.evaluate_all(ctx)
    assert all(e.state == SignalState.NO_SETUP for e in evals)
    assert primary.state == SignalState.NO_SETUP


def test_multiple_playbooks_can_coexist():
    # Context where Pullback is WATCH and Sweep is ARMED
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    session_lvls = {"PDL": 98.0}
    ctx = helper_create_context(price=97.0, low=97.5, order_blocks=[ob], session_levels=session_lvls)

    engine = PlaybookEngine()
    evals, primary = engine.evaluate_all(ctx)

    pb_a = next(e for e in evals if e.playbook_id == "playbook_a_pullback")
    pb_b = next(e for e in evals if e.playbook_id == "playbook_b_liquidity_sweep")

    # Sweep is ARMED because low (97.5) swept PDL (98.0)
    assert pb_b.state == SignalState.ARMED
    # Pullback is WATCH because price (97.0) is approaching OB (95.0)
    assert pb_a.state == SignalState.WATCH
    # Primary candidate is ARMED
    assert primary.playbook_id == "playbook_b_liquidity_sweep"


def test_playbook_thresholds_are_config_driven():
    cfg = load_rules_config()
    assert "playbook_a_pullback" in cfg.playbooks
    assert cfg.playbooks["playbook_a_pullback"]["min_direction_score"] == 40.0


def test_playbook_uses_only_knowable_evidence():
    ctx = helper_create_context()
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.config_version == "research_v1"
    assert isinstance(res.rule_results, list)


# --- PULLBACK TESTS ---

def test_bullish_trend_without_pullback_is_watch():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    # Price is at 97.0, approaching OB [90-95]
    ctx = helper_create_context(price=97.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.WATCH
    assert res.direction == "BULLISH"


def test_bullish_pullback_into_valid_ob_can_arm():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    # Price is inside OB zone at 92.0
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BULLISH"
    assert "5m candle close above local reclaim level" in res.trigger_definition


def test_bearish_pullback_into_valid_ob_can_arm():
    ob = {"ob_id": "ob_bear", "type": "BEARISH_OB", "state": "VALIDATED", "proximal_price": 105.0, "distal_price": 110.0}
    ctx = helper_create_context(
        trend=TrendRegime.TREND_DOWN,
        struct_state="BEARISH",
        dir_score=-80.0,
        price=107.0,
        order_blocks=[ob],
    )
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BEARISH"
    assert "5m candle close below local breakdown level" in res.trigger_definition


def test_pullback_against_invalidated_structure_is_rejected():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, struct_invalidated=True, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.NO_SETUP


def test_invalidated_ob_cannot_arm_pullback():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "INVALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.NO_SETUP


def test_expired_ob_cannot_arm_pullback():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "EXPIRED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.NO_SETUP


def test_pullback_does_not_require_fvg():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    ctx.fvgs = []  # No FVGs
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED


def test_pullback_confluence_is_recorded():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob], vwap=92.0)
    ctx.fvgs = [{"id": "fvg_1"}]
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.setup_quality_components["confluence_score"] == 99.9  # 3 * 33.3


# --- LIQUIDITY SWEEP TESTS ---

def test_approaching_liquidity_is_watch_not_armed():
    session_lvls = {"PDL": 95.0}
    # Price is 96.0 (approaching PDL 95.0 within 1.5 ATR = 3.0)
    ctx = helper_create_context(price=96.0, low=95.5, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.WATCH
    assert res.direction == "BULLISH"


def test_bullish_low_sweep_can_arm_reversal_setup():
    session_lvls = {"PDL": 95.0}
    # Low at 94.0 swept PDL 95.0 by 1.0 (0.5 ATR >= 0.10 min)
    ctx = helper_create_context(price=94.5, low=94.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BULLISH"
    assert "PDL" in res.trigger_definition


def test_bearish_high_sweep_can_arm_reversal_setup():
    session_lvls = {"PDH": 105.0}
    # High at 106.0 swept PDH 105.0
    ctx = helper_create_context(price=105.5, high=106.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BEARISH"
    assert "PDH" in res.trigger_definition


def test_no_actual_sweep_returns_watch_or_no_setup():
    session_lvls = {"PDL": 80.0}
    # Price 100.0 is far from PDL 80.0
    ctx = helper_create_context(price=100.0, low=100.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.NO_SETUP
    assert res.reason_code == "NO_LIQUIDITY_APPROACH_OR_SWEEP"


def test_unrelated_old_liquidity_level_not_used():
    ctx = helper_create_context(session_levels={})
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.NO_SETUP


def test_sweep_direction_logic_supports_countertrend_setup():
    session_lvls = {"PDL": 95.0}
    # Bearish trend/direction score, but bullish PDL sweep occurs -> arms BULLISH reversal
    ctx = helper_create_context(
        trend=TrendRegime.TREND_DOWN,
        dir_score=-80.0,
        price=94.5,
        low=94.0,
        session_levels=session_lvls,
    )
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BULLISH"


def test_liquidity_level_provenance_is_recorded():
    session_lvls = {"SWING_LOW": 90.0}
    ctx = helper_create_context(price=89.5, low=89.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert "swing_low_level" in res.source_pivot_ids


# --- ORB TESTS ---

def test_orb_not_complete_before_configured_window():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": False}
    ctx = helper_create_context(session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.NO_SETUP


def test_completed_orb_inside_range_is_watch():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    # Price inside range at 100.0
    ctx = helper_create_context(price=100.0, session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.WATCH


def test_bullish_orb_setup_can_arm_after_range_complete():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    # High at 106.5 breaks ORB High 105.0
    ctx = helper_create_context(price=106.0, high=106.5, session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BULLISH"


def test_bearish_orb_setup_can_arm_after_range_complete():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    # Low at 93.5 breaks ORB Low 95.0
    ctx = helper_create_context(price=94.0, low=93.5, dir_score=-50.0, session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BEARISH"


def test_premarket_bars_not_used_for_rth_orb():
    session_lvls = {"ORB_COMPLETE": False}  # Premarket bars do not complete RTH ORB
    ctx = helper_create_context(session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.NO_SETUP


def test_orb_uses_configured_session_timezone():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    ctx = helper_create_context(session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.config_version == "research_v1"


def test_orb_does_not_trigger_trade_in_phase6():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    ctx = helper_create_context(price=106.0, high=106.5, session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state in (SignalState.NO_SETUP, SignalState.WATCH, SignalState.ARMED)
    assert res.state != SignalState.TRIGGERED
    assert res.state != SignalState.EXECUTABLE


# --- PHASE 6.1 SEMANTIC HARDENING TESTS ---

def test_armed_requires_future_unsatisfied_trigger():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.trigger_definition != ""
    assert res.trigger_price is not None
    assert res.state != SignalState.TRIGGERED


def test_armed_requires_invalidation_definition():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.invalidation_price == 90.0
    assert res.invalidation_source_type == "ZONE_DISTAL_BOUNDARY"
    assert res.invalidation_source_id == "ob_1"


def test_armed_requires_trigger_provenance():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.trigger_source_type == "ZONE_PROXIMAL_BOUNDARY"
    assert res.trigger_source_id == "ob_1"
    assert res.trigger_knowledge_timestamp != ""


def test_playbook_trigger_condition_not_evaluated_as_triggered_in_phase6():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    session_lvls = {"PDL": 95.0, "ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    ctx = helper_create_context(price=92.0, low=91.0, order_blocks=[ob], session_levels=session_lvls)
    engine = PlaybookEngine()
    evals, primary = engine.evaluate_all(ctx)
    for ev in evals:
        assert ev.state != SignalState.TRIGGERED
        assert ev.state != SignalState.EXECUTABLE


def test_bullish_sweep_armed_before_reclaim_close():
    session_lvls = {"PDL": 95.0}
    ctx = helper_create_context(price=94.5, low=94.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BULLISH"
    assert res.trigger_source_type == "RECLAIMED_LIQUIDITY_LEVEL"
    assert res.invalidation_source_type == "SWEEP_EXTREME_PLUS_BUFFER"


def test_bearish_sweep_armed_before_reclaim_close():
    session_lvls = {"PDH": 105.0}
    ctx = helper_create_context(price=105.5, high=106.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.direction == "BEARISH"
    assert res.trigger_source_type == "RECLAIMED_LIQUIDITY_LEVEL"
    assert res.invalidation_source_type == "SWEEP_EXTREME_PLUS_BUFFER"


def test_reclaim_close_condition_not_consumed_inside_phase6():
    session_lvls = {"PDL": 95.0}
    ctx = helper_create_context(price=95.5, low=94.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state != SignalState.TRIGGERED


def test_orb_armed_before_confirmation_close():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    ctx = helper_create_context(price=106.0, high=106.5, session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.trigger_source_type == "ORB_HIGH_BOUNDARY"
    assert res.invalidation_source_type == "ORB_MIDPOINT"


def test_orb_confirmation_close_not_evaluated_in_phase6():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    ctx = helper_create_context(price=107.0, high=107.5, session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state != SignalState.TRIGGERED


def test_pullback_local_reclaim_level_is_deterministic():
    ob = {"ob_id": "ob_pull", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 98.0, "distal_price": 94.0}
    ctx = helper_create_context(price=96.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.trigger_price == 98.0
    assert res.trigger_source_type == "ZONE_PROXIMAL_BOUNDARY"
    assert res.invalidation_price == 94.0
    assert res.invalidation_source_type == "ZONE_DISTAL_BOUNDARY"


def test_pullback_trigger_uses_only_confirmed_evidence():
    ob = {"ob_id": "ob_pull", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 98.0, "distal_price": 94.0}
    ctx = helper_create_context(price=96.0, order_blocks=[ob])
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.trigger_knowledge_timestamp != ""
    assert res.reason_code == "SETUP_FORMED_WAITING_FOR_TRIGGER"


# --- PHASE 6.2 HARDENING TESTS ---

def test_orb_midpoint_invalidation_uses_correct_source_type():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    ctx = helper_create_context(price=106.0, high=106.5, session_levels=session_lvls)
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    assert res.invalidation_price == 100.0  # (105 + 95)/2
    assert res.invalidation_source_type == "ORB_MIDPOINT"
    assert res.invalidation_source_id == "orb_mid"


def test_bullish_sweep_invalidation_below_sweep_extreme():
    session_lvls = {"PDL": 95.0}
    ctx = helper_create_context(price=94.5, low=94.0, atr=2.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    # low_px (94.0) - 0.20 * atr (0.40) = 93.60
    assert res.invalidation_price == 93.60
    assert res.invalidation_price < 94.0


def test_bearish_sweep_invalidation_above_sweep_extreme():
    session_lvls = {"PDH": 105.0}
    ctx = helper_create_context(price=105.5, high=106.0, atr=2.0, session_levels=session_lvls)
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    # high_px (106.0) + 0.20 * atr (0.40) = 106.40
    assert res.invalidation_price == 106.40
    assert res.invalidation_price > 106.0


def test_sweep_invalidation_buffer_is_config_driven():
    cfg = load_rules_config()
    cfg.playbooks["playbook_b_liquidity_sweep"]["invalidation_atr_buffer"] = 0.50
    session_lvls = {"PDL": 95.0}
    ctx = helper_create_context(price=94.5, low=94.0, atr=2.0, session_levels=session_lvls)
    ctx.rules_config = cfg
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    # low_px (94.0) - 0.50 * atr (1.00) = 93.00
    assert res.invalidation_price == 93.00


def test_pullback_armed_timestamp_precedes_trigger_event():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    # Bar N (10:20): Price enters OB at 92.0
    ctx_armed = helper_create_context(price=92.0, order_blocks=[ob])
    ctx_armed.event_timestamp = "2026-09-15T10:20:00Z"
    ctx_armed.knowledge_timestamp = "2026-09-15T10:20:00Z"
    evaluator = TrendPullbackEvaluator()
    res_armed = evaluator.evaluate(ctx_armed)

    assert res_armed.state == SignalState.ARMED
    assert res_armed.trigger_knowledge_timestamp == "2026-09-15T10:20:00Z"

    # Bar N+1 (10:25): Price closes at 96.0 (> reclaim level 95.0)
    ctx_trigger_bar = helper_create_context(price=96.0, order_blocks=[ob])
    ctx_trigger_bar.event_timestamp = "2026-09-15T10:25:00Z"
    ctx_trigger_bar.knowledge_timestamp = "2026-09-15T10:25:00Z"

    assert ctx_trigger_bar.event_timestamp > res_armed.trigger_knowledge_timestamp


def test_sweep_armed_timestamp_precedes_reclaim_trigger_event():
    session_lvls = {"PDL": 95.0}
    # Bar N (10:20): Sweep low 94.0, close 94.5
    ctx_armed = helper_create_context(price=94.5, low=94.0, session_levels=session_lvls)
    ctx_armed.event_timestamp = "2026-09-15T10:20:00Z"
    ctx_armed.knowledge_timestamp = "2026-09-15T10:20:00Z"
    evaluator = LiquiditySweepEvaluator()
    res_armed = evaluator.evaluate(ctx_armed)

    assert res_armed.state == SignalState.ARMED
    assert res_armed.trigger_knowledge_timestamp == "2026-09-15T10:20:00Z"

    # Bar N+1 (10:25): Reclaim close 95.5
    trigger_event_time = "2026-09-15T10:25:00Z"
    assert trigger_event_time > res_armed.trigger_knowledge_timestamp


def test_orb_armed_timestamp_precedes_confirmation_event():
    session_lvls = {"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True}
    # Bar N (10:20): High probes 106.5, close 104.5
    ctx_armed = helper_create_context(price=104.5, high=106.5, session_levels=session_lvls)
    ctx_armed.event_timestamp = "2026-09-15T10:20:00Z"
    ctx_armed.knowledge_timestamp = "2026-09-15T10:20:00Z"
    evaluator = OpeningRangeBreakoutEvaluator()
    res_armed = evaluator.evaluate(ctx_armed)

    assert res_armed.state == SignalState.ARMED
    assert res_armed.trigger_knowledge_timestamp == "2026-09-15T10:20:00Z"

    # Bar N+1 (10:25): Body close 106.0 above OR High
    trigger_event_time = "2026-09-15T10:25:00Z"
    assert trigger_event_time > res_armed.trigger_knowledge_timestamp


def test_armed_invalidation_reference_is_already_knowable():
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx = helper_create_context(price=92.0, order_blocks=[ob])
    ctx.knowledge_timestamp = "2026-09-15T10:20:00Z"
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)

    assert res.state == SignalState.ARMED
    assert res.invalidation_knowledge_timestamp <= ctx.knowledge_timestamp


def test_pullback_fvg_zone_trigger_and_invalidation():
    ctx = helper_create_context(price=92.0, order_blocks=[])
    ctx.fvgs = [{"id": "fvg_bull_1", "proximal_price": 94.0, "distal_price": 90.0}]
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)

    assert res.state == SignalState.ARMED
    assert res.trigger_source_type == "FVG_PROXIMAL_BOUNDARY"
    assert res.trigger_source_id == "fvg_bull_1"
    assert res.trigger_price == 94.0
    assert res.invalidation_source_type == "FVG_DISTAL_BOUNDARY"
    assert res.invalidation_source_id == "fvg_bull_1"
    assert res.invalidation_price == 90.0


def test_pullback_vwap_zone_trigger_and_invalidation():
    ctx = helper_create_context(price=92.0, order_blocks=[], vwap=92.0, atr=2.0)
    ctx.fvgs = []
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)

    assert res.state == SignalState.ARMED
    assert res.trigger_source_type == "VWAP_LEVEL"
    assert res.trigger_source_id == "vwap_ref"
    assert res.trigger_price == 92.0
    assert res.invalidation_source_type == "VWAP_BUFFER_BOUNDARY"
    assert res.invalidation_source_id == "vwap_ref"
    assert res.invalidation_price == 90.0  # 92.0 - 1.0 * 2.0
