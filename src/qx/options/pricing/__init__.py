"""QX Options Pricing & Greeks Engine Package."""

from typing import Optional
from qx.options.pricing.black_scholes import (
    calculate_black_scholes_price,
    calculate_greeks,
)
from qx.options.pricing.iv_solver import calculate_implied_volatility
from qx.options.pricing.iv_rank import calculate_iv_rank, calculate_iv_percentile
from qx.options.pricing.models import (
    OptionGreeks,
    OptionPricingRequest,
    OptionPricingResult,
)


def evaluate_option_pricing(req: OptionPricingRequest) -> OptionPricingResult:
    """Unified entrypoint to evaluate option theoretical price, Greeks, and IV metrics.

    :param req: OptionPricingRequest payload
    :return: OptionPricingResult containing theoretical price, greeks, solved IV, and IV rank/percentile
    """
    iv = req.iv or 0.25

    # 1. If market_price is supplied, solve for IV first
    if req.market_price is not None and req.market_price > 0:
        iv = calculate_implied_volatility(
            market_price=req.market_price,
            spot=req.underlying_price,
            strike=req.strike,
            dte=req.dte,
            option_type=req.option_type,
            rate=req.risk_free_rate,
            dividend_yield=req.dividend_yield,
        )

    # 2. Calculate theoretical Black-Scholes price
    theo_price = calculate_black_scholes_price(
        spot=req.underlying_price,
        strike=req.strike,
        dte=req.dte,
        sigma=iv,
        option_type=req.option_type,
        rate=req.risk_free_rate,
        dividend_yield=req.dividend_yield,
    )

    # 3. Calculate analytical Greeks
    greeks = calculate_greeks(
        spot=req.underlying_price,
        strike=req.strike,
        dte=req.dte,
        sigma=iv,
        option_type=req.option_type,
        rate=req.risk_free_rate,
        dividend_yield=req.dividend_yield,
    )

    # 4. Calculate IV Rank if 52w bounds are available
    iv_rank_val: Optional[float] = None
    if req.low_52w_iv is not None and req.high_52w_iv is not None:
        iv_rank_val = calculate_iv_rank(iv, req.low_52w_iv, req.high_52w_iv)

    return OptionPricingResult(
        underlying_price=req.underlying_price,
        strike=req.strike,
        dte=req.dte,
        option_type=req.option_type,
        theoretical_price=round(theo_price, 2),
        implied_volatility=round(iv, 4),
        greeks=greeks,
        iv_rank=iv_rank_val,
        iv_percentile=None,
    )


__all__ = [
    "calculate_black_scholes_price",
    "calculate_greeks",
    "calculate_implied_volatility",
    "calculate_iv_rank",
    "calculate_iv_percentile",
    "evaluate_option_pricing",
    "OptionGreeks",
    "OptionPricingRequest",
    "OptionPricingResult",
]
