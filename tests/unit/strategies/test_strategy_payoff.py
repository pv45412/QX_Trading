"""Unit tests for option strategy payoff engine."""

import pytest
from qx.strategies.payoff import OptionLeg, generate_strategy_payoff, calculate_leg_payoff


def test_calculate_single_call_leg_payoff():
    # Long 140 Call @ 5.00
    long_call = OptionLeg(option_type="call", action="buy", strike=140.0, premium=5.0, quantity=1)
    
    # At spot 135: Intrinsic 0, P&L = (0 - 5) * 1 * 100 = -500
    assert calculate_leg_payoff(long_call, 135.0) == -500.0
    
    # At spot 145: Intrinsic 5, P&L = (5 - 5) * 1 * 100 = 0
    assert calculate_leg_payoff(long_call, 145.0) == 0.0
    
    # At spot 150: Intrinsic 10, P&L = (10 - 5) * 1 * 100 = +500
    assert calculate_leg_payoff(long_call, 150.0) == 500.0


def test_bull_call_debit_spread_payoff():
    # Buy 145 Call @ 6.00, Sell 155 Call @ 2.00 -> Net Debit = $4.00 ($400)
    legs = [
        OptionLeg(option_type="call", action="buy", strike=145.0, premium=6.0, quantity=1),
        OptionLeg(option_type="call", action="sell", strike=155.0, premium=2.0, quantity=1),
    ]
    
    result = generate_strategy_payoff("Bull Call Spread", 148.53, legs)
    
    assert result.net_debit_credit == 400.0  # $400 debit
    assert result.max_risk_dollars == 400.0  # Max loss is debit paid
    assert result.max_profit_dollars == 600.0  # Max profit is (10 width - 4 debit) * 100 = 600
    assert len(result.breakevens) == 1
    assert result.breakevens[0] == 149.0  # Strike 145 + $4 debit
