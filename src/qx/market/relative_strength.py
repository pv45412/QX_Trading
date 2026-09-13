"""Date-validated RS20 diagnostics and Relative Strength engine."""

from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from pydantic import BaseModel


@dataclass(frozen=True)
class RelativeStrength:
    rs20: float | None = None
    momentum_5d: float | None = None
    quadrant: str = "UNKNOWN"
    status: str = "INSUFFICIENT_HISTORY"


class RelativeStrengthResult(BaseModel):
    symbol: str
    benchmark: str = "SPY"
    rs_score_1d: float
    rs_score_5d: float
    rs_score_20d: float
    composite_rs_score: float  # 0-100 normalized score


def relative_strength(sector: pd.DataFrame, benchmark: pd.DataFrame) -> RelativeStrength:
    for frame in (sector, benchmark):
        if "close" not in frame or not isinstance(frame.index, pd.DatetimeIndex):
            return RelativeStrength(status="INVALID_DATA")
        if (frame.index.hasnans or not frame.index.is_unique
                or not frame.index.is_monotonic_increasing):
            return RelativeStrength(status="INVALID_DATA")
        if len(frame) < 26:
            return RelativeStrength()

    if not sector.index[-26:].equals(benchmark.index[-26:]):
        return RelativeStrength(status="DATE_MISMATCH")
    try:
        s = [float(value) for value in sector["close"].iloc[-26:]]
        b = [float(value) for value in benchmark["close"].iloc[-26:]]
    except (TypeError, ValueError):
        return RelativeStrength(status="INVALID_DATA")
    if not all(math.isfinite(value) and value > 0 for value in s + b):
        return RelativeStrength(status="INVALID_DATA")
    current = s[-1] / s[-21] - b[-1] / b[-21]
    prior = s[-6] / s[-26] - b[-6] / b[-26]
    momentum = current - prior
    if not math.isfinite(current) or not math.isfinite(momentum):
        return RelativeStrength(status="INVALID_DATA")
    if current > 0:
        quadrant = "LEADING" if momentum > 0 else "WEAKENING"
    else:
        quadrant = "IMPROVING" if momentum > 0 else "LAGGING"
    return RelativeStrength(current, momentum, quadrant, "COMPUTED")


def calculate_relative_strength(
    symbol_close: pd.Series,
    benchmark_close: pd.Series,
    symbol: str = "TARGET",
    benchmark: str = "SPY",
) -> RelativeStrengthResult:
    """Calculate Relative Strength ratios across 1D, 5D, and 20D windows.

    RS Ratio = (% Return Symbol) - (% Return Benchmark)
    """
    if len(symbol_close) < 21 or len(benchmark_close) < 21:
        return RelativeStrengthResult(
            symbol=symbol,
            benchmark=benchmark,
            rs_score_1d=0.0,
            rs_score_5d=0.0,
            rs_score_20d=0.0,
            composite_rs_score=50.0,
        )

    sym_pct_1d = (symbol_close.iloc[-1] / symbol_close.iloc[-2] - 1.0) * 100.0
    bench_pct_1d = (benchmark_close.iloc[-1] / benchmark_close.iloc[-2] - 1.0) * 100.0
    rs_1d = sym_pct_1d - bench_pct_1d

    sym_pct_5d = (symbol_close.iloc[-1] / symbol_close.iloc[-6] - 1.0) * 100.0
    bench_pct_5d = (benchmark_close.iloc[-1] / benchmark_close.iloc[-6] - 1.0) * 100.0
    rs_5d = sym_pct_5d - bench_pct_5d

    sym_pct_20d = (symbol_close.iloc[-1] / symbol_close.iloc[-21] - 1.0) * 100.0
    bench_pct_20d = (benchmark_close.iloc[-1] / benchmark_close.iloc[-21] - 1.0) * 100.0
    rs_20d = sym_pct_20d - bench_pct_20d

    raw_composite = (0.2 * rs_1d) + (0.3 * rs_5d) + (0.5 * rs_20d)
    norm_score = 50.0 + (raw_composite * 5.0)
    composite_score = float(np.clip(norm_score, 0.0, 100.0))

    return RelativeStrengthResult(
        symbol=symbol,
        benchmark=benchmark,
        rs_score_1d=round(rs_1d, 2),
        rs_score_5d=round(rs_5d, 2),
        rs_score_20d=round(rs_20d, 2),
        composite_rs_score=round(composite_score, 2),
    )
