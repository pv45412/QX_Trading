"""Read-only dashboard analytics; no changes to scanner qualification rules."""

from typing import Any
import math

import pandas as pd
from qx.market.sector_rotation import SECTOR_ETFS


# Dashboard-only coverage; the rectangle scanner's universe is unchanged.
DASHBOARD_ETFS = {**SECTOR_ETFS, "Social Sentiment": "BUZZ", "IBD 50": "FFTY",
                  "Cybersecurity": "CIBR", "Cloud Computing": "CLOU", "Software": "IGV",
                  "Insurance": "KIE", "Airlines": "JETS", "Regional Banks": "KRE",
                  "Home Construction": "ITB", "Gold Miners": "GDX", "Metals & Mining": "XME",
                  "Oil Services": "OIH", "Oil & Gas E&P": "XOP", "Natural Gas": "FCG",
                  "Retail": "XRT", "Transportation": "IYT", "Telecommunications": "IYZ", "Steel": "SLX"}


def closes(frame: pd.DataFrame) -> pd.Series:
    if (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans
            or not frame.index.is_unique or not frame.index.is_monotonic_increasing):
        raise ValueError("Invalid observation dates")
    values = frame["close"].astype(float)
    if len(values) < 22 or not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError("Insufficient or invalid prices")
    return values


def metrics(sector: pd.DataFrame, benchmark: pd.DataFrame,
            qqq: pd.DataFrame | None = None, dia: pd.DataFrame | None = None) -> dict[str, Any]:
    left, right = closes(sector), closes(benchmark)
    count = min(252, len(right))
    if len(left) < count:
        raise ValueError("Incomplete benchmark-window coverage")
    left, right = left.iloc[-count:], right.iloc[-count:]
    if not left.index.equals(right.index):
        raise ValueError("Unmatched observation dates")
    ratio = left / right
    returns, spy_returns = left.pct_change().iloc[-21:], right.pct_change().iloc[-21:]
    down = spy_returns < 0
    down_count = int(down.sum())
    up_count = int(((returns > 0) & down).sum())
    # The correction window is SPY's peak-to-trough maximum drawdown in this history.
    drawdown = right / right.cummax() - 1
    trough = int(drawdown.argmin())
    peak = int(right.iloc[:trough + 1].argmax())
    correction = None
    if float(drawdown.iloc[trough]) < 0:
        correction = {"start": right.index[peak].isoformat(), "end": right.index[trough].isoformat(),
                      "spy_return": float(right.iloc[trough] / right.iloc[peak] - 1)}
    dates = pd.DatetimeIndex(right.index)
    prior_month = dates.to_period('M') < dates[-1].to_period('M')
    prior = left.loc[prior_month]
    recent = ratio.iloc[-22:]
    high_position = max(i for i, value in enumerate(recent) if value == recent.max())

    def correlation(other: pd.DataFrame | None) -> float | None:
        if other is None:
            return None
        try:
            values = closes(other).iloc[-22:]
            if not values.index.equals(left.index[-22:]):
                return None
            value = float(returns.corr(values.pct_change().iloc[-21:]))
            return value if math.isfinite(value) else None
        except (ValueError, TypeError, KeyError):
            return None

    return {"as_of": left.index[-1].isoformat(), "sessions": count,
            "return_1d": float(returns.iloc[-1]),
            "excess_1d": float(returns.iloc[-1] - spy_returns.iloc[-1]),
            "mtd": float(left.iloc[-1] / prior.iloc[-1] - 1) if len(prior) else None,
            "rs_change": float(ratio.iloc[-1] / ratio.iloc[-22] - 1),
            "rs_days": int((returns > spy_returns).sum()), "down_days": down_count,
            "up_days": up_count, "up_down": up_count / down_count if down_count else None,
            "corr_qqq": correlation(qqq), "corr_dia": correlation(dia),
            "correction_excess": float(left.iloc[trough] / left.iloc[peak] - 1 - correction["spy_return"]) if correction else None,
            "correction": correction, "current_rs": float(ratio.iloc[-1]),
            "rs_high": float(recent.max()), "days_off_high": len(recent) - 1 - high_position}
