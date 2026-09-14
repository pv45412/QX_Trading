"""Pydantic models for Option Strategy Payoff & Risk/Reward Engine."""

from typing import List, Optional
from pydantic import BaseModel, Field


class OptionLeg(BaseModel):
    """Specific option leg in a multi-leg option strategy."""
    option_type: str = Field(..., description="'call' or 'put'")
    action: str = Field(..., description="'buy' or 'sell'")
    strike: float
    premium: float
    quantity: int = 1
    dte: int = 30


class PayoffCurvePoint(BaseModel):
    """A single data point along the P&L payoff curve."""
    underlying_price: float
    pnl_dollars: float
    pnl_pct: float


class StrategyPayoffResult(BaseModel):
    """Complete option strategy payoff, breakeven, and risk/reward report."""
    strategy_name: str
    underlying_price: float
    net_debit_credit: float  # Positive = net debit paid, Negative = net credit received
    max_risk_dollars: float
    max_profit_dollars: Optional[float]
    breakevens: List[float]
    risk_reward_ratio: Optional[float]
    curve: List[PayoffCurvePoint]
