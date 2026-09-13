"""
QX Market Engine: Fundamental Quality & Long-Term Investment Scoring.
Designed for Long-Term Investors evaluating fundamental growth, relative strength new highs,
debt stability, free cash flow yields, and multi-month consolidation quality.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FundamentalQualityMetrics:
    symbol: str
    eps_growth_quarterly_pct: float
    sales_growth_quarterly_pct: float
    roe_pct: float
    pe_ratio: float
    free_cash_flow_yield_pct: float
    debt_to_equity: float
    rs_line_new_high_before_price: bool
    fundamental_quality_score: float  # Scale 0.0 to 1.0
    investment_tier: str  # 'Institutional Core Growth', 'Quality Watchlist', 'Speculative', 'Weak Fundamentals'


def evaluate_fundamental_quality(
    symbol: str,
    fundamentals: dict,
    price_history: pd.DataFrame | None = None,
    spx_history: pd.DataFrame | None = None,
) -> FundamentalQualityMetrics:
    """
    Evaluates fundamental metrics and relative strength new high conditions for long-term position traders.
    """
    eps_growth = float(fundamentals.get("eps_growth_qtr", 0.0) or 0.0)
    sales_growth = float(fundamentals.get("sales_growth_qtr", 0.0) or 0.0)
    roe = float(fundamentals.get("roe", 0.0) or 0.0)
    pe = float(fundamentals.get("pe_ratio", 0.0) or 0.0)
    fcf_yield = float(fundamentals.get("fcf_yield", 0.0) or 0.0)
    d2e = float(fundamentals.get("debt_to_equity", 0.0) or 0.0)

    # RS Line New High check (RS line = Price / SPX price)
    rs_new_high = _check_rs_line_new_high(price_history, spx_history)

    # Scoring Algorithm
    eps_score = min(max(eps_growth / 25.0, 0.0), 1.0) * 0.25  # 25%+ EPS growth gets max
    sales_score = min(max(sales_growth / 15.0, 0.0), 1.0) * 0.20 # 15%+ Sales growth gets max
    roe_score = min(max(roe / 17.0, 0.0), 1.0) * 0.15 # 17%+ ROE gets max
    fcf_score = min(max(fcf_yield / 5.0, 0.0), 1.0) * 0.15 # 5%+ FCF yield gets max
    debt_penalty = max(0.0, 1.0 - (d2e / 2.0)) * 0.10 # D/E < 2.0 preferred
    rs_score = 0.15 if rs_new_high else 0.05

    total_score = eps_score + sales_score + roe_score + fcf_score + debt_penalty + rs_score
    total_score = min(max(total_score, 0.0), 1.0)

    if total_score >= 0.75:
        tier = "Institutional Core Growth"
    elif total_score >= 0.55:
        tier = "Quality Watchlist"
    elif total_score >= 0.35:
        tier = "Speculative"
    else:
        tier = "Weak Fundamentals"

    return FundamentalQualityMetrics(
        symbol=symbol.upper(),
        eps_growth_quarterly_pct=round(eps_growth, 2),
        sales_growth_quarterly_pct=round(sales_growth, 2),
        roe_pct=round(roe, 2),
        pe_ratio=round(pe, 2),
        free_cash_flow_yield_pct=round(fcf_yield, 2),
        debt_to_equity=round(d2e, 2),
        rs_line_new_high_before_price=rs_new_high,
        fundamental_quality_score=round(total_score, 2),
        investment_tier=tier,
    )


def _check_rs_line_new_high(
    price_history: pd.DataFrame | None,
    spx_history: pd.DataFrame | None,
) -> bool:
    if price_history is None or spx_history is None or price_history.empty or spx_history.empty:
        return False
    try:
        common_idx = price_history.index.intersection(spx_history.index)
        if len(common_idx) < 50:
            return False
        stock_closes = price_history.loc[common_idx, "close"].astype(float)
        spx_closes = spx_history.loc[common_idx, "close"].astype(float)

        rs_line = stock_closes / spx_closes
        recent_rs_max = rs_line.tail(5).max()
        prior_rs_max = rs_line.iloc[-60:-5].max() if len(rs_line) >= 60 else rs_line.iloc[:-5].max()

        stock_price_max = stock_closes.tail(5).max()
        stock_prior_price_max = stock_closes.iloc[-60:-5].max() if len(stock_closes) >= 60 else stock_closes.iloc[:-5].max()

        # RS line makes a new high while price has NOT yet made a new high
        return bool(recent_rs_max > prior_rs_max and stock_price_max <= stock_prior_price_max)
    except Exception:
        return False
