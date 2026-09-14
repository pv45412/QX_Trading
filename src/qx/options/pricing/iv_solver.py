"""Numerical Implied Volatility (IV) Solver."""

from typing import Literal
from qx.options.pricing.black_scholes import calculate_black_scholes_price, calculate_greeks


def calculate_implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    dte: int,
    option_type: Literal["call", "put"],
    rate: float = 0.045,
    dividend_yield: float = 0.0,
    tol: float = 1e-4,
    max_iter: int = 100,
) -> float:
    """Solve for implied volatility using Newton-Raphson with Bisection fallback.

    :param market_price: Observed market price of option ($)
    :param spot: Underlying spot price ($)
    :param strike: Option strike price ($)
    :param dte: Days to expiration
    :param option_type: "call" or "put"
    :param rate: Risk-free rate
    :param dividend_yield: Dividend yield
    :param tol: Target price convergence tolerance
    :param max_iter: Maximum iterations
    :return: Annualized implied volatility decimal (e.g. 0.25 for 25%)
    """
    intrinsic = max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
    if market_price <= intrinsic + 1e-4:
        return 0.0001

    # 1. Newton-Raphson solver
    sigma = 0.25
    for _ in range(max_iter):
        price = calculate_black_scholes_price(spot, strike, dte, sigma, option_type, rate, dividend_yield)
        diff = price - market_price

        if abs(diff) < tol:
            return round(sigma, 4)

        greeks = calculate_greeks(spot, strike, dte, sigma, option_type, rate, dividend_yield)
        vega_raw = greeks.vega * 100.0  # Convert back to raw vega per 1.0 (100%) IV change

        if vega_raw < 1e-6:
            break

        sigma_next = sigma - diff / vega_raw
        if sigma_next <= 0.001 or sigma_next > 5.0:
            break

        sigma = sigma_next

    # 2. Bisection fallback solver
    low = 0.0001
    high = 5.0
    for _ in range(60):
        mid = (low + high) / 2.0
        price = calculate_black_scholes_price(spot, strike, dte, mid, option_type, rate, dividend_yield)
        diff = price - market_price

        if abs(diff) < tol:
            return round(mid, 4)

        if diff > 0:
            high = mid
        else:
            low = mid

    return round((low + high) / 2.0, 4)
