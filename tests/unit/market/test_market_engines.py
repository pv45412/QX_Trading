"""Unit tests for Market Structure and Relative Strength engines."""

import pandas as pd
import pytest
from qx.market.structure.structure_engine import analyze_market_structure, detect_fair_value_gaps
from qx.market.relative_strength import calculate_relative_strength


def test_detect_fair_value_gaps():
    high = pd.Series([100.0, 102.0, 105.0, 108.0])
    low = pd.Series([98.0, 100.0, 103.0, 106.0])
    fvgs = detect_fair_value_gaps(high, low)
    assert len(fvgs) > 0
    assert fvgs[0].gap_type == "BULLISH_FVG"


def test_calculate_relative_strength():
    sym_close = pd.Series([100.0 + i for i in range(25)])
    bench_close = pd.Series([400.0 + (i * 0.1) for i in range(25)])
    res = calculate_relative_strength(sym_close, bench_close, symbol="AAPL", benchmark="SPY")
    assert res.composite_rs_score > 50.0
    assert res.symbol == "AAPL"
