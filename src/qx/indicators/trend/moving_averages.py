"""Canonical SMA (Simple Moving Average) and EMA (Exponential Moving Average) implementations."""

import numpy as np
import pandas as pd


def calculate_sma(
    prices: pd.Series | np.ndarray | list[float],
    period: int = 20,
) -> pd.Series:
    """Calculate Simple Moving Average (SMA).

    :param prices: Price series
    :param period: Lookback period
    :return: pd.Series of SMA values
    """
    series = pd.Series(prices, dtype=float)
    return series.rolling(window=period).mean()


def calculate_ema(
    prices: pd.Series | np.ndarray | list[float],
    period: int = 20,
) -> pd.Series:
    """Calculate Exponential Moving Average (EMA).

    :param prices: Price series
    :param period: Lookback period
    :return: pd.Series of EMA values
    """
    series = pd.Series(prices, dtype=float)
    return series.ewm(span=period, adjust=False).mean()
