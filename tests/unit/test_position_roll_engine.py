"""Unit tests for QX Position Adjustment & Roll Engine."""

import pytest
from qx.positions.roll.engine import evaluate_position_roll
from qx.positions.roll.models import PositionRollRequest


def test_credit_roll_out_short_put():
    """Verify net credit roll recommendation for short put with low DTE."""
    req = PositionRollRequest(
        symbol="AAPL",
        underlying_price=220.0,
        position_type="short_put",
        current_strike=220.0,
        current_dte=5,
        current_premium=4.00,
        trend_score=50.0,
        structure_score=50.0,
    )
    plan = evaluate_position_roll(req)
    assert plan.symbol == "AAPL"
    assert plan.recommendation.roll_type == "CREDIT_ROLL_OUT"
    assert plan.recommendation.target_dte == 30
    assert plan.recommendation.net_credit_debit > 0
    assert len(plan.recommendation.recommended_legs) == 2
    assert plan.recommendation.recommended_legs[0].action == "BUY_TO_CLOSE"
    assert plan.recommendation.recommended_legs[1].action == "SELL_TO_OPEN"


def test_leg_into_spread_long_call():
    """Verify spread conversion recommendation for long call requiring risk adjustment."""
    req = PositionRollRequest(
        symbol="NVDA",
        underlying_price=120.0,
        position_type="long_call",
        current_strike=115.0,
        current_dte=25,
        current_premium=8.00,
        reward_remaining_pct=30.0,  # Below 40 threshold
    )
    plan = evaluate_position_roll(req)
    assert plan.symbol == "NVDA"
    assert plan.recommendation.roll_type == "LEG_INTO_SPREAD"
    assert len(plan.recommendation.recommended_legs) == 1
    assert plan.recommendation.recommended_legs[0].action == "SELL_TO_OPEN"
    assert plan.recommendation.recommended_legs[0].strike > 120.0


def test_protective_collar_long_stock():
    """Verify protective collar recommendation for long stock with deteriorating health."""
    req = PositionRollRequest(
        symbol="TSLA",
        underlying_price=200.0,
        position_type="long_stock",
        current_dte=30,
        trend_score=30.0,
        structure_score=30.0,
        invalidation_distance_pct=2.0,
    )
    plan = evaluate_position_roll(req)
    assert plan.symbol == "TSLA"
    assert plan.recommendation.roll_type == "PROTECTIVE_COLLAR"
    assert len(plan.recommendation.recommended_legs) == 2
    actions = [leg.action for leg in plan.recommendation.recommended_legs]
    assert "BUY_TO_OPEN" in actions
    assert "SELL_TO_OPEN" in actions


def test_close_position_on_stop_breached():
    """Verify hard close position recommendation when stop loss is breached."""
    req = PositionRollRequest(
        symbol="AMD",
        underlying_price=140.0,
        position_type="long_call",
        current_strike=150.0,
        current_dte=20,
        stop_breached=True,
    )
    plan = evaluate_position_roll(req)
    assert plan.symbol == "AMD"
    assert plan.recommendation.roll_type == "CLOSE_POSITION"
    assert plan.recommendation.recommended_legs[0].action == "SELL_TO_CLOSE"


def test_hold_no_action_for_strong_position():
    """Verify no adjustment needed when position health is optimal."""
    req = PositionRollRequest(
        symbol="MSFT",
        underlying_price=450.0,
        position_type="long_stock",
        current_dte=45,
        trend_score=85.0,
        structure_score=85.0,
        invalidation_distance_pct=8.0,
        reward_remaining_pct=80.0,
    )
    plan = evaluate_position_roll(req)
    assert plan.symbol == "MSFT"
    assert plan.recommendation.roll_type == "HOLD_NO_ACTION"
    assert len(plan.recommendation.recommended_legs) == 0
