"""Unit tests for QX Options Pricing & Greeks Engine."""

import math
import pytest
from qx.options.pricing import (
    calculate_black_scholes_price,
    calculate_greeks,
    calculate_implied_volatility,
    calculate_iv_rank,
    calculate_iv_percentile,
    evaluate_option_pricing,
    OptionPricingRequest,
)


def test_black_scholes_call_put_pricing():
    """Verify Black-Scholes call/put pricing and put-call parity."""
    spot = 100.0
    strike = 100.0
    dte = 30
    sigma = 0.25
    rate = 0.045

    call_price = calculate_black_scholes_price(spot, strike, dte, sigma, "call", rate=rate)
    put_price = calculate_black_scholes_price(spot, strike, dte, sigma, "put", rate=rate)

    assert call_price > 2.50
    assert put_price > 2.00

    # Put-Call Parity: C - P = S - K * exp(-r * T)
    T = dte / 365.0
    parity_diff = (call_price - put_price) - (spot - strike * math.exp(-rate * T))
    assert abs(parity_diff) < 1e-3


def test_greeks_math_and_bounds():
    """Verify analytical Greeks bounds and call/put symmetry."""
    spot = 150.0
    strike = 150.0
    dte = 45
    sigma = 0.30

    call_greeks = calculate_greeks(spot, strike, dte, sigma, "call")
    put_greeks = calculate_greeks(spot, strike, dte, sigma, "put")

    # Delta
    assert 0.45 <= call_greeks.delta <= 0.60
    assert -0.55 <= put_greeks.delta <= -0.40
    assert abs(call_greeks.delta - put_greeks.delta - 1.0) < 0.05

    # Gamma symmetry
    assert call_greeks.gamma > 0.0
    assert abs(call_greeks.gamma - put_greeks.gamma) < 1e-4

    # Theta decay
    assert call_greeks.theta < 0.0
    assert put_greeks.theta < 0.0

    # Vega
    assert call_greeks.vega > 0.0
    assert abs(call_greeks.vega - put_greeks.vega) < 1e-4


def test_implied_volatility_solver():
    """Verify Newton-Raphson / Bisection IV solver convergence."""
    spot = 200.0
    strike = 200.0
    dte = 30
    target_sigma = 0.35

    known_price = calculate_black_scholes_price(spot, strike, dte, target_sigma, "call")
    solved_iv = calculate_implied_volatility(known_price, spot, strike, dte, "call")

    assert abs(solved_iv - target_sigma) < 0.005


def test_iv_rank_and_percentile():
    """Verify 52-week IV Rank and Percentile calculation."""
    rank = calculate_iv_rank(current_iv=0.30, low_52w=0.20, high_52w=0.40)
    assert rank == 50.0

    percentile = calculate_iv_percentile(current_iv=0.30, iv_history=[0.10, 0.20, 0.25, 0.35, 0.40])
    assert percentile == 60.0


def test_evaluate_option_pricing_wrapper():
    """Verify unified evaluation wrapper returns complete pricing result."""
    req = OptionPricingRequest(
        underlying_price=100.0,
        strike=105.0,
        dte=30,
        option_type="call",
        iv=0.20,
        low_52w_iv=0.15,
        high_52w_iv=0.35,
    )
    result = evaluate_option_pricing(req)
    assert result.underlying_price == 100.0
    assert result.strike == 105.0
    assert result.theoretical_price > 0.0
    assert result.greeks.delta > 0.0
    assert result.iv_rank == 25.0
