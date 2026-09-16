"""Phase 7 Unit Test Suite: Entry Trigger & Confirmation Engine.

Verifies:
- ARMED -> TRIGGERED state transition
- Prohibition of EXECUTABLE state
- Temporal provenance separation (armed_at <= trigger_level_known_at <= trigger_event_timestamp <= trigger_confirmed_at)
- Pullback, Liquidity Sweep, and ORB trigger rules
- Invalidation precedence ("INVALIDATION WINS")
- Bar completion requirement
- Gap open trigger handling
- Duplicate trigger prevention
- Armed setup lifetime expiration
- Publication state gating
"""

import pytest
from qx.config.rules_config import load_rules_config
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
    PlaybookEvaluation,
    QXEvaluationContext,
    TrendPullbackEvaluator,
)
from qx.triggers import EntryTriggerEngine, TriggerEvent, TriggerRuleType, TriggeredSetupResult


from qx.direction.direction_engine import evaluate_direction_engine


def helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0, timestamp="2026-09-15T10:20:00Z"):
    ob = {"ob_id": "ob_1", "type": "BULLISH_OB", "state": "VALIDATED", "proximal_price": ob_prox, "distal_price": ob_dist}
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
        latest_bar={"close": price, "high": price, "low": price, "price": price},
        market_regime=mr,
        direction=dir_res,
        structure_result=struct_res,
        order_blocks=[ob],
        session_levels={},
        vwap=None,
        atr=2.0,
        publication_state=PublicationState.VERIFIED,
        event_timestamp=timestamp,
        knowledge_timestamp=timestamp,
    )
    evaluator = TrendPullbackEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    return res


def helper_make_armed_sweep(price=94.5, low=94.0, pdl=95.0, timestamp="2026-09-15T10:20:00Z"):
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
        delta_value=50.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=50.0,
        market_alignment_score=50.0,
        htf_structure_state="BULLISH",
    )

    ctx = QXEvaluationContext(
        symbol="NVDA",
        timeframe="5m",
        latest_bar={"close": price, "high": price, "low": low, "price": price},
        market_regime=mr,
        direction=dir_res,
        structure_result=struct_res,
        order_blocks=[],
        session_levels={"PDL": pdl},
        vwap=None,
        atr=2.0,
        publication_state=PublicationState.VERIFIED,
        event_timestamp=timestamp,
        knowledge_timestamp=timestamp,
    )
    evaluator = LiquiditySweepEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    return res


def helper_make_armed_orb(price=106.0, high=106.5, orb_high=105.0, orb_low=95.0, timestamp="2026-09-15T10:20:00Z"):
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
        delta_value=50.0,
        delta_provenance=DeltaProvenance.ACTUAL_TRADE_AGGRESSOR,
        relative_strength_score=50.0,
        market_alignment_score=50.0,
        htf_structure_state="BULLISH",
    )

    ctx = QXEvaluationContext(
        symbol="NVDA",
        timeframe="5m",
        latest_bar={"close": price, "high": high, "low": price, "price": price},
        market_regime=mr,
        direction=dir_res,
        structure_result=struct_res,
        order_blocks=[],
        session_levels={"ORB_HIGH": orb_high, "ORB_LOW": orb_low, "ORB_COMPLETE": True},
        vwap=None,
        atr=2.0,
        publication_state=PublicationState.VERIFIED,
        event_timestamp=timestamp,
        knowledge_timestamp=timestamp,
    )
    evaluator = OpeningRangeBreakoutEvaluator()
    res = evaluator.evaluate(ctx)
    assert res.state == SignalState.ARMED
    return res


# --- TESTS ---

def test_armed_to_triggered_state_transition():
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0)
    engine = EntryTriggerEngine()

    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=1, armed_bar_idx=0)

    assert res.state == SignalState.TRIGGERED
    assert res.trigger_event is not None
    assert res.trigger_event.trigger_rule_type == TriggerRuleType.CLOSE_ABOVE_LEVEL


def test_executable_state_prohibited_in_phase7():
    armed_eval = helper_make_armed_pullback()
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=1, armed_bar_idx=0)

    with pytest.raises(ValueError, match="EXECUTABLE"):
        TriggeredSetupResult(
            playbook_evaluation_id=res.playbook_evaluation_id,
            playbook_id=res.playbook_id,
            symbol=res.symbol,
            timeframe=res.timeframe,
            direction=res.direction,
            state=SignalState.EXECUTABLE,
            trigger_event=res.trigger_event,
            armed_at=res.armed_at,
            trigger_level_known_at=res.trigger_level_known_at,
            trigger_event_timestamp=res.trigger_event_timestamp,
            trigger_confirmed_at=res.trigger_confirmed_at,
            trigger_price=res.trigger_price,
            invalidation_price=res.invalidation_price,
            publication_state=res.publication_state,
        )


def test_trade_state_is_none_tradeability_not_yet_evaluated():
    armed_eval = helper_make_armed_pullback()
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=1, armed_bar_idx=0)
    assert res.trade_state == "NONE - TRADEABILITY NOT YET EVALUATED"


def test_temporal_provenance_separation():
    armed_eval = helper_make_armed_pullback(timestamp="2026-09-15T10:20:00Z")
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=1, armed_bar_idx=0)

    assert res.armed_at == "2026-09-15T10:20:00Z"
    assert res.trigger_level_known_at == "2026-09-15T10:20:00Z"
    assert res.trigger_event_timestamp == "2026-09-15T10:25:00Z"
    assert res.trigger_confirmed_at == "2026-09-15T10:25:00Z"
    assert res.armed_at <= res.trigger_level_known_at <= res.trigger_event_timestamp <= res.trigger_confirmed_at


def test_pullback_reclaim_close_trigger():
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)
    assert res.state == SignalState.TRIGGERED
    assert res.trigger_event.trigger_rule_type == TriggerRuleType.CLOSE_ABOVE_LEVEL
    assert res.trigger_price == 95.0


def test_liquidity_sweep_reclaim_close_trigger():
    armed_eval = helper_make_armed_sweep(price=94.5, pdl=95.0)
    engine = EntryTriggerEngine()
    bar = {"open": 94.5, "high": 96.0, "low": 94.2, "close": 95.5, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)
    assert res.state == SignalState.TRIGGERED
    assert res.trigger_event.trigger_rule_type == TriggerRuleType.RECLAIM_ABOVE_LEVEL
    assert res.trigger_price == 95.0


def test_orb_body_close_trigger():
    armed_eval = helper_make_armed_orb(price=104.5, high=106.5, orb_high=105.0)
    engine = EntryTriggerEngine()
    # Body close (open 104.8, close 106.0) above OR High 105.0
    bar = {"open": 104.8, "high": 106.5, "low": 104.5, "close": 106.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)
    assert res.state == SignalState.TRIGGERED
    assert res.trigger_event.trigger_rule_type == TriggerRuleType.BODY_CLOSE_ABOVE_LEVEL


def test_same_bar_invalidation_wins():
    # Bullish setup: trigger=95.0, invalidation=90.0
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0)
    engine = EntryTriggerEngine()
    # Volatile bar: low=89.0 (< 90.0 invalidation), close=96.0 (> 95.0 trigger)
    bar = {"open": 93.0, "high": 97.0, "low": 89.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)

    # INVALIDATION WINS -> state must NOT be TRIGGERED
    assert res.state == SignalState.NO_SETUP
    assert res.state != SignalState.TRIGGERED
    assert res.evidence_ladder["reason"] == "SETUP_INVALIDATED"


def test_in_progress_candle_not_triggered_until_close():
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    engine = EntryTriggerEngine()
    # Candle that closes below trigger price (94.0 < 95.0)
    bar = {"open": 93.0, "high": 96.5, "low": 93.0, "close": 94.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)
    assert res.state == SignalState.ARMED  # Remains ARMED awaiting bar close confirmation


def test_gap_open_handling():
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0)
    engine = EntryTriggerEngine()
    # Gap open at 97.0 (> trigger 95.0, > invalidation 90.0)
    bar = {"open": 97.0, "high": 98.0, "low": 96.5, "close": 97.5, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)

    assert res.state == SignalState.TRIGGERED
    assert res.trigger_event.trigger_rule_type == TriggerRuleType.OPEN_GAP_ABOVE_LEVEL
    assert res.trigger_event.confirmation_method == "OPEN_GAP_CONFIRMED"


def test_duplicate_trigger_prevention():
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    engine = EntryTriggerEngine()
    bar1 = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res1 = engine.evaluate_trigger(armed_eval, bar1, bar_idx=1, armed_bar_idx=0)
    assert res1.state == SignalState.TRIGGERED

    # Subsequent bar on same setup evaluation — terminal state, must be rejected
    bar2 = {"open": 96.0, "high": 98.0, "low": 95.5, "close": 97.0, "timestamp": "2026-09-15T10:30:00Z"}
    res2 = engine.evaluate_trigger(armed_eval, bar2, bar_idx=2, armed_bar_idx=0)
    assert res2.state == SignalState.NO_SETUP
    # Engine marks triggered eval as terminal; reason is EVALUATION_IS_TERMINAL
    assert res2.evidence_ladder["reason"] == "EVALUATION_IS_TERMINAL"


def test_max_armed_bars_expiration():
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T11:30:00Z"}
    # bar_idx=15 > armed_bar_idx=0 + max_armed_bars=12
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=15, armed_bar_idx=0)
    assert res.state == SignalState.NO_SETUP
    assert res.evidence_ladder["reason"] == "SETUP_EXPIRED"


def test_blocked_publication_state_cannot_trigger():
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    armed_eval.publication_state = PublicationState.BLOCKED
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)
    assert res.state == SignalState.NO_SETUP
    assert res.evidence_ladder["reason"] == "BLOCKED_PUBLICATION_STATE"


# ─── Phase 7.1 Temporal Causality Tests ──────────────────────────────────────

def test_trigger_level_known_no_later_than_armed_time():
    """trigger_level_known_at must be <= armed_at (i.e. the level existed before arming)."""
    armed_eval = helper_make_armed_pullback(
        price=92.0, ob_prox=95.0, ob_dist=90.0, timestamp="2026-09-15T10:20:00Z"
    )
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=1, armed_bar_idx=0)
    assert res.state == SignalState.TRIGGERED
    # trigger_level_known_at == armed_at is the equality case and is valid
    assert res.trigger_level_known_at <= res.armed_at


def test_trigger_event_occurs_after_armed_time():
    """trigger_event_timestamp must be strictly > armed_at."""
    armed_eval = helper_make_armed_pullback(
        price=92.0, ob_prox=95.0, ob_dist=90.0, timestamp="2026-09-15T10:20:00Z"
    )
    engine = EntryTriggerEngine()
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=1, armed_bar_idx=0)
    assert res.state == SignalState.TRIGGERED
    # trigger_event_timestamp must be strictly after armed_at
    assert res.trigger_event_timestamp > res.armed_at


def test_same_bar_arm_and_trigger_is_rejected():
    """A setup may not become ARMED and TRIGGERED from the same bar.

    bar_idx <= armed_bar_idx means they occurred on the same or earlier bar.
    The engine must return ARMED (not TRIGGERED) and include the rejection reason.
    """
    armed_eval = helper_make_armed_pullback(
        price=92.0, ob_prox=95.0, ob_dist=90.0, timestamp="2026-09-15T10:20:00Z"
    )
    engine = EntryTriggerEngine()
    # Same bar: bar_idx == armed_bar_idx
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:20:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=0, armed_bar_idx=0)
    assert res.state == SignalState.ARMED
    assert res.evidence_ladder["reason"] == "SAME_BAR_ARM_AND_TRIGGER_REJECTED"


# ─── Phase 7.1 BODY_CLOSE Orientation Tests ──────────────────────────────────

def test_body_close_bullish_candle_above_level_triggers():
    """BODY_CLOSE (bullish): close > trigger_level AND close > open (bullish orientation)."""
    armed_eval = helper_make_armed_orb(price=104.5, high=106.5, orb_high=105.0)
    engine = EntryTriggerEngine()
    # Bullish candle: open=104.8, close=106.0 — close > 105.0 AND close > open
    bar = {"open": 104.8, "high": 106.5, "low": 104.5, "close": 106.0, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)
    assert res.state == SignalState.TRIGGERED
    assert res.trigger_event.trigger_rule_type == TriggerRuleType.BODY_CLOSE_ABOVE_LEVEL


def test_body_close_wick_above_but_close_below_does_not_trigger():
    """BODY_CLOSE (bullish): wick pokes above trigger but close is below — must NOT trigger."""
    armed_eval = helper_make_armed_orb(price=104.5, high=106.5, orb_high=105.0)
    engine = EntryTriggerEngine()
    # Wick to 106.0 but candle closes at 104.8 (< 105.0)
    bar = {"open": 104.5, "high": 106.0, "low": 104.0, "close": 104.8, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar)
    assert res.state == SignalState.ARMED  # No trigger; wick only


def test_body_close_bearish_orientation_required_for_bearish_rule():
    """BODY_CLOSE (bearish ORB): candle orientation is required in addition to price level crossing.

    BODY_CLOSE_BELOW_LEVEL semantics:
      Bearish trigger: close < trigger_price AND close < open (bearish candle orientation)

    This test uses a directly-constructed PlaybookEvaluation to control trigger geometry precisely,
    avoiding geometric contradictions from the ORB evaluator gap path.

    Scenario:
      - BEARISH ORB setup with trigger_price=95.0 (ORB_LOW), invalidation_price=100.0
      - Bar: open=95.5 (above trigger, no gap-down), close=94.8 (below trigger=95.0), close < open
        → This IS a bearish body close and MUST trigger
      - Bar: open=95.5, close=94.8 but close > open (impossible geometrically with those values,
        so we test the orientation inversion through engine rule directly)

    Instead, we test the bearish BODY_CLOSE via a bearish-then-trigger bar, and verify the
    complementary wick-only non-trigger (wick below trigger but bearish close above trigger).
    """
    from qx.models.rules import GammaRegime, MarketRegimeModel, SessionRegime, TrendRegime, VolatilityRegime
    from qx.playbooks.base import PlaybookEvaluation

    mr = MarketRegimeModel(
        trend=TrendRegime.TREND_DOWN,
        volatility=VolatilityRegime.NORMAL,
        gamma=GammaRegime.UNKNOWN,
        session=SessionRegime.BALANCED,
    )
    # Construct bearish ORB armed evaluation directly
    armed_eval = PlaybookEvaluation(
        playbook_id="playbook_c_orb_breakout",
        symbol="NVDA",
        timeframe="5m",
        direction="BEARISH",
        state=SignalState.ARMED,
        setup_detected=True,
        trigger_definition="5m body close below ORB Low",
        trigger_price=95.0,            # ORB_LOW
        trigger_source_type="ORB_LOW",
        trigger_source_id="orb_session_20260915",
        trigger_knowledge_timestamp="2026-09-15T10:20:00Z",
        invalidation_price=100.0,      # ORB midpoint or prior swing
        invalidation_source_type="ORB_HIGH",
        invalidation_source_id="orb_session_20260915",
        invalidation_knowledge_timestamp="2026-09-15T10:20:00Z",
        market_regime=mr,
        event_timestamp="2026-09-15T10:20:00Z",
        knowledge_timestamp="2026-09-15T10:20:00Z",
        reason_code="SETUP_FORMED_WAITING_FOR_TRIGGER",
    )
    assert armed_eval.direction == "BEARISH"

    engine = EntryTriggerEngine()

    # Test A: Bearish body close below ORB_LOW — MUST trigger
    # open=96.0 (above trigger=95.0 → no gap-down since bearish gap needs open <= trigger)
    # close=94.5 (below trigger=95.0), close < open → bearish candle orientation → TRIGGERS
    bar_a = {"open": 96.0, "high": 96.5, "low": 94.3, "close": 94.5, "timestamp": "2026-09-15T10:25:00Z"}
    res_a = engine.evaluate_trigger(armed_eval, bar_a, bar_idx=1, armed_bar_idx=0)
    assert res_a.state == SignalState.TRIGGERED, "Bearish body close must trigger"
    assert res_a.trigger_event.trigger_rule_type == TriggerRuleType.BODY_CLOSE_BELOW_LEVEL

    # Test B: Wick only below trigger, bearish close above trigger — must NOT trigger
    # A new engine instance (the eval_id from test A is now terminal in the previous engine)
    engine2 = EntryTriggerEngine()
    # Wick dips to 94.5 (below 95.0) but close=95.8 (above trigger) — wick only
    bar_b = {"open": 96.0, "high": 96.5, "low": 94.5, "close": 95.8, "timestamp": "2026-09-15T10:25:00Z"}
    res_b = engine2.evaluate_trigger(armed_eval, bar_b, bar_idx=1, armed_bar_idx=0)
    assert res_b.state == SignalState.ARMED, "Wick below trigger with close above must remain ARMED"


# ─── Phase 7.1 Gap Handling Tests ────────────────────────────────────────────

def test_gap_open_records_actual_bar_open_not_trigger_price():
    """Gap triggers must record actual bar_open, never synthesise a fill at trigger_price."""
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0)
    engine = EntryTriggerEngine()
    # Gap: open=98.0, which is well above trigger=95.0
    bar = {"open": 98.0, "high": 99.0, "low": 97.5, "close": 98.5, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, atr=2.0)

    assert res.state == SignalState.TRIGGERED
    assert res.trigger_event.gap_beyond_trigger is True
    assert res.trigger_event.bar_open == 98.0  # Actual open recorded
    assert res.trigger_event.observed_price == 98.0  # observed_price = bar_open for gaps
    # trigger_price is the level, not the fill
    assert res.trigger_event.trigger_price == 95.0
    # Gap distance and ATR metrics are present
    assert res.trigger_event.gap_distance == pytest.approx(3.0, abs=0.01)
    assert res.trigger_event.gap_distance_atr == pytest.approx(1.5, abs=0.01)
    assert res.trigger_event.confirmation_method == "OPEN_GAP_CONFIRMED"


def test_gap_open_fields_present_in_evidence_ladder():
    """Gap metadata is recorded in the evidence_ladder of the triggered result."""
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0)
    engine = EntryTriggerEngine()
    bar = {"open": 97.0, "high": 98.0, "low": 96.5, "close": 97.5, "timestamp": "2026-09-15T10:25:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, atr=2.0)

    assert res.state == SignalState.TRIGGERED
    assert res.evidence_ladder["gap_beyond_trigger"] is True
    assert "gap_distance" in res.evidence_ladder
    assert "gap_distance_atr" in res.evidence_ladder
    assert res.evidence_ladder["gap_distance"] == pytest.approx(2.0, abs=0.01)
    assert res.evidence_ladder["gap_distance_atr"] == pytest.approx(1.0, abs=0.01)


# ─── Phase 7.1 Audit: Item 2 — Configuration-Driven Expiration ───────────────

def test_max_armed_bars_is_config_driven():
    """max_armed_bars must be loaded from versioned rules_config_v1.json, not a Python constant.

    The config structure is:
        trigger_confirmation.max_armed_bars.<playbook_id>.<timeframe> = N

    This test:
    1. Reads the live config via load_rules_config()
    2. Confirms the per-playbook, per-timeframe structure is present
    3. Patches max_armed_bars to a custom low value and verifies the engine respects it
    """
    from qx.config.rules_config import load_rules_config, TriggerConfirmationConfig, RulesEngineConfig

    # 1. Load the live config and assert structure
    cfg = load_rules_config()
    assert cfg.trigger_confirmation is not None, "trigger_confirmation must exist in config"
    max_armed = cfg.trigger_confirmation.max_armed_bars
    assert isinstance(max_armed, dict), "max_armed_bars must be a dict keyed by playbook_id"

    # Verify all three playbooks are present
    assert "playbook_a_pullback" in max_armed
    assert "playbook_b_liquidity_sweep" in max_armed
    assert "playbook_c_orb_breakout" in max_armed

    # Verify per-timeframe nesting
    for pb_id in ("playbook_a_pullback", "playbook_b_liquidity_sweep", "playbook_c_orb_breakout"):
        pb_cfg = max_armed[pb_id]
        assert isinstance(pb_cfg, dict), f"{pb_id} must map timeframe -> int"
        assert "5m" in pb_cfg, f"{pb_id} must include a '5m' config"
        assert isinstance(pb_cfg["5m"], int), f"{pb_id}['5m'] must be an integer"

    # 2. Confirmed values from rules_config_v1.json
    assert max_armed["playbook_a_pullback"]["5m"] == 12
    assert max_armed["playbook_b_liquidity_sweep"]["5m"] == 8
    assert max_armed["playbook_c_orb_breakout"]["5m"] == 12

    # 3. Patch config to max_armed_bars=2 and verify engine expires after 2 bars
    custom_trig_cfg = TriggerConfirmationConfig(
        max_armed_bars={
            "playbook_a_pullback": {"1m": 2, "5m": 2, "15m": 2},
            "playbook_b_liquidity_sweep": {"1m": 2, "5m": 2, "15m": 2},
            "playbook_c_orb_breakout": {"1m": 2, "5m": 2, "15m": 2},
        }
    )
    custom_cfg = RulesEngineConfig(trigger_confirmation=custom_trig_cfg)

    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    engine = EntryTriggerEngine(rules_config=custom_cfg)

    # bar_idx=3 > armed_bar_idx=0 + max_armed_bars=2 → EXPIRED
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:35:00Z"}
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=3, armed_bar_idx=0)
    assert res.state == SignalState.NO_SETUP
    assert res.evidence_ladder["reason"] == "SETUP_EXPIRED"
    assert res.evidence_ladder["max_armed_bars"] == 2  # Custom value from config, not hardcoded 12


# ─── Phase 7.1 Audit: Item 3 — Terminal State Immutability ───────────────────

def test_triggered_eval_is_terminal():
    """After TRIGGERED, the same source_playbook_evaluation_id must never produce another trigger.

    A new ARMED evaluation ID is required for a new market opportunity.
    """
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    engine = EntryTriggerEngine()

    bar1 = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:25:00Z"}
    res1 = engine.evaluate_trigger(armed_eval, bar1, bar_idx=1, armed_bar_idx=0)
    assert res1.state == SignalState.TRIGGERED

    # Attempt to trigger again on the same eval_id — must be rejected as terminal
    bar2 = {"open": 96.5, "high": 99.0, "low": 96.0, "close": 98.0, "timestamp": "2026-09-15T10:30:00Z"}
    res2 = engine.evaluate_trigger(armed_eval, bar2, bar_idx=2, armed_bar_idx=0)
    assert res2.state == SignalState.NO_SETUP
    assert res2.evidence_ladder["reason"] == "EVALUATION_IS_TERMINAL"


def test_invalidated_eval_is_terminal():
    """After SETUP_INVALIDATED (invalidation condition hit), the eval_id must never trigger.

    Invalidation is a terminal outcome. Even if price later re-crosses the trigger level,
    a new ARMED evaluation is required.
    """
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0)
    engine = EntryTriggerEngine()

    # Bar that violates invalidation (low=89.0 < invalidation=90.0)
    bar1 = {"open": 93.0, "high": 94.0, "low": 89.0, "close": 93.5, "timestamp": "2026-09-15T10:25:00Z"}
    res1 = engine.evaluate_trigger(armed_eval, bar1, bar_idx=1, armed_bar_idx=0)
    assert res1.state == SignalState.NO_SETUP
    assert res1.evidence_ladder["reason"] == "SETUP_INVALIDATED"

    # Attempt to evaluate again on the same eval_id — must be terminal
    bar2 = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:30:00Z"}
    res2 = engine.evaluate_trigger(armed_eval, bar2, bar_idx=2, armed_bar_idx=0)
    assert res2.state == SignalState.NO_SETUP
    assert res2.evidence_ladder["reason"] == "EVALUATION_IS_TERMINAL"


def test_expired_eval_is_terminal():
    """After SETUP_EXPIRED (max_armed_bars exceeded), the eval_id must never trigger.

    Expiry is a terminal outcome. Even if price later satisfies the trigger, the setup
    has lapsed and a new ARMED evaluation is required.
    """
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0)
    engine = EntryTriggerEngine()

    # bar_idx=15 > 0 + max_armed_bars=12 → EXPIRED
    bar1 = {"open": 93.0, "high": 94.0, "low": 93.0, "close": 93.5, "timestamp": "2026-09-15T11:30:00Z"}
    res1 = engine.evaluate_trigger(armed_eval, bar1, bar_idx=15, armed_bar_idx=0)
    assert res1.state == SignalState.NO_SETUP
    assert res1.evidence_ladder["reason"] == "SETUP_EXPIRED"

    # Attempt to evaluate again on same eval_id — must be terminal
    bar2 = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T11:35:00Z"}
    res2 = engine.evaluate_trigger(armed_eval, bar2, bar_idx=16, armed_bar_idx=0)
    assert res2.state == SignalState.NO_SETUP
    assert res2.evidence_ladder["reason"] == "EVALUATION_IS_TERMINAL"


# ─── Phase 7.1 Audit: Item 4 — Trigger Source Re-Validation ──────────────────

def test_invalidated_trigger_source_cannot_trigger():
    """Order Block that was valid at ARMED time but becomes invalidated before trigger time
    must prevent the trigger from firing.

    Scenario:
      10:20 — Pullback ARMED; Order Block state=VALIDATED
      10:25 — Order Block state transitions to INVALIDATED
      10:30 — Price closes above old trigger level
    Expected: NOT TRIGGERED (reason: SOURCE_INVALIDATED_AT_TRIGGER)
    """
    ob = {
        "ob_id": "ob_1",
        "type": "BULLISH_OB",
        "state": "VALIDATED",   # Valid at arming time
        "proximal_price": 95.0,
        "distal_price": 90.0,
    }
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0, timestamp="2026-09-15T10:20:00Z")
    engine = EntryTriggerEngine()

    # Simulate OB becoming invalidated before the trigger bar
    invalidated_ob = {
        "ob_id": "ob_1",
        "type": "BULLISH_OB",
        "state": "INVALIDATED",  # OB state at trigger evaluation time
        "proximal_price": 95.0,
        "distal_price": 90.0,
    }

    # 10:30 bar: price closes above trigger=95.0 — would trigger if OB were still valid
    bar = {"open": 93.0, "high": 97.0, "low": 93.0, "close": 96.0, "timestamp": "2026-09-15T10:30:00Z"}
    res = engine.evaluate_trigger(
        armed_eval, bar,
        bar_idx=2, armed_bar_idx=0,
        source_order_block=invalidated_ob,  # OB now invalidated
    )

    assert res.state == SignalState.NO_SETUP
    assert res.evidence_ladder["reason"] == "SOURCE_INVALIDATED_AT_TRIGGER"
    assert res.trigger_source_valid is False


# ─── Phase 7.1 Audit: Item 5 — Gap + Same-Bar Invalidation Policy ────────────

def test_gap_trigger_same_bar_invalidation_is_rejected_without_intrabar_ordering():
    """When a bar opens beyond the trigger AND the same bar violates invalidation,
    and intrabar ordering is unavailable, INVALIDATION WINS — no trigger produced.

    Scenario (Bullish Pullback):
      trigger_price    = 95.0  (OB proximal — trigger above)
      invalidation_price = 90.0 (OB distal — invalidation below)

      Bar: open=97.0 (gap above trigger=95.0 → gap condition fires)
           low=89.5  (below invalidation=90.0 → invalidation condition fires)
           close=96.5

      Intrabar ordering: UNKNOWN — both conditions are satisfied by the OHLC bar
      but we cannot determine which occurred first.

    Policy: INVALIDATION WINS — state must be NO_SETUP, not TRIGGERED.
    """
    armed_eval = helper_make_armed_pullback(price=92.0, ob_prox=95.0, ob_dist=90.0)
    engine = EntryTriggerEngine()

    # Bar opens beyond trigger (gap), but low is also below invalidation — ambiguous intrabar ordering
    bar = {
        "open": 97.0,   # Gap: open > trigger=95.0 → gap fires
        "high": 97.5,
        "low": 89.5,    # Invalidation: low < invalidation=90.0 → invalidation fires
        "close": 96.5,  # Close above trigger — would have been a clean trigger without the low
        "timestamp": "2026-09-15T10:25:00Z",
    }
    res = engine.evaluate_trigger(armed_eval, bar, bar_idx=1, armed_bar_idx=0)

    # INVALIDATION WINS — must not be TRIGGERED despite gap open and close above trigger
    assert res.state == SignalState.NO_SETUP, (
        f"Expected NO_SETUP (INVALIDATION WINS) but got {res.state}. "
        "When gap and invalidation occur on same bar without intrabar ordering, invalidation must win."
    )
    assert res.evidence_ladder["reason"] == "SETUP_INVALIDATED"
    assert res.state != SignalState.TRIGGERED
