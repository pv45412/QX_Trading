"""Pydantic models for QX Multi-Asset Portfolio Engine."""

from datetime import datetime, timezone
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field, model_validator

from qx.portfolio.sectors import (
    SECTOR_MAPPING_SOURCE,
    SECTOR_MAPPING_VERSION,
    normalize_sector,
)


class PortfolioPosition(BaseModel):
    symbol: str = Field(..., min_length=1)
    asset_class: Literal["STOCK", "OPTION"] = "STOCK"
    sector: Optional[str] = None
    provider_sector_raw: Optional[str] = None
    canonical_sector_id: Optional[str] = None
    sector_status: Literal["KNOWN", "UNKNOWN", "UNAVAILABLE"] = "UNAVAILABLE"
    sector_mapping_source: str = SECTOR_MAPPING_SOURCE
    sector_mapping_version: str = SECTOR_MAPPING_VERSION
    quantity: float = Field(..., description="Positive for Long, Negative for Short")
    entry_price: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    delta: float = 1.0  # 1.0 per share for stock, -1.0 to 1.0 per contract for options
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    greeks_status: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"] = "UNAVAILABLE"

    @model_validator(mode="after")
    def normalize_sector_provenance(self):
        raw = self.provider_sector_raw if self.provider_sector_raw is not None else self.sector
        mapping = normalize_sector(self.canonical_sector_id or raw)
        self.provider_sector_raw = str(raw).strip() if raw else mapping.provider_sector_raw
        self.canonical_sector_id = mapping.canonical_sector_id
        self.sector = self.provider_sector_raw
        self.sector_status = mapping.sector_status
        self.sector_mapping_source = mapping.sector_mapping_source
        self.sector_mapping_version = mapping.sector_mapping_version
        return self


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


from enum import Enum


class FreshnessState(str, Enum):
    FRESH = "FRESH"
    STALE_WARNED = "STALE_WARNED"
    STALE_BLOCKED = "STALE_BLOCKED"


class AccountSnapshot(BaseModel):
    account_id_hash: str
    account_equity: float = Field(..., gt=0, description="Total net liquidation equity")
    cash_balance: float = Field(..., ge=0)
    buying_power: float = Field(..., ge=0)
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PortfolioSnapshot(BaseModel):
    account: AccountSnapshot
    positions: list[PortfolioPosition] = Field(default_factory=list)
    open_orders_count: int = 0
    greeks: PortfolioGreeks = Field(default_factory=PortfolioGreeks)
    sector_allocations: list[SectorAllocation] = Field(default_factory=list)
    source: str = "schwab_read_only"
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    freshness_state: str = "FRESH"


class AccountRiskContext(BaseModel):
    account_id: str
    equity: float
    cash: float
    buying_power: float
    daily_realized_pnl: Optional[float] = 0.0
    daily_unrealized_pnl: Optional[float] = 0.0
    daily_realized_pnl_source: Optional[float] = None
    daily_unrealized_pnl_source: Optional[float] = None
    open_orders_count: Optional[int] = 0
    positions: list[PortfolioPosition] = Field(default_factory=list)
    greeks: PortfolioGreeks = Field(default_factory=PortfolioGreeks)
    sector_allocations: list[SectorAllocation] = Field(default_factory=list)
    sector_status: Literal["KNOWN", "UNKNOWN", "UNAVAILABLE"] = "KNOWN"
    sector_mapping_source: str = SECTOR_MAPPING_SOURCE
    sector_mapping_version: str = SECTOR_MAPPING_VERSION
    pnl_status: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"] = "UNAVAILABLE"
    greeks_status: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"] = "UNAVAILABLE"
    data_as_of: datetime
    retrieved_at: Optional[datetime] = None
    snapshot_id: Optional[int] = None
    freshness: FreshnessState = FreshnessState.FRESH
    broker_provenance: str
    publication_state: str = "RESEARCH_ONLY"
    read_only: bool = True
    sync_status: str = "SYNCED"

    @model_validator(mode="after")
    def mark_missing_risk_inputs_partial(self):
        if (
            self.daily_realized_pnl is None
            or self.daily_unrealized_pnl is None
            or self.open_orders_count is None
        ):
            self.sync_status = "PARTIAL"
        return self


class PortfolioRiskState(str, Enum):
    PORTFOLIO_APPROVED = "PORTFOLIO_APPROVED"
    PORTFOLIO_VETOED = "PORTFOLIO_VETOED"
    BLOCKED = "BLOCKED"


class PortfolioRiskResult(BaseModel):
    risk_result_id: str
    expression_id: str
    candidate_id: str
    symbol: str
    strategy_type: str
    direction: str
    
    state: PortfolioRiskState
    trade_state: str = "NONE - EXECUTION ELIGIBILITY NOT YET EVALUATED"
    
    account_id: str
    account_equity: float
    buying_power_available: float
    
    max_loss_per_contract: Optional[float] = None
    candidate_quantity: int = 1
    candidate_total_max_loss: Optional[float] = None
    candidate_buying_power_required: Optional[float] = None
    
    max_allowed_risk_dollars: float = 0.0
    max_allowed_risk_pct: float = 0.0
    
    recommended_max_contracts: int = 0
    approved_contracts_cap: int = 0
    
    max_contracts_by_risk: Optional[int] = None
    max_contracts_by_daily_loss: Optional[int] = None
    max_contracts_by_buying_power: Optional[int] = None
    max_contracts_by_symbol: Optional[int] = None
    max_contracts_by_sector: Optional[int] = None
    max_contracts_by_delta: Optional[int] = None
    max_contracts_by_gamma: Optional[int] = None
    max_contracts_by_vega: Optional[int] = None
    max_contracts_by_theta: Optional[int] = None
    max_contracts_by_correlation: Optional[int] = None
    
    binding_constraint: Optional[str] = None
    exposure_basis: str = "MAX_LOSS"
    
    portfolio_delta_before: float = 0.0
    portfolio_delta_after: Optional[float] = None
    
    portfolio_gamma_before: float = 0.0
    portfolio_gamma_after: Optional[float] = None
    
    portfolio_theta_before: float = 0.0
    portfolio_theta_after: Optional[float] = None
    
    portfolio_vega_before: float = 0.0
    portfolio_vega_after: Optional[float] = None
    
    symbol_exposure_before: float = 0.0
    symbol_exposure_after: float = 0.0
    
    sector_exposure_before: float = 0.0
    sector_exposure_after: float = 0.0
    
    concentration_before: float = 0.0
    concentration_after: float = 0.0
    
    daily_loss_used: float = 0.0
    daily_loss_remaining: float = 0.0
    
    correlation_risk: bool = False
    existing_related_positions: list[str] = Field(default_factory=list)
    
    reason_codes: list[str] = Field(default_factory=list)
    evidence_ladder: dict[str, Any] = Field(default_factory=dict)
    
    evaluated_at: str
    data_as_of: str
    config_version: str
    engine_version: str

