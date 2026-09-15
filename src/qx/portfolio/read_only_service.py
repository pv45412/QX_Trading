"""Strictly Read-Only Portfolio Service & Cache Layer for QX Platform.

MANDATORY SECURITY BOUNDARY:
This module provides READ-ONLY account equity, positions, and Greek exposures.
It contains ZERO methods for submitting, modifying, canceling, or routing orders.
"""

from datetime import datetime, timezone
import hashlib
import threading
from typing import Any, Dict, List, Optional, Protocol

from qx.portfolio.greeks_risk import calculate_portfolio_greeks
from qx.portfolio.models import AccountSnapshot, PortfolioGreeks, PortfolioPosition, PortfolioSnapshot, SectorAllocation


class ReadOnlyBrokerPortfolioProvider(Protocol):
    """Protocol declaring read-only brokerage account operations.

    MANDATORY BOUNDARY: This interface must expose NO order placement, order modification,
    order cancellation, or funds transfer methods.
    """

    def get_account_snapshot(self) -> Optional[AccountSnapshot]:
        """Fetch read-only account equity, cash balance, and buying power."""
        ...

    def get_positions(self) -> list[PortfolioPosition]:
        """Fetch current portfolio holdings."""
        ...

    def get_open_orders(self) -> list[dict[str, Any]]:
        """Fetch current open broker orders if read access supports it."""
        ...


class PortfolioCache:
    """Thread-safe in-memory cache for PortfolioSnapshot with configurable TTL."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self.ttl_seconds = max(15.0, min(60.0, ttl_seconds))
        self._cached_snapshot: Optional[PortfolioSnapshot] = None
        self._last_fetched_at: Optional[datetime] = None
        self._lock = threading.Lock()

    def get(self, now: Optional[datetime] = None) -> Optional[PortfolioSnapshot]:
        with self._lock:
            if self._cached_snapshot is None or self._last_fetched_at is None:
                return None
            now_dt = now or datetime.now(timezone.utc)
            ts = self._last_fetched_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            age = (now_dt - ts).total_seconds()
            if age > self.ttl_seconds * 2:
                # Stale blocked
                updated_dict = self._cached_snapshot.model_dump()
                updated_dict["freshness_state"] = "STALE_BLOCKED"
                return PortfolioSnapshot(**updated_dict)
            elif age > self.ttl_seconds:
                # Stale warned
                updated_dict = self._cached_snapshot.model_dump()
                updated_dict["freshness_state"] = "STALE_WARNED"
                return PortfolioSnapshot(**updated_dict)

            return self._cached_snapshot

    def set(self, snapshot: PortfolioSnapshot, now: Optional[datetime] = None) -> None:
        with self._lock:
            now_dt = now or datetime.now(timezone.utc)
            self._cached_snapshot = snapshot
            self._last_fetched_at = now_dt


class MockReadOnlyBrokerProvider:
    """Mock read-only broker provider for verified test execution."""

    def __init__(
        self,
        equity: float = 500000.0,
        cash: float = 150000.0,
        buying_power: float = 350000.0,
        positions: Optional[list[PortfolioPosition]] = None,
        account_id: str = "SCHWAB_ACCT_9982",
    ) -> None:
        self.equity = equity
        self.cash = cash
        self.buying_power = buying_power
        self.positions = positions or []
        self.account_id_hash = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:12]

    def get_account_snapshot(self) -> Optional[AccountSnapshot]:
        return AccountSnapshot(
            account_id_hash=self.account_id_hash,
            account_equity=self.equity,
            cash_balance=self.cash,
            buying_power=self.buying_power,
            as_of=datetime.now(timezone.utc),
        )

    def get_positions(self) -> list[PortfolioPosition]:
        return list(self.positions)

    def get_open_orders(self) -> list[dict[str, Any]]:
        return []


class ReadOnlyPortfolioService:
    """Read-Only Portfolio Service isolated from execution router."""

    def __init__(
        self,
        provider: Optional[ReadOnlyBrokerPortfolioProvider] = None,
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        self.provider = provider
        self.cache = PortfolioCache(ttl_seconds=cache_ttl_seconds)

    def fetch_fresh_snapshot(
        self,
        now: Optional[datetime] = None,
    ) -> Optional[PortfolioSnapshot]:
        """Fetch fresh portfolio snapshot from read-only data provider and update cache.

        NO SYNTHETIC FALLBACKS: If provider is missing or returns None, return None.
        """
        if self.provider is None:
            return None

        now_dt = now or datetime.now(timezone.utc)
        account = self.provider.get_account_snapshot()
        if account is None or account.account_equity <= 0:
            return None

        pos_list = self.provider.get_positions()
        open_orders = self.provider.get_open_orders()

        # Calculate sector allocations based on account equity
        sector_totals: dict[str, float] = {}
        for p in pos_list:
            # Option market value uses 100x contract multiplier
            mult = 100.0 if p.asset_class == "OPTION" else 1.0
            mv = abs(p.quantity) * p.current_price * mult
            sector_totals[p.sector] = sector_totals.get(p.sector, 0.0) + mv

        sector_allocations: list[SectorAllocation] = []
        equity = account.account_equity
        for sec, mv in sector_totals.items():
            pct = (mv / equity * 100.0) if equity > 0 else 0.0
            sector_allocations.append(
                SectorAllocation(
                    sector=sec,
                    allocation_pct=round(pct, 2),
                    market_value=round(mv, 2),
                    is_overconcentrated=pct > 25.0,
                )
            )

        # Calculate portfolio Greeks via centralized Greeks calculator
        greeks_calc = calculate_portfolio_greeks(pos_list)

        snapshot = PortfolioSnapshot(
            account=account,
            positions=pos_list,
            open_orders_count=len(open_orders),
            greeks=greeks_calc,
            sector_allocations=sector_allocations,
            source="broker_read_only",
            as_of=now_dt,
            freshness_state="FRESH",
        )

        self.cache.set(snapshot, now=now_dt)
        return snapshot

    def get_cached_snapshot(self, now: Optional[datetime] = None) -> Optional[PortfolioSnapshot]:
        """Read snapshot from cache, refreshing from provider if uninitialized."""
        cached = self.cache.get(now=now)
        if cached is None:
            return self.fetch_fresh_snapshot(now=now)
        return cached
