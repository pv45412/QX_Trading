"""Privacy-safe read-only projection for the canonical Portfolio workspace."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from qx.pipeline.models import DataDependencyStatus, PIPELINE_VERSION
from qx.portfolio.models import AccountRiskContext, PortfolioGreeks, SectorAllocation


class PortfolioWorkspacePosition(BaseModel):
    symbol: str
    asset_class: str
    quantity: float
    entry_price: float
    current_price: float
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    concentration_pct: float | None = None
    canonical_sector_id: str | None = None
    provider_sector_raw: str | None = None
    sector_status: str
    sector_mapping_source: str
    sector_mapping_version: str
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    greeks_status: str


class PortfolioWorkspaceResponse(BaseModel):
    request_started_at: datetime
    evaluation_timestamp: datetime
    pipeline_version: str = PIPELINE_VERSION
    publication_state: str = "BLOCKED"
    status: Literal["COMPLETE", "PARTIAL", "STALE", "UNAVAILABLE"] = "UNAVAILABLE"
    read_only: bool = True
    account_id: str | None = None
    equity: float | None = None
    cash: float | None = None
    buying_power: float | None = None
    daily_realized_pnl: float | None = None
    daily_unrealized_pnl: float | None = None
    total_unrealized_pnl: float | None = None
    pnl_status: str = "UNAVAILABLE"
    open_orders_count: int | None = None
    gross_market_exposure: float | None = None
    net_market_exposure: float | None = None
    positions: list[PortfolioWorkspacePosition] = Field(default_factory=list)
    greeks: PortfolioGreeks | None = None
    greeks_status: str = "UNAVAILABLE"
    sector_allocations: list[SectorAllocation] = Field(default_factory=list)
    sector_status: str = "UNAVAILABLE"
    sector_mapping_source: str | None = None
    sector_mapping_version: str | None = None
    data_as_of: datetime | None = None
    retrieved_at: datetime | None = None
    snapshot_id: int | None = None
    freshness: str = "UNAVAILABLE"
    sync_status: str = "UNAVAILABLE"
    source: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    dependency: DataDependencyStatus
    provider_latency_ms: float | None = None


def build_portfolio_workspace_response(
    account: AccountRiskContext | None,
    *,
    request_started_at: datetime,
    evaluation_timestamp: datetime,
    dependency: DataDependencyStatus,
    provider_latency_ms: float | None,
) -> PortfolioWorkspaceResponse:
    if account is None:
        return PortfolioWorkspaceResponse(
            request_started_at=request_started_at,
            evaluation_timestamp=evaluation_timestamp,
            reason_codes=[dependency.reason_code or "ACCOUNT_SNAPSHOT_UNAVAILABLE"],
            dependency=dependency,
            provider_latency_ms=provider_latency_ms,
        )

    positions = []
    gross_exposure = 0.0
    net_exposure = 0.0
    supplied_pnl = []
    all_pnl_supplied = True
    for position in account.positions:
        multiplier = 100.0 if position.asset_class == "OPTION" else 1.0
        signed_value = position.quantity * position.current_price * multiplier
        market_value = position.market_value
        if market_value is None:
            market_value = signed_value
        gross_exposure += abs(market_value)
        net_exposure += market_value
        if position.unrealized_pnl is None:
            all_pnl_supplied = False
        else:
            supplied_pnl.append(position.unrealized_pnl)
        concentration = (
            round((abs(market_value) / account.equity) * 100.0, 4)
            if account.equity > 0
            else None
        )
        positions.append(
            PortfolioWorkspacePosition(
                symbol=position.symbol,
                asset_class=position.asset_class,
                quantity=position.quantity,
                entry_price=position.entry_price,
                current_price=position.current_price,
                market_value=market_value,
                unrealized_pnl=position.unrealized_pnl,
                unrealized_pnl_pct=position.unrealized_pnl_pct,
                concentration_pct=concentration,
                canonical_sector_id=position.canonical_sector_id,
                provider_sector_raw=position.provider_sector_raw,
                sector_status=position.sector_status,
                sector_mapping_source=position.sector_mapping_source,
                sector_mapping_version=position.sector_mapping_version,
                delta=position.delta if position.greeks_status == "AVAILABLE" else None,
                gamma=position.gamma if position.greeks_status == "AVAILABLE" else None,
                theta=position.theta if position.greeks_status == "AVAILABLE" else None,
                vega=position.vega if position.greeks_status == "AVAILABLE" else None,
                greeks_status=position.greeks_status,
            )
        )

    reasons = []
    freshness = account.freshness.value
    if freshness != "FRESH":
        reasons.append("ACCOUNT_DATA_STALE")
    if account.sync_status != "SYNCED":
        reasons.append("PARTIAL_ACCOUNT_EVIDENCE")
    if account.sector_status != "KNOWN":
        reasons.append("SECTOR_PROVENANCE_INCOMPLETE")
    if account.greeks_status != "AVAILABLE":
        reasons.append("GREEKS_UNAVAILABLE")
    if account.pnl_status != "AVAILABLE":
        reasons.append("PNL_EVIDENCE_INCOMPLETE")

    status: Literal["COMPLETE", "PARTIAL", "STALE", "UNAVAILABLE"]
    if freshness != "FRESH":
        status = "STALE"
    elif reasons:
        status = "PARTIAL"
    else:
        status = "COMPLETE"

    return PortfolioWorkspaceResponse(
        request_started_at=request_started_at,
        evaluation_timestamp=evaluation_timestamp,
        publication_state=account.publication_state,
        status=status,
        account_id=account.account_id,
        equity=account.equity,
        cash=account.cash,
        buying_power=account.buying_power,
        daily_realized_pnl=account.daily_realized_pnl_source,
        daily_unrealized_pnl=account.daily_unrealized_pnl_source,
        total_unrealized_pnl=(sum(supplied_pnl) if all_pnl_supplied else None),
        pnl_status=account.pnl_status,
        open_orders_count=account.open_orders_count,
        gross_market_exposure=gross_exposure,
        net_market_exposure=net_exposure,
        positions=positions,
        greeks=(account.greeks if account.greeks_status in {"AVAILABLE", "PARTIAL"} else None),
        greeks_status=account.greeks_status,
        sector_allocations=account.sector_allocations,
        sector_status=account.sector_status,
        sector_mapping_source=account.sector_mapping_source,
        sector_mapping_version=account.sector_mapping_version,
        data_as_of=account.data_as_of,
        retrieved_at=account.retrieved_at,
        snapshot_id=account.snapshot_id,
        freshness=freshness,
        sync_status=account.sync_status,
        source=account.broker_provenance,
        reason_codes=reasons,
        dependency=dependency,
        provider_latency_ms=provider_latency_ms,
    )
