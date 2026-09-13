"""Canonical RSI (Relative Strength Index) implementation using Wilder's Smoothing."""

import numpy as np
import pandas as pd


def calculate_rsi(prices: pd.Series | np.ndarray | list[float], period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI) using Wilder's exponential smoothing method.

    :param prices: Price series (typically close prices)
    :param period: Lookback period (default 14)
    :return: pd.Series of RSI values (0.0 to 100.0)
    """
    if isinstance(prices, (list, np.ndarray)):
        series = pd.Series(prices, dtype=float)
    else:
        series = prices.astype(float)

    if len(series) < period + 1:
        return pd.Series(np.nan, index=series.index)

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Initial average gain/loss
    avg_gain = pd.Series(index=series.index, dtype=float)
    avg_loss = pd.Series(index=series.index, dtype=float)

    avg_gain.iloc[period] = gain.iloc[1 : period + 1].mean()
    avg_loss.iloc[period] = loss.iloc[1 : period + 1].mean()

    # Wilder's smoothing
    for i in range(period + 1, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # If avg_loss is 0, RSI is 100
    rsi = rsi.fillna(100.0)
    rsi.iloc[:period] = np.nan
    return rsi
