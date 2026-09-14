"""Canonical Market Structure & Liquidity Engine (BOS, CHoCH, FVG, Swings, VWAP)."""

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field
from qx.structure.fvg import FairValueGap, detect_fair_value_gaps
from qx.structure.vwap import VWAPChannels, calculate_vwap_channels


class StructureAnalysisResult(BaseModel):
    current_trend: str  # "BULLISH", "BEARISH", or "NEUTRAL"
    latest_bos: str | None = None
    latest_choch: str | None = None
    active_fvgs: list[FairValueGap] = Field(default_factory=list)
    vwap_channels: VWAPChannels | None = None
    structure_score: float = Field(ge=0.0, le=100.0)


def analyze_market_structure(bars: pd.DataFrame) -> StructureAnalysisResult:
    """Analyze OHLC bars for market trend, BOS, CHoCH, active FVGs, and VWAP SD Channels.

    :param bars: pd.DataFrame containing 'high', 'low', 'close', 'open' columns
    """
    vwap_bands = calculate_vwap_channels(bars)

    if len(bars) < 10:
        return StructureAnalysisResult(
            current_trend="NEUTRAL",
            latest_bos=None,
            latest_choch=None,
            active_fvgs=[],
            vwap_channels=vwap_bands,
            structure_score=50.0,
        )

    high = bars["high"]
    low = bars["low"]
    close = bars["close"]

    fvgs = detect_fair_value_gaps(high, low)

    # Detect swing highs and swing lows over 5-bar window
    swing_highs = close[(close > close.shift(1)) & (close > close.shift(-1)) & (close > close.shift(2)) & (close > close.shift(-2))]
    swing_lows = close[(close < close.shift(1)) & (close < close.shift(-1)) & (close < close.shift(2)) & (close < close.shift(-2))]

    current_price = float(close.iloc[-1])
    trend = "NEUTRAL"
    bos = None
    choch = None
    score = 50.0

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        higher_highs = float(swing_highs.iloc[-1]) > float(swing_highs.iloc[-2])
        higher_lows = float(swing_lows.iloc[-1]) > float(swing_lows.iloc[-2])

        if higher_highs and higher_lows:
            trend = "BULLISH"
            score = 80.0
            if current_price > float(swing_highs.iloc[-1]):
                bos = "BULLISH_BOS"
                score = 90.0
        elif not higher_highs and not higher_lows:
            trend = "BEARISH"
            score = 20.0
            if current_price < float(swing_lows.iloc[-1]):
                bos = "BEARISH_BOS"
                score = 10.0
        else:
            # Change of character potential
            if higher_highs and not higher_lows:
                choch = "BEARISH_CHOCH"
                score = 40.0
            elif not higher_highs and higher_lows:
                choch = "BULLISH_CHOCH"
                score = 60.0

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
        vwap_channels=vwap_bands,
        structure_score=round(score, 2),
    )
