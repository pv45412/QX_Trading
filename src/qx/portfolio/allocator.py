"""Sector concentration auditor and capital allocation risk manager."""

from collections import defaultdict
from typing import Iterable
from qx.portfolio.greeks_risk import calculate_portfolio_greeks
from qx.portfolio.models import PortfolioPosition, PortfolioSummary, SectorAllocation


def evaluate_portfolio_summary(
    positions: Iterable[PortfolioPosition],
    max_sector_concentration_pct: float = 30.0,
    spy_beta_map: dict[str, float] | None = None,
) -> PortfolioSummary:
    """Compute total market value, net unrealized P&L, aggregate Greeks, and sector concentration audit."""
    pos_list = list(positions)
    if not pos_list:
        return PortfolioSummary(
            total_market_value=0.0,
            total_unrealized_pnl=0.0,
            total_unrealized_pnl_pct=0.0,
            greeks=calculate_portfolio_greeks([]),
            sector_allocations=[],
        )

    total_value = 0.0
    total_cost = 0.0
    sector_values = defaultdict(float)

    for pos in pos_list:
        multiplier = 100.0 if pos.asset_class == "OPTION" else 1.0
        val = abs(pos.quantity) * pos.current_price * multiplier
        cost = abs(pos.quantity) * pos.entry_price * multiplier
        total_value += val
        total_cost += cost
        sector_values[pos.sector] += val

    unrealized_pnl = total_value - total_cost
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100.0) if total_cost > 0 else 0.0

    allocations = []
    for sector, s_val in sector_values.items():
        pct = (s_val / total_value * 100.0) if total_value > 0 else 0.0
        allocations.append(SectorAllocation(
            sector=sector,
            allocation_pct=round(pct, 2),
            market_value=round(s_val, 2),
            is_overconcentrated=pct > max_sector_concentration_pct,
        ))

    allocations.sort(key=lambda a: a.allocation_pct, reverse=True)
    greeks = calculate_portfolio_greeks(pos_list, spy_beta_map=spy_beta_map)

    return PortfolioSummary(
        total_market_value=round(total_value, 2),
        total_unrealized_pnl=round(unrealized_pnl, 2),
        total_unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
        greeks=greeks,
        sector_allocations=allocations,
    )
