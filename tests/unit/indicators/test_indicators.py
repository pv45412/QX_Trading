"""Unit tests for canonical qx.indicators package."""

import numpy as np
import pandas as pd
import pytest

from qx.indicators import (
    calculate_rsi,
    calculate_atr,
    calculate_expected_move,
    calculate_iv_rank,
    calculate_iv_percentile,
)


def test_calculate_rsi_range():
    prices = pd.Series([10.0, 11.0, 12.0, 11.5, 12.5, 13.0, 14.0, 13.5, 14.5, 15.0, 16.0, 15.5, 16.5, 17.0, 18.0, 17.5, 18.5, 19.0])
    rsi = calculate_rsi(prices, period=14)
    assert not rsi.isna().all()
    valid_rsi = rsi.dropna()
    assert (valid_rsi >= 0.0).all() and (valid_rsi <= 100.0).all()


def test_calculate_atr_values():
    high = [10, 11, 12, 11.5, 12.5, 13, 14, 13.5, 14.5, 15, 16, 15.5, 16.5, 17, 18, 17.5, 18.5, 19]
    low = [9, 10, 11, 10.5, 11.5, 12, 13, 12.5, 13.5, 14, 15, 14.5, 15.5, 16, 17, 16.5, 17.5, 18]
    close = [9.5, 10.5, 11.5, 11, 12, 12.5, 13.5, 13, 14, 14.5, 15.5, 15, 16, 16.5, 17.5, 17, 18, 18.5]
    atr = calculate_atr(high, low, close, period=14)
    assert not atr.isna().all()
    valid_atr = atr.dropna()
    assert (valid_atr > 0).all()


def test_calculate_expected_move():
    res = calculate_expected_move(price=100.0, implied_volatility=20.0, dte=30)
    assert res["expected_move_dollars"] > 0
    assert res["upper_bound"] == round(100.0 + res["expected_move_dollars"], 2)
    assert res["lower_bound"] == round(100.0 - res["expected_move_dollars"], 2)


def test_calculate_iv_rank():
    iv_history = [15.0, 20.0, 25.0, 30.0, 35.0]
    rank = calculate_iv_rank(25.0, iv_history)
    assert rank == 50.0

    percentile = calculate_iv_percentile(25.0, iv_history)
    assert percentile == 40.0
