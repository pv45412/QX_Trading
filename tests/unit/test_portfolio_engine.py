"""Unit tests for QX Multi-Asset Portfolio Engine & Greeks Risk Matrix."""

import pytest
from qx.portfolio import (
    PortfolioGreeks,
    PortfolioPosition,
    PortfolioSummary,
    SectorAllocation,
    calculate_portfolio_greeks,
    evaluate_portfolio_summary,
)


def test_portfolio_greeks_calculation():
    """Verify aggregate portfolio Greeks risk exposure math."""
    positions = [
        PortfolioPosition(
            symbol="AAPL",
            asset_class="STOCK",
            sector="Information Technology",
            quantity=100,
            entry_price=150.0,
            current_price=160.0,
            delta=1.0,
        ),
        PortfolioPosition(
            symbol="AAPL",
            asset_class="OPTION",
            sector="Information Technology",
            quantity=1,  # 1 Call contract = 100 multiplier
            entry_price=5.0,
            current_price=7.5,
            delta=0.65,
            gamma=0.04,
            theta=-0.08,
            vega=0.15,
        ),
    ]

    greeks = calculate_portfolio_greeks(positions)
    assert isinstance(greeks, PortfolioGreeks)
    assert greeks.net_delta == 165.0  # 100 * 1.0 + 1 * 100 * 0.65 = 165.0
    assert greeks.net_gamma == 4.0   # 1 * 100 * 0.04 = 4.0
    assert greeks.net_theta == -8.0  # 1 * 100 * -0.08 = -8.0
    assert greeks.net_vega == 15.0   # 1 * 100 * 0.15 = 15.0


def test_portfolio_summary_and_sector_allocation():
    """Verify total market value, unrealized P&L, and sector concentration audit."""
    positions = [
        PortfolioPosition(
            symbol="XLK",
            asset_class="STOCK",
            sector="Information Technology",
            quantity=200,
            entry_price=200.0,
            current_price=210.0,
        ),
        PortfolioPosition(
            symbol="XLE",
            asset_class="STOCK",
            sector="Energy",
            quantity=50,
            entry_price=80.0,
            current_price=90.0,
        ),
    ]

    summary = evaluate_portfolio_summary(positions, max_sector_concentration_pct=80.0)
    assert isinstance(summary, PortfolioSummary)
    assert summary.total_market_value == 200 * 210 + 50 * 90  # 42000 + 4500 = 46500.0
    assert summary.total_unrealized_pnl == (42000 - 40000) + (4500 - 4000)  # 2500.0

    assert len(summary.sector_allocations) == 2
    tech_allocation = next(a for a in summary.sector_allocations if a.sector == "Information Technology")
    assert tech_allocation.allocation_pct > 85.0
    assert tech_allocation.is_overconcentrated is True  # > 80% concentration limit
