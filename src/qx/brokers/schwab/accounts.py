"""Read-only Schwab account snapshot adapter for canonical portfolio risk."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

from qx.brokers.schwab.client import SchwabApiClient
from qx.pipeline.snapshot_store import internal_account_id
from qx.portfolio.greeks_risk import calculate_portfolio_greeks
from qx.portfolio.models import (
    AccountRiskContext,
    FreshnessState,
    PortfolioPosition,
    SectorAllocation,
)
from qx.portfolio.sectors import normalize_sector, normalize_sector_by_ticker


_OPTION_SECTOR_ID: str | None = None  # options don't have canonical sectors


class SchwabReadOnlyAccountSnapshotProvider:
    provider_name = "schwab_read_only"

    def __init__(self, client: SchwabApiClient, *, metadata_store: Any | None = None) -> None:
        self.client = client
        self._metadata_store = metadata_store

    def get_account_risk_snapshot(self) -> AccountRiskContext | None:
        payload = self.client.get("/trader/v1/accounts", params={"fields": "positions"})
        accounts = payload.get("data", payload)
        if isinstance(accounts, dict):
            accounts = [accounts]
        if not isinstance(accounts, list) or len(accounts) != 1:
            return None

        raw_account = accounts[0]
        if not isinstance(raw_account, dict):
            return None
        securities = raw_account.get("securitiesAccount", raw_account)
        if not isinstance(securities, dict):
            return None
        balances = securities.get("currentBalances", {})
        if not isinstance(balances, dict):
            return None

        equity = _number(
            balances.get("liquidationValue", balances.get("equity", 0.0))
        )
        if equity <= 0:
            return None
        cash = max(0.0, _number(balances.get("cashBalance", 0.0)))
        buying_power = max(
            0.0,
            _number(
                balances.get(
                    "buyingPower",
                    balances.get("availableFunds", balances.get("cashAvailableForTrading", 0.0)),
                )
            ),
        )

        positions, complete_positions = _positions(
            securities.get("positions", []),
            metadata_store=self._metadata_store,
        )
        greeks = calculate_portfolio_greeks(positions)
        daily_realized = _optional_number(balances.get("dailyRealizedProfitLoss"))
        daily_unrealized = _optional_number(balances.get("dailyUnrealizedProfitLoss"))
        raw_open_orders = securities.get("openOrders")
        open_orders_count = len(raw_open_orders) if isinstance(raw_open_orders, list) else None
        account_key = str(
            raw_account.get("hashValue")
            or securities.get("accountId")
            or securities.get("accountNumber")
            or "schwab-read-only-account"
        )
        account_hash = raw_account.get("hashValue")
        if open_orders_count is None and isinstance(account_hash, str) and account_hash:
            open_orders_count = self._open_orders_count(
                account_hash, datetime.now(timezone.utc)
            )
        retrieved_at = datetime.now(timezone.utc)
        sector_status = _account_sector_status(positions, complete_positions)
        complete_account_risk = (
            complete_positions
            and sector_status == "KNOWN"
            and daily_realized is not None
            and daily_unrealized is not None
            and open_orders_count is not None
        )
        sync_status = "SYNCED" if complete_account_risk else "PARTIAL"
        pnl_status = (
            "AVAILABLE"
            if daily_realized is not None and daily_unrealized is not None
            else "PARTIAL"
            if daily_realized is not None or daily_unrealized is not None
            else "UNAVAILABLE"
        )
        greeks_status = (
            "AVAILABLE"
            if positions and all(position.greeks_status == "AVAILABLE" for position in positions)
            else "PARTIAL"
            if any(position.greeks_status == "AVAILABLE" for position in positions)
            else "UNAVAILABLE"
        )
        return AccountRiskContext(
            account_id=internal_account_id(account_key),
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            daily_realized_pnl=daily_realized,
            daily_unrealized_pnl=daily_unrealized,
            daily_realized_pnl_source=daily_realized,
            daily_unrealized_pnl_source=daily_unrealized,
            open_orders_count=open_orders_count,
            positions=positions,
            greeks=greeks,
            sector_allocations=_sector_allocations(positions, equity),
            sector_status=sector_status,
            pnl_status=pnl_status,
            greeks_status=greeks_status,
            data_as_of=retrieved_at,
            retrieved_at=retrieved_at,
            freshness=FreshnessState.FRESH,
            broker_provenance=self.provider_name,
            publication_state="RESEARCH_ONLY",
            read_only=True,
            sync_status=sync_status,
        )

    def _open_orders_count(self, account_hash: str, now: datetime) -> int | None:
        try:
            payload = self.client.get(
                f"/trader/v1/accounts/{account_hash}/orders",
                params={
                    "fromEnteredTime": (now - timedelta(days=60)).isoformat(),
                    "toEnteredTime": now.isoformat(),
                },
            )
        except Exception:
            return None
        orders = payload.get("data", payload)
        if not isinstance(orders, list):
            return None
        closed = {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "REPLACED"}
        return sum(
            1
            for order in orders
            if isinstance(order, dict) and str(order.get("status", "")).upper() not in closed
        )


def _positions(
    raw_positions: object,
    *,
    metadata_store: Any | None = None,
) -> tuple[list[PortfolioPosition], bool]:
    if not isinstance(raw_positions, list):
        return [], False
    positions: list[PortfolioPosition] = []
    complete = True
    for raw in raw_positions:
        if not isinstance(raw, dict):
            complete = False
            continue
        instrument = raw.get("instrument", {})
        if not isinstance(instrument, dict):
            complete = False
            continue
        symbol = str(instrument.get("symbol", "")).strip().upper()
        asset_type = str(instrument.get("assetType", "EQUITY")).upper()
        asset_class = "OPTION" if "OPTION" in asset_type else "STOCK"
        quantity = _number(raw.get("longQuantity", 0.0)) - _number(
            raw.get("shortQuantity", 0.0)
        )
        average_price = _number(raw.get("averagePrice", 0.0))
        market_value = _number(raw.get("marketValue", 0.0))
        multiplier = 100.0 if asset_class == "OPTION" else 1.0
        current_price = abs(market_value) / (abs(quantity) * multiplier) if quantity else 0.0
        if not symbol or quantity == 0 or average_price <= 0 or current_price <= 0:
            complete = False
            continue
        if asset_class == "OPTION":
            complete = False

        # Resolve sector: prefer Schwab instrument field, fall back to metadata store
        broker_sector_raw = instrument.get("sector", raw.get("sector"))
        sector_mapping = normalize_sector(broker_sector_raw)
        if sector_mapping.sector_status != "KNOWN" and metadata_store is not None:
            # For options, extract the underlying ticker from Schwab's underlyingSymbol
            # or parse from the OCC-format option symbol (e.g. 'FTNT  261016P00150000' → 'FTNT')
            underlying_raw = instrument.get("underlyingSymbol") or ""
            if not underlying_raw and asset_class == "OPTION":
                # Parse underlying from OCC option symbol: leading alpha chars are the ticker
                match = re.match(r"^([A-Z]+)", symbol.replace(" ", ""))
                underlying_raw = match.group(1) if match else symbol
            underlying = str(underlying_raw or symbol).strip().upper()
            meta = metadata_store.get(underlying)
            if meta is not None and meta.sector not in ("", "Unknown", "ETF"):
                sector_mapping = normalize_sector(meta.sector)

        # Final fallback: check the leveraged/inverse ETF ticker map by symbol
        if sector_mapping.sector_status != "KNOWN":
            etf_mapping = normalize_sector_by_ticker(symbol)
            if etf_mapping is not None:
                sector_mapping = etf_mapping


        unrealized_pnl = _position_unrealized_pnl(raw, quantity)
        cost_basis = abs(quantity) * average_price * multiplier
        positions.append(
            PortfolioPosition(
                symbol=symbol,
                asset_class=asset_class,
                provider_sector_raw=sector_mapping.provider_sector_raw,
                canonical_sector_id=sector_mapping.canonical_sector_id,
                sector_status=sector_mapping.sector_status,
                sector_mapping_source=sector_mapping.sector_mapping_source,
                sector_mapping_version=sector_mapping.sector_mapping_version,
                quantity=quantity,
                entry_price=average_price,
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=(
                    (unrealized_pnl / cost_basis) * 100.0
                    if unrealized_pnl is not None and cost_basis > 0
                    else None
                ),
                delta=1.0 if asset_class == "STOCK" else 0.0,
                greeks_status="AVAILABLE" if asset_class == "STOCK" else "UNAVAILABLE",
            )
        )
    return positions, complete


def _account_sector_status(
    positions: list[PortfolioPosition], positions_complete: bool
) -> str:
    if not positions_complete:
        return "UNAVAILABLE"
    if any(position.sector_status != "KNOWN" for position in positions):
        return "UNKNOWN"
    return "KNOWN"


def _sector_allocations(
    positions: list[PortfolioPosition],
    equity: float,
) -> list[SectorAllocation]:
    totals: dict[str, float] = {}
    for position in positions:
        if position.sector_status != "KNOWN" or position.canonical_sector_id is None:
            continue
        multiplier = 100.0 if position.asset_class == "OPTION" else 1.0
        value = abs(position.quantity) * position.current_price * multiplier
        canonical_sector_id = position.canonical_sector_id
        totals[canonical_sector_id] = totals.get(canonical_sector_id, 0.0) + value
    return [
        SectorAllocation(
            sector=sector,
            allocation_pct=(value / equity) * 100.0,
            market_value=value,
            is_overconcentrated=(value / equity) * 100.0 > 25.0,
        )
        for sector, value in totals.items()
    ]


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _position_unrealized_pnl(raw: dict[str, Any], quantity: float) -> float | None:
    preferred = "longOpenProfitLoss" if quantity > 0 else "shortOpenProfitLoss"
    value = _optional_number(raw.get(preferred))
    if value is not None:
        return value
    return _optional_number(raw.get("openProfitLoss"))
