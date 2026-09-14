"""Unit tests for Option Strategy Payoff & Risk/Reward Engine."""

import pytest
from qx.strategies.payoff import (
    OptionLeg,
    calculate_leg_payoff,
    generate_strategy_payoff,
)
from qx.strategies.payoff import generate_strategy_payoff as reexported_generator


def test_single_call_leg_payoff():
    """Verify single option leg P&L calculation at expiration."""
    long_call = OptionLeg(option_type="call", action="buy", strike=100.0, premium=3.00, quantity=1)
    short_call = OptionLeg(option_type="call", action="sell", strike=100.0, premium=3.00, quantity=1)

    # In the money (Spot = 110)
    assert calculate_leg_payoff(long_call, 110.0) == 700.0   # (10 - 3) * 100
    assert calculate_leg_payoff(short_call, 110.0) == -700.0

    # Out of the money (Spot = 95)
    assert calculate_leg_payoff(long_call, 95.0) == -300.0   # (0 - 3) * 100
    assert calculate_leg_payoff(short_call, 95.0) == 300.0


def test_bull_call_debit_spread_payoff():
    """Verify Bull Call Debit Spread P&L curve, breakeven, and risk/reward metrics."""
    legs = [
        OptionLeg(option_type="call", action="buy", strike=100.0, premium=4.00, quantity=1),
        OptionLeg(option_type="call", action="sell", strike=105.0, premium=1.50, quantity=1),
    ]

    result = generate_strategy_payoff(
        strategy_name="Bull Call Debit Spread",
        underlying_price=100.0,
        legs=legs,
        num_points=51,
        range_pct=0.20,
    )

    assert result.strategy_name == "Bull Call Debit Spread"
    assert result.net_debit_credit == 250.0  # $4.00 - $1.50 = $2.50 net debit * 100
    assert result.max_risk_dollars == 250.0
    assert result.max_profit_dollars == 250.0
    assert result.risk_reward_ratio == 1.0

    # Breakeven should be strike (100) + net debit (2.50) = 102.50
    assert len(result.breakevens) == 1
    assert abs(result.breakevens[0] - 102.50) < 0.20


def test_iron_condor_payoff():
    """Verify 4-leg Iron Condor payoff curve and 2 breakeven points."""
    legs = [
        OptionLeg(option_type="put", action="buy", strike=90.0, premium=1.00, quantity=1),
        OptionLeg(option_type="put", action="sell", strike=95.0, premium=2.50, quantity=1),
        OptionLeg(option_type="call", action="sell", strike=105.0, premium=2.50, quantity=1),
        OptionLeg(option_type="call", action="buy", strike=110.0, premium=1.00, quantity=1),
    ]

    result = generate_strategy_payoff(
        strategy_name="Iron Condor",
        underlying_price=100.0,
        legs=legs,
        num_points=51,
        range_pct=0.25,
    )

    assert result.net_debit_credit == -300.0  # Net credit of $3.00 * 100
    assert len(result.breakevens) == 2
    assert result.breakevens[0] < 100.0 < result.breakevens[1]


def test_backward_compatibility_payoff_reexport():
    """Verify re-exported generator function in qx.strategies.payoff."""
    legs = [OptionLeg(option_type="call", action="buy", strike=100.0, premium=2.00)]
    res = reexported_generator("Long Call", 100.0, legs)
    assert res.strategy_name == "Long Call"
    assert res.net_debit_credit == 200.0
