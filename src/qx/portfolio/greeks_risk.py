"""Aggregate Greeks risk exposure calculator."""

from typing import Iterable
from qx.portfolio.models import PortfolioGreeks, PortfolioPosition


def calculate_portfolio_greeks(positions: Iterable[PortfolioPosition], spy_beta_map: dict[str, float] | None = None) -> PortfolioGreeks:
    """Calculate aggregate net Delta, Gamma, Theta, and Vega risk across multi-asset positions."""
    spy_beta_map = spy_beta_map or {}
    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    beta_weighted_delta = 0.0

    for pos in positions:
        multiplier = 100.0 if pos.asset_class == "OPTION" else 1.0
        pos_delta = pos.quantity * pos.delta * multiplier
        pos_gamma = pos.quantity * pos.gamma * multiplier
        pos_theta = pos.quantity * pos.theta * multiplier
        pos_vega = pos.quantity * pos.vega * multiplier

        total_delta += pos_delta
        total_gamma += pos_gamma
        total_theta += pos_theta
        total_vega += pos_vega

        beta = spy_beta_map.get(pos.symbol.upper(), 1.0)
        beta_weighted_delta += pos_delta * beta

    return PortfolioGreeks(
        net_delta=round(total_delta, 4),
        net_gamma=round(total_gamma, 4),
        net_theta=round(total_theta, 4),
        net_vega=round(total_vega, 4),
        beta_weighted_delta=round(beta_weighted_delta, 4),
    )
