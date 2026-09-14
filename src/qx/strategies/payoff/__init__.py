"""QX Option Strategy Payoff & Risk/Reward Engine Package."""

from typing import List, Optional
from qx.strategies.payoff.curve_calculator import calculate_leg_payoff, generate_payoff_grid
from qx.strategies.payoff.metrics_calculator import calculate_breakevens, calculate_risk_reward
from qx.strategies.payoff.models import OptionLeg, PayoffCurvePoint, StrategyPayoffResult


def generate_strategy_payoff(
    strategy_name: str,
    underlying_price: float,
    legs: List[OptionLeg],
    num_points: int = 51,
    range_pct: float = 0.20,
) -> StrategyPayoffResult:
    """Generate multi-leg option strategy payoff curve across a price range."""
    if not legs or underlying_price <= 0:
        return StrategyPayoffResult(
            strategy_name=strategy_name,
            underlying_price=underlying_price,
            net_debit_credit=0.0,
            max_risk_dollars=0.0,
            max_profit_dollars=0.0,
            breakevens=[],
            risk_reward_ratio=0.0,
            curve=[],
        )

    # Net debit (+) or credit (-)
    net_debit_credit = 0.0
    for leg in legs:
        sign = 1 if leg.action.lower() in ("buy", "long") else -1
        net_debit_credit += leg.premium * sign * 100.0 * leg.quantity

    curve, prices, pnls = generate_payoff_grid(
        legs=legs,
        underlying_price=underlying_price,
        num_points=num_points,
        range_pct=range_pct,
        net_debit_credit=net_debit_credit,
    )

    breakevens = calculate_breakevens(prices, pnls)
    max_risk_dollars, max_profit_dollars, rr_ratio = calculate_risk_reward(pnls, legs=legs)

    return StrategyPayoffResult(
        strategy_name=strategy_name,
        underlying_price=underlying_price,
        net_debit_credit=round(net_debit_credit, 2),
        max_risk_dollars=max_risk_dollars,
        max_profit_dollars=max_profit_dollars,
        breakevens=breakevens,
        risk_reward_ratio=rr_ratio,
        curve=curve,
    )


__all__ = [
    "calculate_breakevens",
    "calculate_leg_payoff",
    "calculate_risk_reward",
    "generate_payoff_grid",
    "generate_strategy_payoff",
    "OptionLeg",
    "PayoffCurvePoint",
    "StrategyPayoffResult",
]
