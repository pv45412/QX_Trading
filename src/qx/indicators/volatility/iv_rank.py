"""Canonical IV Rank and IV Percentile calculation routines."""

import numpy as np
import pandas as pd


def calculate_iv_rank(
    current_iv: float,
    iv_history: pd.Series | list[float],
) -> float:
    """Calculate IV Rank relative to 52-week (or custom period) high and low.

    Formula: IV Rank = (Current IV - Min IV) / (Max IV - Min IV) * 100

    :param current_iv: Current Implied Volatility
    :param iv_history: Historical IV series
    :return: IV Rank float between 0.0 and 100.0
    """
    series = pd.Series(iv_history, dtype=float).dropna()
    if len(series) == 0:
        return 50.0

    min_iv = series.min()
    max_iv = series.max()

    if max_iv == min_iv:
        return 50.0

    rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100.0
    return float(np.clip(rank, 0.0, 100.0))


def calculate_iv_percentile(
    current_iv: float,
    iv_history: pd.Series | list[float],
) -> float:
    """Calculate IV Percentile (percentage of past days where IV was lower than current IV).

    :param current_iv: Current Implied Volatility
    :param iv_history: Historical IV series
    :return: IV Percentile float between 0.0 and 100.0
    """
    series = pd.Series(iv_history, dtype=float).dropna()
    if len(series) == 0:
        return 50.0

    count_below = (series < current_iv).sum()
    percentile = (count_below / len(series)) * 100.0
    return float(np.clip(percentile, 0.0, 100.0))
