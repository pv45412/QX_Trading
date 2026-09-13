"""Canonical ATR (Average True Range) implementation using Wilder's Smoothing."""

import numpy as np
import pandas as pd


def calculate_atr(
    high: pd.Series | np.ndarray | list[float],
    low: pd.Series | np.ndarray | list[float],
    close: pd.Series | np.ndarray | list[float],
    period: int = 14,
) -> pd.Series:
    """Calculate Average True Range (ATR) using Wilder's smoothing method.

    :param high: High prices
    :param low: Low prices
    :param close: Close prices
    :param period: Lookback period (default 14)
    :return: pd.Series of ATR values
    """
    h = pd.Series(high, dtype=float)
    l = pd.Series(low, dtype=float)
    c = pd.Series(close, dtype=float)

    if len(c) < period + 1:
        return pd.Series(np.nan, index=c.index)

    prev_close = c.shift(1)
    tr1 = h - l
    tr2 = (h - prev_close).abs()
    tr3 = (l - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = pd.Series(index=c.index, dtype=float)
    atr.iloc[period] = tr.iloc[1 : period + 1].mean()

    for i in range(period + 1, len(c)):
        atr.iloc[i] = (atr.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period

    atr.iloc[:period] = np.nan
    return atr
