"""Unit tests for Strategy Modules."""

import pytest
from qx.strategies.base import StrategyContext
from qx.strategies.debit_spreads.bull_call_spread import BullCallSpreadModule
from qx.strategies.calendars.spx_calendar import SPXCalendarModule


def test_bull_call_spread_compatibility():
    mod = BullCallSpreadModule()
    ctx = StrategyContext(
        symbol="AAPL",
        underlying_price=150.0,
        direction_score=80.0,
        iv_rank=20.0,
    )
    score = mod.evaluate_compatibility(ctx)
    assert score >= 60.0

    trade = mod.construct_trade(ctx, {})
    assert trade is not None
    assert trade.strategy_name == "Bull Call Debit Spread"
    assert trade.symbol == "AAPL"
    assert trade.max_risk_dollars > 0


def test_spx_calendar_compatibility():
    mod = SPXCalendarModule()
    ctx = StrategyContext(
        symbol="SPX",
        underlying_price=5000.0,
        direction_score=50.0,  # Neutral direction
        iv_rank=25.0,  # Low IV
    )
    score = mod.evaluate_compatibility(ctx)
    assert score >= 70.0

    trade = mod.construct_trade(ctx, {})
    assert trade is not None
    assert trade.strategy_name == "SPX Calendar Spread"
    assert trade.symbol == "SPX"
