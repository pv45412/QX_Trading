"""Leg Payoff and Price Grid Curve calculation engine."""

from typing import List, Tuple
from qx.strategies.payoff.models import OptionLeg, PayoffCurvePoint


def calculate_leg_payoff(leg: OptionLeg, spot_price: float) -> float:
    """Calculate at-expiration P&L in dollars for a single option leg at spot_price."""
    sign = 1 if leg.action.lower() in ("buy", "long") else -1

    if leg.option_type.lower() == "call":
        intrinsic = max(0.0, spot_price - leg.strike)
    else:  # put
        intrinsic = max(0.0, leg.strike - spot_price)

    # P&L per contract = (Intrinsic value - Initial premium paid/received) * sign * 100 * quantity
    pnl = (intrinsic - leg.premium) * sign * 100.0 * leg.quantity
    return pnl


def generate_payoff_grid(
    legs: List[OptionLeg],
    underlying_price: float,
    num_points: int = 51,
    range_pct: float = 0.20,
    net_debit_credit: float = 0.0,
) -> Tuple[List[PayoffCurvePoint], List[float], List[float]]:
    """Generate P&L curve grid points, raw price array, and raw P&L dollar array across price range.

    :return: Tuple of (PayoffCurvePoint list, raw prices list, raw pnls list)
    """
    min_price = max(0.5, underlying_price * (1.0 - range_pct))
    max_price = underlying_price * (1.0 + range_pct)
    step = (max_price - min_price) / (num_points - 1)

    curve: List[PayoffCurvePoint] = []
    pnls: List[float] = []
    prices: List[float] = []

    cost_basis = abs(net_debit_credit) if net_debit_credit != 0 else 100.0

    for i in range(num_points):
        price = round(min_price + i * step, 2)
        prices.append(price)

        total_pnl = sum(calculate_leg_payoff(leg, price) for leg in legs)
        pnls.append(total_pnl)

        pnl_pct = round((total_pnl / cost_basis) * 100.0, 2)

        curve.append(
            PayoffCurvePoint(
                underlying_price=price,
                pnl_dollars=round(total_pnl, 2),
                pnl_pct=pnl_pct,
            )
        )

    return curve, prices, pnls
