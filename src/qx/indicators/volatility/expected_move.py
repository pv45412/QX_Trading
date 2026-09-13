"""Canonical Expected Move calculation based on Implied Volatility and DTE."""

import math


def calculate_expected_move(
    price: float,
    implied_volatility: float,
    dte: int,
) -> dict[str, float]:
    """Calculate the expected 1-standard-deviation move for an underlying given IV and DTE.

    Formula: Expected Move = Price * (IV / 100) * sqrt(DTE / 365)

    :param price: Current underlying price
    :param implied_volatility: IV as percentage (e.g. 25.5 for 25.5%) or decimal (0.255)
    :param dte: Days to expiration
    :return: dict with expected_move_dollars, upper_bound, lower_bound, move_percent
    """
    if dte <= 0 or price <= 0:
        return {
            "expected_move_dollars": 0.0,
            "upper_bound": price,
            "lower_bound": price,
            "move_percent": 0.0,
        }

    iv_decimal = implied_volatility if implied_volatility <= 3.0 else implied_volatility / 100.0
    move_dollars = price * iv_decimal * math.sqrt(dte / 365.0)
    move_pct = (move_dollars / price) * 100.0

    return {
        "expected_move_dollars": round(move_dollars, 2),
        "upper_bound": round(price + move_dollars, 2),
        "lower_bound": round(price - move_dollars, 2),
        "move_percent": round(move_pct, 2),
    }
