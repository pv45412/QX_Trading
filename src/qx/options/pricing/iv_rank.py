"""IV Rank and IV Percentile metrics engine."""

from typing import List, Optional


def calculate_iv_rank(current_iv: float, low_52w: float, high_52w: float) -> float:
    """Calculate 52-week IV Rank (0-100).

    IV Rank measures where current IV sits relative to its 52-week High/Low range.
    """
    if high_52w <= low_52w or low_52w <= 0:
        return 50.0

    rank = ((current_iv - low_52w) / (high_52w - low_52w)) * 100.0
    return round(max(0.0, min(100.0, rank)), 2)


def calculate_iv_percentile(current_iv: float, iv_history: List[float]) -> float:
    """Calculate 52-week IV Percentile (0-100).

    IV Percentile measures the percentage of days in history where IV was below current IV.
    """
    if not iv_history:
        return 50.0

    lower_count = sum(1 for iv in iv_history if iv < current_iv)
    percentile = (lower_count / len(iv_history)) * 100.0
    return round(max(0.0, min(100.0, percentile)), 2)
