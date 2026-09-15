"""Institutional Smart Money Concepts (SMC) Engine.

Translates TOS SMC_Complete_Suite_v3_1 into Python:
- Adaptive Multi-Timeframe Pivot Fractals (10/21-bar windows)
- Structural Breaks: BOS (Trend Continuation) vs CHoCH (Trend Reversal)
- Order Blocks (Demand & Supply OBs) with Auto-Mitigation
- Liquidity Pools (Equal Highs EQH / Equal Lows EQL)
"""

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field


class OrderBlock(BaseModel):
    block_type: str  # "DEMAND_OB" or "SUPPLY_OB"
    top_price: float
    bottom_price: float
    bar_index: int
    is_mitigated: bool = False


class LiquidityPool(BaseModel):
    pool_type: str  # "EQH" or "EQL"
    price: float
    tolerance_pct: float = 0.075


class SMCAnalysisResult(BaseModel):
    regime: str  # "BULLISH", "BEARISH", or "CONSOLIDATION"
    latest_bos: str | None = None
    latest_choch: str | None = None
    demand_ob: OrderBlock | None = None
    supply_ob: OrderBlock | None = None
    liquidity_pools: list[LiquidityPool] = Field(default_factory=list)
    structure_score: float = Field(ge=0.0, le=100.0)


def analyze_smc_structure(bars: pd.DataFrame, is_fast_chart: bool = False) -> SMCAnalysisResult:
    """Analyze OHLCV DataFrame for institutional SMC structure.

    :param bars: DataFrame with 'high', 'low', 'close', 'open', 'volume'
    """
    if len(bars) < 15:
        return SMCAnalysisResult(
            regime="CONSOLIDATION",
            latest_bos=None,
            latest_choch=None,
            demand_ob=None,
            supply_ob=None,
            liquidity_pools=[],
            structure_score=50.0,
        )

    h = bars["high"].to_numpy()
    l = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    o = bars["open"].to_numpy()
    n = len(c)

    # Window lookbacks matching ThinkScript SMC_Complete_Suite
    ext_window = 37 if is_fast_chart else 21
    half_ext = ext_window // 2

    # Pivot detection
    pivot_highs = []
    pivot_lows = []

    for i in range(half_ext, n - half_ext):
        window_h = h[i - half_ext : i + half_ext + 1]
        window_l = l[i - half_ext : i + half_ext + 1]
        if h[i] == np.max(window_h):
            pivot_highs.append((i, float(h[i])))
        if l[i] == np.min(window_l):
            pivot_lows.append((i, float(l[i])))

    if not pivot_highs or not pivot_lows:
        last_h = float(np.max(h[-10:]))
        last_l = float(np.min(l[-10:]))
        pivot_highs = [(n - 5, last_h)]
        pivot_lows = [(n - 5, last_l)]

    major_high = pivot_highs[-1][1]
    major_low = pivot_lows[-1][1]

    curr_price = float(c[-1])
    prev_price = float(c[-2]) if n >= 2 else curr_price

    # Trend State Tracking
    regime = "CONSOLIDATION"
    if curr_price > major_high:
        regime = "BULLISH"
    elif curr_price < major_low:
        regime = "BEARISH"
    else:
        # Check higher highs vs higher lows
        if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
            if pivot_highs[-1][1] > pivot_highs[-2][1] and pivot_lows[-1][1] > pivot_lows[-2][1]:
                regime = "BULLISH"
            elif pivot_highs[-1][1] < pivot_highs[-2][1] and pivot_lows[-1][1] < pivot_lows[-2][1]:
                regime = "BEARISH"

    body_cross_h = (curr_price > major_high) and (prev_price <= major_high)
    body_cross_l = (curr_price < major_low) and (prev_price >= major_low)

    bos = None
    choch = None
    if body_cross_h:
        if regime == "BULLISH":
            bos = "BULLISH_BOS"
        else:
            choch = "BULLISH_CHOCH"
            regime = "BULLISH"

    if body_cross_l:
        if regime == "BEARISH":
            bos = "BEARISH_BOS"
        else:
            choch = "BEARISH_CHOCH"
            regime = "BEARISH"

    # Order Block Extraction (Demand OB & Supply OB)
    demand_ob = None
    supply_ob = None

    # Search backwards for last opposing red candle before a bullish move
    for i in range(n - 2, max(0, n - 20), -1):
        if c[i] < o[i]:  # Red candle (Demand OB Candidate)
            top = round(float(max(o[i], c[i])), 2)
            bot = round(float(l[i]), 2)
            # Check if mitigated (price fell below bottom)
            is_mitigated = float(np.min(l[i+1:])) < bot if i + 1 < n else False
            demand_ob = OrderBlock(
                block_type="DEMAND_OB",
                top_price=top,
                bottom_price=bot,
                bar_index=i,
                is_mitigated=is_mitigated,
            )
            break

    # Search backwards for last opposing green candle before a bearish move
    for i in range(n - 2, max(0, n - 20), -1):
        if c[i] > o[i]:  # Green candle (Supply OB Candidate)
            top = round(float(h[i]), 2)
            bot = round(float(min(o[i], c[i])), 2)
            # Check if mitigated (price rose above top)
            is_mitigated = float(np.max(h[i+1:])) > top if i + 1 < n else False
            supply_ob = OrderBlock(
                block_type="SUPPLY_OB",
                top_price=top,
                bottom_price=bot,
                bar_index=i,
                is_mitigated=is_mitigated,
            )
            break

    # Liquidity Pool Detection (EQH / EQL)
    liquidity_pools = []
    if len(pivot_highs) >= 2:
        h1, h2 = pivot_highs[-1][1], pivot_highs[-2][1]
        if abs(h1 - h2) / h2 <= 0.0015:
            liquidity_pools.append(LiquidityPool(pool_type="EQH", price=round((h1 + h2) / 2, 2)))
    if len(pivot_lows) >= 2:
        l1, l2 = pivot_lows[-1][1], pivot_lows[-2][1]
        if abs(l1 - l2) / l2 <= 0.0015:
            liquidity_pools.append(LiquidityPool(pool_type="EQL", price=round((l1 + l2) / 2, 2)))

    # Structure Score Calculation
    score = 50.0
    if regime == "BULLISH":
        score = 80.0
        if bos == "BULLISH_BOS":
            score = 92.0
        elif choch == "BULLISH_CHOCH":
            score = 88.0
    elif regime == "BEARISH":
        score = 20.0
        if bos == "BEARISH_BOS":
            score = 8.0
        elif choch == "BEARISH_CHOCH":
            score = 12.0

    if demand_ob and not demand_ob.is_mitigated and demand_ob.bottom_price <= curr_price <= demand_ob.top_price * 1.005:
        score = min(98.0, score + 10.0)

    return SMCAnalysisResult(
        regime=regime,
        latest_bos=bos,
        latest_choch=choch,
        demand_ob=demand_ob,
        supply_ob=supply_ob,
        liquidity_pools=liquidity_pools,
        structure_score=round(score, 2),
    )
