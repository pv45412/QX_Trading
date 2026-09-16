"""Phase 6 Characterization Scenarios.

Exhaustively verifies representative setup scenarios across Playbook A, B, and C:
- Pullback: bullish WATCH, bullish ARMED, bearish WATCH, bearish ARMED, invalidated structure, OB unavailable, OB mitigated, OB expired.
- Liquidity Sweep: approaching PDL, bullish PDL sweep, approaching PDH, bearish PDH sweep, EQL sweep, EQH sweep, fake proximity.
- ORB: range forming, completed inside range, bullish setup, bearish setup, overextended breakout, oversized range, quiet range.
"""

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
    QXEvaluationContext,
    TrendPullbackEvaluator,
)
from qx.regime.market_regime import evaluate_market_regime
from qx.direction.direction_engine import evaluate_direction_engine


def helper_build_context(
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


def test_phase6_characterization_scenarios():
    eval_pullback = TrendPullbackEvaluator()
    eval_sweep = LiquiditySweepEvaluator()
    eval_orb = OpeningRangeBreakoutEvaluator()

    # --- PULLBACK CHARACTERIZATION ---

    # 1. Bullish WATCH
    ob_bull = {"ob_id": "ob_b1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx_p1 = helper_build_context(price=97.0, order_blocks=[ob_bull])
    p1 = eval_pullback.evaluate(ctx_p1)
    assert p1.state == SignalState.WATCH
    assert p1.direction == "BULLISH"
    assert "ob_b1" in p1.source_order_block_ids

    # 2. Bullish ARMED
    ctx_p2 = helper_build_context(price=92.0, order_blocks=[ob_bull])
    p2 = eval_pullback.evaluate(ctx_p2)
    assert p2.state == SignalState.ARMED
    assert p2.trigger_price is not None
    assert p2.invalidation_price is not None

    # 3. Bearish WATCH
    ob_bear = {"ob_id": "ob_br1", "type": "BEARISH_OB", "state": "VALIDATED", "proximal_price": 105.0, "distal_price": 110.0}
    ctx_p3 = helper_build_context(trend=TrendRegime.TREND_DOWN, struct_state="BEARISH", dir_score=-80.0, price=103.0, order_blocks=[ob_bear])
    p3 = eval_pullback.evaluate(ctx_p3)
    assert p3.state == SignalState.WATCH
    assert p3.direction == "BEARISH"

    # 4. Bearish ARMED
    ctx_p4 = helper_build_context(trend=TrendRegime.TREND_DOWN, struct_state="BEARISH", dir_score=-80.0, price=107.0, order_blocks=[ob_bear])
    p4 = eval_pullback.evaluate(ctx_p4)
    assert p4.state == SignalState.ARMED

    # 5. Invalidated Structure
    ctx_p5 = helper_build_context(price=92.0, struct_invalidated=True, order_blocks=[ob_bull])
    p5 = eval_pullback.evaluate(ctx_p5)
    assert p5.state == SignalState.NO_SETUP

    # 6. OB Unavailable
    ctx_p6 = helper_build_context(price=92.0, order_blocks=[])
    p6 = eval_pullback.evaluate(ctx_p6)
    assert p6.state == SignalState.NO_SETUP

    # 7. OB Mitigated
    ob_mit = {"ob_id": "ob_mit1", "type": "BULLISH_OB", "state": "MITIGATED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx_p7 = helper_build_context(price=92.0, order_blocks=[ob_mit])
    p7 = eval_pullback.evaluate(ctx_p7)
    assert p7.state == SignalState.ARMED

    # 8. OB Expired
    ob_exp = {"ob_id": "ob_exp1", "type": "BULLISH_OB", "state": "EXPIRED", "proximal_price": 95.0, "distal_price": 90.0}
    ctx_p8 = helper_build_context(price=92.0, order_blocks=[ob_exp])
    p8 = eval_pullback.evaluate(ctx_p8)
    assert p8.state == SignalState.NO_SETUP


    # --- SWEEP CHARACTERIZATION ---

    # 9. Approaching PDL
    ctx_s9 = helper_build_context(price=96.0, low=95.5, session_levels={"PDL": 95.0})
    s9 = eval_sweep.evaluate(ctx_s9)
    assert s9.state == SignalState.WATCH
    assert s9.direction == "BULLISH"

    # 10. Bullish PDL Sweep
    ctx_s10 = helper_build_context(price=94.5, low=94.0, session_levels={"PDL": 95.0})
    s10 = eval_sweep.evaluate(ctx_s10)
    assert s10.state == SignalState.ARMED
    assert s10.direction == "BULLISH"

    # 11. Approaching PDH
    ctx_s11 = helper_build_context(price=104.0, high=104.5, session_levels={"PDH": 105.0})
    s11 = eval_sweep.evaluate(ctx_s11)
    assert s11.state == SignalState.WATCH
    assert s11.direction == "BEARISH"

    # 12. Bearish PDH Sweep
    ctx_s12 = helper_build_context(price=105.5, high=106.0, session_levels={"PDH": 105.0})
    s12 = eval_sweep.evaluate(ctx_s12)
    assert s12.state == SignalState.ARMED
    assert s12.direction == "BEARISH"

    # 13. Equal Low Sweep
    ctx_s13 = helper_build_context(price=89.5, low=89.0, session_levels={"EQL": 90.0})
    s13 = eval_sweep.evaluate(ctx_s13)
    assert s13.state == SignalState.ARMED
    assert "eql_level" in s13.source_pivot_ids

    # 14. Equal High Sweep
    ctx_s14 = helper_build_context(price=110.5, high=111.0, session_levels={"EQH": 110.0})
    s14 = eval_sweep.evaluate(ctx_s14)
    assert s14.state == SignalState.ARMED
    assert "eqh_level" in s14.source_pivot_ids

    # 15. Fake Proximity without Sweep
    ctx_s15 = helper_build_context(price=120.0, low=120.0, session_levels={"PDL": 90.0})
    s15 = eval_sweep.evaluate(ctx_s15)
    assert s15.state == SignalState.NO_SETUP


    # --- ORB CHARACTERIZATION ---

    # 16. Range Still Forming
    ctx_o16 = helper_build_context(session_levels={"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": False})
    o16 = eval_orb.evaluate(ctx_o16)
    assert o16.state == SignalState.NO_SETUP

    # 17. Completed Range, Inside Range
    ctx_o17 = helper_build_context(price=100.0, session_levels={"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True})
    o17 = eval_orb.evaluate(ctx_o17)
    assert o17.state == SignalState.WATCH

    # 18. Bullish Setup
    ctx_o18 = helper_build_context(price=106.0, high=106.5, session_levels={"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True})
    o18 = eval_orb.evaluate(ctx_o18)
    assert o18.state == SignalState.ARMED
    assert o18.direction == "BULLISH"

    # 19. Bearish Setup
    ctx_o19 = helper_build_context(price=94.0, low=93.5, dir_score=-60.0, session_levels={"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True})
    o19 = eval_orb.evaluate(ctx_o19)
    assert o19.state == SignalState.ARMED
    assert o19.direction == "BEARISH"

    # 20. Overextended Breakout
    ctx_o20 = helper_build_context(price=120.0, high=120.0, session_levels={"ORB_HIGH": 105.0, "ORB_LOW": 95.0, "ORB_COMPLETE": True})
    o20 = eval_orb.evaluate(ctx_o20)
    assert o20.state == SignalState.NO_SETUP

    # 21. Oversized Opening Range
    ctx_o21 = helper_build_context(price=100.0, atr=2.0, session_levels={"ORB_HIGH": 120.0, "ORB_LOW": 80.0, "ORB_COMPLETE": True})
    o21 = eval_orb.evaluate(ctx_o21)
    assert o21.setup_quality_components["orb_range_atr"] == 20.0  # (120-80)/2.0

    # 22. Quiet Opening Range
    ctx_o22 = helper_build_context(price=100.0, atr=2.0, session_levels={"ORB_HIGH": 101.0, "ORB_LOW": 99.0, "ORB_COMPLETE": True})
    o22 = eval_orb.evaluate(ctx_o22)
    assert o22.setup_quality_components["orb_range_atr"] == 1.0  # (101-99)/2.0
