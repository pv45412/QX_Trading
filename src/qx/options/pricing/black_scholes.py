"""Black-Scholes analytical option pricing & Greeks model."""

import math
from typing import Literal, Tuple
from qx.options.pricing.models import OptionGreeks


def _n(x: float) -> float:
    """Standard normal probability density function (PDF)."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _N(x: float) -> float:
    """Cumulative distribution function (CDF) for standard normal distribution."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def calculate_d1_d2(
    spot: float,
    strike: float,
    dte: int,
    sigma: float,
    rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> Tuple[float, float, float]:
    """Calculate Black-Scholes d1, d2, and time in years T."""
    T = max(1e-5, dte / 365.0)
    sigma = max(1e-4, sigma)
    spot = max(1e-4, spot)
    strike = max(1e-4, strike)

    numerator = math.log(spot / strike) + (rate - dividend_yield + 0.5 * sigma * sigma) * T
    denominator = sigma * math.sqrt(T)

    d1 = numerator / denominator
    d2 = d1 - denominator
    return d1, d2, T


def calculate_black_scholes_price(
    spot: float,
    strike: float,
    dte: int,
    sigma: float,
    option_type: Literal["call", "put"],
    rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> float:
    """Calculate theoretical Black-Scholes option price.

    :param spot: Current underlying price ($)
    :param strike: Option strike price ($)
    :param dte: Days to expiration
    :param sigma: Annualized volatility decimal (e.g. 0.25)
    :param option_type: "call" or "put"
    :param rate: Risk-free rate decimal (e.g. 0.045)
    :param dividend_yield: Dividend yield decimal (e.g. 0.0)
    :return: Theoretical option price ($)
    """
    d1, d2, T = calculate_d1_d2(spot, strike, dte, sigma, rate, dividend_yield)
    q_disc = math.exp(-dividend_yield * T)
    r_disc = math.exp(-rate * T)

    if option_type == "call":
        price = spot * q_disc * _N(d1) - strike * r_disc * _N(d2)
    else:
        price = strike * r_disc * _N(-d2) - spot * q_disc * _N(-d1)

    return max(0.0, price)


def calculate_greeks(
    spot: float,
    strike: float,
    dte: int,
    sigma: float,
    option_type: Literal["call", "put"],
    rate: float = 0.045,
    dividend_yield: float = 0.0,
) -> OptionGreeks:
    """Calculate analytical option Greeks (Delta, Gamma, Theta, Vega, Rho)."""
    d1, d2, T = calculate_d1_d2(spot, strike, dte, sigma, rate, dividend_yield)
    q_disc = math.exp(-dividend_yield * T)
    r_disc = math.exp(-rate * T)
    pdf_d1 = _n(d1)

    # 1. Delta
    if option_type == "call":
        delta = q_disc * _N(d1)
    else:
        delta = -q_disc * _N(-d1)

    # 2. Gamma
    gamma = (q_disc * pdf_d1) / (spot * sigma * math.sqrt(T))

    # 3. Theta (Annualized -> converted to 1 day theta)
    term1 = -(spot * q_disc * pdf_d1 * sigma) / (2.0 * math.sqrt(T))
    if option_type == "call":
        theta_annual = (
            term1
            - rate * strike * r_disc * _N(d2)
            + dividend_yield * spot * q_disc * _N(d1)
        )
    else:
        theta_annual = (
            term1
            + rate * strike * r_disc * _N(-d2)
            - dividend_yield * spot * q_disc * _N(-d1)
        )
    theta_daily = theta_annual / 365.0

    # 4. Vega (per 1% IV change)
    vega = (spot * q_disc * math.sqrt(T) * pdf_d1) / 100.0

    # 5. Rho (per 1% interest rate change)
    if option_type == "call":
        rho = (strike * T * r_disc * _N(d2)) / 100.0
    else:
        rho = (-strike * T * r_disc * _N(-d2)) / 100.0

    return OptionGreeks(
        delta=round(delta, 4),
        gamma=round(gamma, 4),
        theta=round(theta_daily, 4),
        vega=round(vega, 4),
        rho=round(rho, 4),
    )
