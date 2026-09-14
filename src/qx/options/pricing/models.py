"""Pydantic data models for QX Options Pricing & Greeks Engine."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class OptionGreeks(BaseModel):
    """Sensitivity parameters (Greeks) for option contracts."""
    delta: float = Field(description="Sensitivity of option price to underlying price change ($1)")
    gamma: float = Field(description="Rate of change of delta per $1 move in underlying")
    theta: float = Field(description="Daily time decay of option price ($/day)")
    vega: float = Field(description="Sensitivity of option price to 1 percentage point change in IV")
    rho: float = Field(description="Sensitivity of option price to 1 percentage point change in interest rates")


class OptionPricingResult(BaseModel):
    """Complete option analytical valuation & sensitivity report."""
    underlying_price: float
    strike: float
    dte: int
    option_type: Literal["call", "put"]
    theoretical_price: float
    implied_volatility: float
    greeks: OptionGreeks
    iv_rank: Optional[float] = Field(default=None, description="52-week IV Rank (0-100)")
    iv_percentile: Optional[float] = Field(default=None, description="52-week IV Percentile (0-100)")


class OptionPricingRequest(BaseModel):
    """Request contract for pricing and Greeks evaluation."""
    underlying_price: float
    strike: float
    dte: int
    option_type: Literal["call", "put"]
    risk_free_rate: float = 0.045
    dividend_yield: float = 0.0
    iv: Optional[float] = Field(default=0.25, description="Annualized volatility decimal e.g. 0.25 for 25%")
    market_price: Optional[float] = Field(default=None, description="Market price to solve IV if provided")
    low_52w_iv: Optional[float] = Field(default=None, description="52-week minimum IV for IV Rank")
    high_52w_iv: Optional[float] = Field(default=None, description="52-week maximum IV for IV Rank")
