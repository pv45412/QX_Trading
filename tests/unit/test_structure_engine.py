"""Unit tests for Canonical Market Structure & Liquidity Engine (qx.structure)."""

import pandas as pd
import numpy as np
import pytest
from qx.structure import (
    StructureAnalysisResult,
    analyze_market_structure,
    detect_fair_value_gaps,
    calculate_vwap_channels,
    FairValueGap,
    VWAPChannels,
)


def test_fair_value_gap_detection():
    # Construct a 5-bar series with a Bullish FVG
    # Bar 1: H=100, L=95
    # Bar 2: H=105, L=98
    # Bar 3: H=112, L=102 (L3 > H1 => FVG between 100 and 102)
    highs = pd.Series([100.0, 105.0, 112.0, 115.0, 118.0])
    lows = pd.Series([95.0, 98.0, 102.0, 110.0, 112.0])
    
    fvgs = detect_fair_value_gaps(highs, lows)
    assert len(fvgs) >= 1
    bullish = [f for f in fvgs if f.gap_type == "BULLISH_FVG"]
    assert len(bullish) >= 1
    assert bullish[0].bottom_price == 100.0
    assert bullish[0].top_price == 102.0


def test_vwap_channels_calculation():
    dates = pd.date_range("2026-09-11 09:30", periods=20, freq="15min")
    bars = pd.DataFrame({
        "open": [100.0 + i for i in range(20)],
        "high": [101.0 + i for i in range(20)],
        "low": [99.0 + i for i in range(20)],
        "close": [100.5 + i for i in range(20)],
        "volume": [1000 + i * 100 for i in range(20)],
    }, index=dates)

    channels = calculate_vwap_channels(bars)
    assert isinstance(channels, VWAPChannels)
    assert channels.vwap > 0
    assert channels.plus_2sd >= channels.plus_1sd >= channels.vwap
    assert channels.minus_2sd <= channels.minus_1sd <= channels.vwap


def test_analyze_market_structure_bullish():
    dates = pd.date_range("2026-09-01", periods=20, freq="D")
    closes = [100, 102, 101, 105, 104, 108, 107, 112, 110, 115, 114, 118, 117, 122, 120, 125, 124, 128, 127, 132]
    bars = pd.DataFrame({
        "open": closes,
        "high": [c + 2 for c in closes],
        "low": [c - 2 for c in closes],
        "close": closes,
        "volume": [5000] * 20,
    }, index=dates)

    result = analyze_market_structure(bars)
    assert isinstance(result, StructureAnalysisResult)
    assert result.current_trend in ["BULLISH", "NEUTRAL"]
    assert result.structure_score >= 50.0
    assert result.vwap_channels is not None
