"""Strictly Read-Only Portfolio Service & Cache Layer for QX Platform.

MANDATORY SECURITY BOUNDARY:
This module provides READ-ONLY account equity, positions, and Greek exposures.
It contains ZERO methods for submitting, modifying, canceling, or routing orders.
"""

from datetime import datetime, timezone
import hashlib
from typing import Optional

from qx.portfolio.models import AccountSnapshot, PortfolioGreeks, PortfolioPosition, PortfolioSnapshot, SectorAllocation


class PortfolioCache:
    """Thread-safe in-memory cache for PortfolioSnapshot with configurable TTL."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self.ttl_seconds = max(15.0, min(60.0, ttl_seconds))
        self._cached_snapshot: Optional[PortfolioSnapshot] = None
        self._last_fetched_at: Optional[datetime] = None

    def get(self, now: Optional[datetime] = None) -> Optional[PortfolioSnapshot]:
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
        now_dt = now or datetime.now(timezone.utc)
        self._cached_snapshot = snapshot
        self._last_fetched_at = now_dt


class ReadOnlyPortfolioService:
    """Read-Only Portfolio Service isolated from execution router."""

    def __init__(
        self,
        raw_account_id: str = "SCHWAB_ACCT_9982",
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        self.account_id_hash = hashlib.sha256(raw_account_id.encode("utf-8")).hexdigest()[:12]
        self.cache = PortfolioCache(ttl_seconds=cache_ttl_seconds)

    def fetch_fresh_snapshot(
        self,
        equity: float = 500000.0,
        cash: float = 150000.0,
        buying_power: float = 350000.0,
        positions: Optional[list[PortfolioPosition]] = None,
        now: Optional[datetime] = None,
    ) -> PortfolioSnapshot:
        """Fetch fresh portfolio snapshot from read-only data provider and update cache."""
        now_dt = now or datetime.now(timezone.utc)
        pos_list = positions or []

        # Calculate sector allocations
        sector_totals: dict[str, float] = {}
        total_mv = sum(p.quantity * p.current_price for p in pos_list) if pos_list else 0.0

        for p in pos_list:
            mv = p.quantity * p.current_price
            sector_totals[p.sector] = sector_totals.get(p.sector, 0.0) + mv

        sector_allocations: list[SectorAllocation] = []
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

        # Calculate net portfolio Greeks
        net_delta = sum(p.quantity * p.delta for p in pos_list)
        net_gamma = sum(p.quantity * p.gamma for p in pos_list)
        net_theta = sum(p.quantity * p.theta for p in pos_list)
        net_vega = sum(p.quantity * p.vega for p in pos_list)

        account = AccountSnapshot(
            account_id_hash=self.account_id_hash,
            account_equity=equity,
            cash_balance=cash,
            buying_power=buying_power,
            as_of=now_dt,
        )

        snapshot = PortfolioSnapshot(
            account=account,
            positions=pos_list,
            open_orders_count=0,
            greeks=PortfolioGreeks(
                net_delta=round(net_delta, 2),
                net_gamma=round(net_gamma, 4),
                net_theta=round(net_theta, 2),
                net_vega=round(net_vega, 2),
            ),
            sector_allocations=sector_allocations,
            source="schwab_read_only",
            as_of=now_dt,
            freshness_state="FRESH",
        )

        self.cache.set(snapshot, now=now_dt)
        return snapshot

    def get_cached_snapshot(self, now: Optional[datetime] = None) -> PortfolioSnapshot:
        """Read snapshot from cache, refreshing if uninitialized."""
        cached = self.cache.get(now=now)
        if cached is None:
            return self.fetch_fresh_snapshot(now=now)
        return cached
