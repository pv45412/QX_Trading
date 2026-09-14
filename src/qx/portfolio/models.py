"""Pydantic models for QX Multi-Asset Portfolio Engine."""

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


class PortfolioPosition(BaseModel):
    symbol: str = Field(..., min_length=1)
    asset_class: Literal["STOCK", "OPTION"] = "STOCK"
    sector: str = "Unassigned"
    quantity: float = Field(..., description="Positive for Long, Negative for Short")
    entry_price: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)
    delta: float = 1.0  # 1.0 per share for stock, -1.0 to 1.0 per contract for options
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0


class PortfolioGreeks(BaseModel):
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    beta_weighted_delta: float = 0.0


class SectorAllocation(BaseModel):
    sector: str
    allocation_pct: float
    market_value: float
    is_overconcentrated: bool = False


class PortfolioSummary(BaseModel):
    total_market_value: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    greeks: PortfolioGreeks
    sector_allocations: list[SectorAllocation] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
