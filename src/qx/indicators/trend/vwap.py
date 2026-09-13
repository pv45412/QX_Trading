"""Canonical VWAP (Volume Weighted Average Price) implementation."""

import numpy as np
import pandas as pd


def calculate_vwap(
    high: pd.Series | np.ndarray | list[float],
    low: pd.Series | np.ndarray | list[float],
    close: pd.Series | np.ndarray | list[float],
    volume: pd.Series | np.ndarray | list[float],
) -> pd.Series:
    """Calculate Volume Weighted Average Price (VWAP).

    Typical Price = (High + Low + Close) / 3
    VWAP = Cumulative(Typical Price * Volume) / Cumulative(Volume)

    :param high: High prices
    :param low: Low prices
    :param close: Close prices
    :param volume: Volume
    :return: pd.Series of VWAP values
    """
    h = pd.Series(high, dtype=float)
    l = pd.Series(low, dtype=float)
    c = pd.Series(close, dtype=float)
    v = pd.Series(volume, dtype=float)

    typical_price = (h + l + c) / 3.0
    tp_v = typical_price * v

    cum_tp_v = tp_v.cumsum()
    cum_v = v.cumsum().replace(0, np.nan)

    vwap = cum_tp_v / cum_v
    return vwap
