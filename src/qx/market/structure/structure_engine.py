"""Market Structure Detection Engine (BOS, CHoCH, FVG, Swings)."""

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field


class FairValueGap(BaseModel):
    gap_type: str  # "BULLISH_FVG" or "BEARISH_FVG"
    top_price: float
    bottom_price: float
    bar_index: int


class StructureAnalysisResult(BaseModel):
    current_trend: str  # "BULLISH", "BEARISH", or "NEUTRAL"
    latest_bos: str | None = None
    latest_choch: str | None = None
    active_fvgs: list[FairValueGap] = Field(default_factory=list)
    structure_score: float = Field(ge=0.0, le=100.0)


def detect_fair_value_gaps(
    high: pd.Series,
    low: pd.Series,
    min_gap_pct: float = 0.05,
) -> list[FairValueGap]:
    """Detect Fair Value Gaps (FVG) across 3-bar sequences.

    Bullish FVG: Low of Bar 3 > High of Bar 1
    Bearish FVG: High of Bar 3 < Low of Bar 1
    """
    fvgs: list[FairValueGap] = []
    if len(high) < 3:
        return fvgs

    h = high.to_numpy()
    l = low.to_numpy()

    for i in range(2, len(h)):
        # Bullish FVG
        if l[i] > h[i - 2]:
            gap_size = l[i] - h[i - 2]
            gap_pct = (gap_size / h[i - 2]) * 100.0
            if gap_pct >= min_gap_pct:
                fvgs.append(
                    FairValueGap(
                        gap_type="BULLISH_FVG",
                        top_price=round(float(l[i]), 2),
                        bottom_price=round(float(h[i - 2]), 2),
                        bar_index=i,
                    )
                )
        # Bearish FVG
        elif h[i] < l[i - 2]:
            gap_size = l[i - 2] - h[i]
            gap_pct = (gap_size / l[i - 2]) * 100.0
            if gap_pct >= min_gap_pct:
                fvgs.append(
                    FairValueGap(
                        gap_type="BEARISH_FVG",
                        top_price=round(float(l[i - 2]), 2),
                        bottom_price=round(float(h[i]), 2),
                        bar_index=i,
                    )
                )
    return fvgs


def analyze_market_structure(bars: pd.DataFrame) -> StructureAnalysisResult:
    """Analyze OHLC bars for market trend, BOS, CHoCH, and active FVGs.

    :param bars: pd.DataFrame containing 'high', 'low', 'close', 'open' columns
    """
    if len(bars) < 10:
        return StructureAnalysisResult(
            current_trend="NEUTRAL",
            latest_bos=None,
            latest_choch=None,
            active_fvgs=[],
            structure_score=50.0,
        )

    high = bars["high"]
    low = bars["low"]
    close = bars["close"]

    fvgs = detect_fair_value_gaps(high, low)

    # Detect swing highs and swing lows over 5-bar window
    swing_highs = close[(close > close.shift(1)) & (close > close.shift(-1)) & (close > close.shift(2)) & (close > close.shift(-2))]
    swing_lows = close[(close < close.shift(1)) & (close < close.shift(-1)) & (close < close.shift(2)) & (close < close.shift(-2))]

    current_price = close.iloc[-1]
    trend = "NEUTRAL"
    bos = None
    choch = None
    score = 50.0

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        higher_highs = swing_highs.iloc[-1] > swing_highs.iloc[-2]
        higher_lows = swing_lows.iloc[-1] > swing_lows.iloc[-2]

        if higher_highs and higher_lows:
            trend = "BULLISH"
            score = 80.0
            if current_price > swing_highs.iloc[-1]:
                bos = "BULLISH_BOS"
                score = 90.0
        elif not higher_highs and not higher_lows:
            trend = "BEARISH"
            score = 20.0
            if current_price < swing_lows.iloc[-1]:
                bos = "BEARISH_BOS"
                score = 10.0

    # Adjust score if bullish/bearish FVGs are active near current price
    bullish_fvgs = [f for f in fvgs if f.gap_type == "BULLISH_FVG"]
    bearish_fvgs = [f for f in fvgs if f.gap_type == "BEARISH_FVG"]

    if bullish_fvgs and trend == "BULLISH":
        score = min(100.0, score + 10.0)
    elif bearish_fvgs and trend == "BEARISH":
        score = max(0.0, score - 10.0)

    return StructureAnalysisResult(
        current_trend=trend,
        latest_bos=bos,
        latest_choch=choch,
        active_fvgs=fvgs[-5:],  # Keep recent 5 FVGs
        structure_score=round(score, 2),
    )
