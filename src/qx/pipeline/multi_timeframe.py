"""BE2 Multi-Timeframe Context Contract.

Defines the authoritative Option B Dual-Timeframe Evidence Matrix:
- DAY: Setup/Execution 5m, HTF 1h, Macro Daily
- SWING: Setup/Execution 1h, HTF Daily, Macro Weekly
- INVEST: Setup/Execution Daily, HTF Weekly, Macro Monthly

Strict Point-in-Time Causality:
- Only completed HTF candles with completion_timestamp <= evaluation_timestamp may be used.
- Incomplete HTF candles must never enter HTF SMC calculation.
- Zero future lookahead.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from qx.pipeline.point_in_time import (
    aware_utc,
    bar_timestamp,
    evaluated_bar_window_sha256,
    filter_bars_at_or_before,
    parse_timestamp,
)
from qx.structure.smc_suite import SMCAnalysisResult, analyze_smc_structure


HORIZON_TIMEFRAME_MATRIX: Dict[str, Dict[str, str]] = {
    "DAY": {
        "setup": "5m",
        "htf": "1h",
        "macro": "1d",
    },
    "SWING": {
        "setup": "1h",
        "htf": "1d",
        "macro": "1w",
    },
    "INVEST": {
        "setup": "1d",
        "htf": "1w",
        "macro": "1w",  # Standard daily/weekly historical stream
    },
}


def aggregate_daily_bars_to_weekly(bars: Any) -> pd.DataFrame:
    """Aggregate audited daily OHLCV evidence into Monday-anchored weekly bars."""
    if bars is None:
        return pd.DataFrame()
    frame = bars.copy() if isinstance(bars, pd.DataFrame) else pd.DataFrame(bars)
    if frame.empty:
        return pd.DataFrame()

    timestamp_column = next(
        (column for column in ("timestamp", "datetime", "time", "date") if column in frame.columns),
        None,
    )
    if timestamp_column is not None:
        timestamps = pd.DatetimeIndex(
            pd.to_datetime(frame.pop(timestamp_column), utc=True, errors="coerce")
        )
    elif isinstance(frame.index, pd.DatetimeIndex):
        timestamps = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True, errors="coerce"))
    else:
        raise ValueError("Daily bars require an explicit point-in-time timestamp")
    if timestamps.isna().any():
        raise ValueError("Daily bars contain invalid timestamps")

    required_columns = {"open", "high", "low", "close", "volume"}
    if not required_columns.issubset(frame.columns):
        raise ValueError("Daily bars require OHLCV columns")
    frame = frame.loc[:, ["open", "high", "low", "close", "volume"]].copy()
    frame.index = timestamps
    frame = frame.sort_index(kind="stable")
    periods = frame.index.tz_localize(None).to_period("W-SUN")

    rows: list[dict[str, float]] = []
    weekly_timestamps: list[pd.Timestamp] = []
    for period, group in frame.groupby(periods, sort=True):
        rows.append(
            {
                "open": float(group["open"].iloc[0]),
                "high": float(group["high"].max()),
                "low": float(group["low"].min()),
                "close": float(group["close"].iloc[-1]),
                "volume": float(group["volume"].sum()),
            }
        )
        weekly_timestamps.append(period.start_time.tz_localize("UTC"))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(weekly_timestamps))


def resolve_timeframes_for_horizon(horizon: Optional[str]) -> Dict[str, str]:
    """Resolves setup, HTF, and macro timeframes for a given horizon under Option B."""
    norm = (horizon or "DAY").strip().upper()
    return HORIZON_TIMEFRAME_MATRIX.get(norm, HORIZON_TIMEFRAME_MATRIX["DAY"]).copy()


def resolve_horizon_for_timeframe(timeframe: Optional[str]) -> str:
    """Infers default horizon from setup timeframe if not explicitly specified."""
    norm = (timeframe or "5m").strip().lower()
    if norm in ("1d", "daily", "d"):
        return "INVEST"
    if norm in ("1h", "60m", "4h", "240m", "h"):
        return "SWING"
    return "DAY"


def timeframe_duration_timedelta(timeframe: str) -> timedelta:
    """Maps a canonical timeframe string to its exact duration timedelta."""
    norm = timeframe.strip().lower()
    if norm.endswith("m") and norm[:-1].isdigit():
        return timedelta(minutes=int(norm[:-1]))
    if norm.endswith("h") and norm[:-1].isdigit():
        return timedelta(hours=int(norm[:-1]))
    if norm in ("1d", "daily", "d") or (norm.endswith("d") and norm[:-1].isdigit()):
        days = int(norm[:-1]) if norm[:-1].isdigit() else 1
        return timedelta(days=days)
    if norm in ("1w", "weekly", "w") or (norm.endswith("w") and norm[:-1].isdigit()):
        weeks = int(norm[:-1]) if norm[:-1].isdigit() else 1
        return timedelta(weeks=weeks)
    if norm in ("1m", "monthly", "1mo", "mo"):
        return timedelta(days=30)
    return timedelta(minutes=5)


def bar_completion_timestamp(bar: Any, timeframe: str) -> datetime:
    """Determines the exact point-in-time completion timestamp of a bar.
    
    A candle starting at T_start is completed at T_start + duration(timeframe).
    If the bar record carries an explicit completion/end timestamp, that is used.
    """
    for key in ("completion_timestamp", "end_timestamp", "close_time", "end_time"):
        val = None
        if isinstance(bar, dict):
            val = bar.get(key)
        elif isinstance(bar, pd.Series):
            val = bar.get(key)
        else:
            val = getattr(bar, key, None)
        parsed = parse_timestamp(val)
        if parsed is not None:
            return parsed

    start = bar_timestamp(bar)
    if start is None:
        raise ValueError("Bar requires an explicit point-in-time timestamp")
    return aware_utc(start) + timeframe_duration_timedelta(timeframe)


def filter_completed_htf_bars(
    bars: Any,
    evaluation_timestamp: datetime,
    timeframe: str,
) -> Tuple[pd.DataFrame, int, int]:
    """Filters higher-timeframe bars to strictly COMPLETED candles before evaluation_timestamp.
    
    Returns:
        (completed_df, usable_count, incomplete_count)
        
    Strict causality rule:
    Any HTF candle where bar_completion_timestamp > evaluation_timestamp is incomplete
    and MUST be excluded from HTF market structure calculations.
    """
    cutoff = aware_utc(evaluation_timestamp)
    if bars is None:
        return pd.DataFrame(), 0, 0

    if isinstance(bars, pd.DataFrame):
        frame = bars.copy()
    elif isinstance(bars, (list, tuple)):
        if not bars:
            return pd.DataFrame(), 0, 0
        from qx.pipeline.point_in_time import _bar_to_dict
        frame = pd.DataFrame([_bar_to_dict(b) for b in bars])
    else:
        return pd.DataFrame(), 0, 0

    if frame.empty:
        return frame, 0, 0

    completion_times: List[datetime] = []
    for idx in range(len(frame)):
        row = frame.iloc[idx]
        c_time = bar_completion_timestamp(row, timeframe)
        completion_times.append(c_time)

    frame["_completion_time"] = completion_times
    visible_mask = frame["_completion_time"] <= cutoff
    completed_df = frame.loc[visible_mask].copy()
    incomplete_count = int((~visible_mask).sum())
    usable_count = len(completed_df)

    completed_df = completed_df.drop(columns=["_completion_time"])
    
    # Sort stably by timestamp
    timestamp_col = next(
        (col for col in ("timestamp", "datetime", "time", "date") if col in completed_df.columns),
        None,
    )
    if timestamp_col is not None:
        completed_df["_sort_ts"] = pd.to_datetime(completed_df[timestamp_col], utc=True, errors="coerce")
        completed_df = completed_df.sort_values("_sort_ts", kind="stable").drop(columns=["_sort_ts"]).reset_index(drop=True)
    elif isinstance(completed_df.index, pd.DatetimeIndex):
        completed_df = completed_df.sort_index(kind="stable")

    return completed_df, usable_count, incomplete_count


class HTFContextResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    available: bool = False
    timeframe: str
    structure_state: Optional[str] = None  # BULLISH, BEARISH, NEUTRAL, or None
    age_bars: int = 9999
    bar_count: int = 0
    usable_bar_count: int = 0
    incomplete_candle_count: int = 0
    content_sha256: Optional[str] = None
    reason_code: Optional[str] = None
    structure_result: Optional[SMCAnalysisResult] = None


def evaluate_htf_structure(
    bars: Any,
    evaluation_timestamp: datetime,
    timeframe: str,
    symbol: str = "SPY",
    min_bars: int = 5,
) -> HTFContextResult:
    """Evaluates HTF market structure under strict point-in-time candle completion."""
    completed_bars, usable_count, incomplete_count = filter_completed_htf_bars(
        bars=bars,
        evaluation_timestamp=evaluation_timestamp,
        timeframe=timeframe,
    )

    total_bars = usable_count + incomplete_count

    if completed_bars.empty or usable_count < min_bars:
        return HTFContextResult(
            available=False,
            timeframe=timeframe,
            structure_state=None,
            age_bars=9999,
            bar_count=total_bars,
            usable_bar_count=usable_count,
            incomplete_candle_count=incomplete_count,
            content_sha256=None,
            reason_code="INSUFFICIENT_COMPLETED_HTF_BARS" if total_bars > 0 else "NO_HTF_BARS",
        )

    try:
        content_sha256 = evaluated_bar_window_sha256(completed_bars, timeframe)
    except Exception:
        content_sha256 = None

    structure = analyze_smc_structure(
        bars=completed_bars,
        is_fast_chart=True,
        symbol=symbol,
        timeframe=timeframe,
        break_confirmation_mode="CLOSE",
        evaluation_bar_index=len(completed_bars) - 1,
    )

    regime_val = getattr(structure, "regime", "NEUTRAL")
    state_str = str(regime_val.value if hasattr(regime_val, "value") else regime_val).upper()
    age_bars = getattr(structure, "age_bars", 0)

    return HTFContextResult(
        available=True,
        timeframe=timeframe,
        structure_state=state_str,
        age_bars=age_bars,
        bar_count=total_bars,
        usable_bar_count=usable_count,
        incomplete_candle_count=incomplete_count,
        content_sha256=content_sha256,
        structure_result=structure,
    )
