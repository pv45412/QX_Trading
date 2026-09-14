"""Backward compatibility layer re-exporting Option Strategy Payoff & Risk/Reward Engine.

Canonical domain package: qx.strategies.payoff
"""

from qx.strategies.payoff import (
    OptionLeg,
    PayoffCurvePoint,
    StrategyPayoffResult,
    calculate_breakevens,
    calculate_leg_payoff,
    calculate_risk_reward,
    generate_payoff_grid,
    generate_strategy_payoff,
)

__all__ = [
    "OptionLeg",
    "PayoffCurvePoint",
    "StrategyPayoffResult",
    "calculate_breakevens",
    "calculate_leg_payoff",
    "calculate_risk_reward",
    "generate_payoff_grid",
    "generate_strategy_payoff",
]
