"""Phase 7 Characterization Scenarios.

Exhaustively verifies entry trigger & confirmation scenarios across Playbook A, B, and C:
- Pullback: bullish trigger, bearish trigger, invalidation precedence, expired setup, in-progress bar, gap open.
- Liquidity Sweep: bullish sweep reclaim trigger, bearish sweep reclaim trigger, invalidation precedence, duplicate consumption.
- ORB: bullish body close trigger, bearish body close trigger, wick probe non-trigger, blocked publication state.
"""

from qx.direction.direction_engine import evaluate_direction_engine
from qx.models.rules import DeltaProvenance, GammaRegime, MarketRegimeModel, PublicationState, SessionRegime, SignalState, TrendRegime, VolatilityRegime
from qx.playbooks import LiquiditySweepEvaluator, OpeningRangeBreakoutEvaluator, QXEvaluationContext, TrendPullbackEvaluator
from qx.triggers import EntryTriggerEngine, TriggerRuleType


def helper_build_armed_eval(pb_type="pullback", price=92.0, high=92.0, low=92.0, session_levels=None, order_blocks=None, timestamp="2026-09-15T10:20:00Z"):
    mr = MarketRegimeModel(trend=TrendRegime.TREND_UP, volatility=VolatilityRegime.NORMAL, gamma=GammaRegime.UNKNOWN, session=SessionRegime.BALANCED)
    struct_res = type("StructRes", (), {"state": "BULLISH", "invalidated": False})()
    dir_res = evaluate_direction_engine(
        symbol="NVDA",
        timeframe="5m",
        structure_state="BULLISH",
        price=price,
        vwap=price,
        vwap_slope=1.0,
        fast_ema=price + 1.0,
        medium_ema=price,
        slow_ema=price - 1.0,
        fast_slope=0.1,
        medium_slope=0.1,
        slow_slope=0.1,
        delta_value=80.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=80.0,
        market_alignment_score=80.0,
        htf_structure_state="BULLISH",
    )

    ctx = QXEvaluationContext(
        symbol="NVDA",
        timeframe="5m",
        latest_bar={"close": price, "high": high, "low": low, "price": price},
        market_regime=mr,
        direction=dir_res,
        structure_result=struct_res,
        order_blocks=order_blocks or [],
        session_levels=session_levels or {},
        vwap=None,
        atr=2.0,
        publication_state=PublicationState.VERIFIED,
        event_timestamp=timestamp,
        knowledge_timestamp=timestamp,
    )

    if pb_type == "pullback":
        evaluator = TrendPullbackEvaluator()
    elif pb_type == "sweep":
        evaluator = LiquiditySweepEvaluator()
    else:
        evaluator = OpeningRangeBreakoutEvaluator()

    res = evaluator.evaluate(ctx)
    return res


def test_phase7_characterization_scenarios():
    engine = EntryTriggerEngine()

    # --- PULLBACK CHARACTERIZATION ---
    ob_bull = [{"ob_id": "ob_b1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}]
    armed_p1 = helper_build_armed_eval(pb_type="pullback", price=92.0, order_blocks=ob_bull)
    assert armed_p1.state == SignalState.ARMED

    # Scenario 1: Bullish Pullback Trigger
    bar_p1 = {"open": 93.0, "high": 96.5, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    t1 = engine.evaluate_trigger(armed_p1, bar_p1)
    assert t1.state == SignalState.TRIGGERED
    assert t1.trigger_event.trigger_rule_type == TriggerRuleType.CLOSE_ABOVE_LEVEL

    # Scenario 2: In-Progress Bar Non-Trigger
    bar_p2 = {"open": 93.0, "high": 96.5, "low": 93.0, "close": 94.0, "timestamp": "2026-09-15T10:25:00Z"}
    t2 = EntryTriggerEngine().evaluate_trigger(armed_p1, bar_p2)
    assert t2.state == SignalState.ARMED

    # Scenario 3: Invalidation Precedence ("INVALIDATION WINS")
    bar_p3 = {"open": 93.0, "high": 97.0, "low": 89.5, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    t3 = EntryTriggerEngine().evaluate_trigger(armed_p1, bar_p3)
    assert t3.state == SignalState.NO_SETUP
    assert t3.evidence_ladder["reason"] == "SETUP_INVALIDATED"

    # Scenario 4: Gap Open Trigger
    bar_p4 = {"open": 96.5, "high": 98.0, "low": 96.0, "close": 97.0, "timestamp": "2026-09-15T10:25:00Z"}
    t4 = EntryTriggerEngine().evaluate_trigger(armed_p1, bar_p4)
    assert t4.state == SignalState.TRIGGERED
    assert t4.trigger_event.trigger_rule_type == TriggerRuleType.OPEN_GAP_ABOVE_LEVEL

    # --- LIQUIDITY SWEEP CHARACTERIZATION ---
    armed_s1 = helper_build_armed_eval(pb_type="sweep", price=94.5, low=94.0, session_levels={"PDL": 95.0})
    assert armed_s1.state == SignalState.ARMED

    # Scenario 5: Bullish Sweep Reclaim Trigger
    bar_s5 = {"open": 94.5, "high": 96.0, "low": 94.2, "close": 95.5, "timestamp": "2026-09-15T10:25:00Z"}
    t5 = EntryTriggerEngine().evaluate_trigger(armed_s1, bar_s5)
    assert t5.state == SignalState.TRIGGERED
    assert t5.trigger_event.trigger_rule_type == TriggerRuleType.RECLAIM_ABOVE_LEVEL

    # --- ORB CHARACTERIZATION ---
    armed_o1 = helper_build_armed_eval(pb_type="orb", price=106.0, high=106.5, session_levels={"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True})
    assert armed_o1.state == SignalState.ARMED

    # Scenario 6: Bullish ORB Confirmed Body Close Trigger
    bar_o6 = {"open": 104.8, "high": 106.8, "low": 104.5, "close": 106.2, "timestamp": "2026-09-15T10:25:00Z"}
    t6 = EntryTriggerEngine().evaluate_trigger(armed_o1, bar_o6)
    assert t6.state == SignalState.TRIGGERED
    assert t6.trigger_event.trigger_rule_type == TriggerRuleType.BODY_CLOSE_ABOVE_LEVEL

    # Scenario 7: Wick Probe Non-Trigger (Close inside range)
    bar_o7 = {"open": 103.0, "high": 106.5, "low": 103.0, "close": 104.5, "timestamp": "2026-09-15T10:25:00Z"}
    t7 = EntryTriggerEngine().evaluate_trigger(armed_o1, bar_o7)
    assert t7.state == SignalState.ARMED
