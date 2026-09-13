from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import pandas as pd


@dataclass(frozen=True)
class EmaTimingSnapshot:
    score: float
    label: str
    trigger: str
    alignment: str
    note: str


class EmaTimingProvider(Protocol):
    def get_timing(self, symbol: str) -> EmaTimingSnapshot:
        """Return fractal EMA timing for the symbol."""


class YFinanceEmaTimingProvider:
    """Builds daily/hourly/30m/15m EMA timing from yfinance bars."""

    def get_timing(self, symbol: str) -> EmaTimingSnapshot:
        daily = _download(symbol, period="3mo", interval="1d")
        hourly = _download(symbol, period="60d", interval="60m")
        thirty = _download(symbol, period="30d", interval="30m")
        fifteen = _download(symbol, period="5d", interval="15m")
        return build_ema_timing_snapshot(
            daily=daily,
            hourly=hourly,
            thirty_min=thirty,
            fifteen_min=fifteen,
        )


def build_ema_timing_snapshot(
    *,
    daily: pd.DataFrame,
    hourly: pd.DataFrame,
    thirty_min: pd.DataFrame,
    fifteen_min: pd.DataFrame,
) -> EmaTimingSnapshot:
    daily_speed = _ema_state(daily, 5)
    hourly_floor = _ema_state(hourly, 50)
    thirty_mean = _ema_state(thirty_min, 21)
    fifteen_trigger = _ema_state(fifteen_min, 8)

    score = (
        (0.25 if daily_speed.above and daily_speed.rising else 0.0)
        + (0.30 if hourly_floor.above else 0.0)
        + (0.25 if thirty_mean.above else 0.0)
        + (0.20 if fifteen_trigger.above else 0.0)
    )
    label = _timing_label(score)
    trigger = "Trigger active" if fifteen_trigger.above else "Wait for 15m 8 EMA reclaim"
    alignment = (
        f"D5 {'up' if daily_speed.rising else 'flat/down'}; "
        f"H50 {'held' if hourly_floor.above else 'lost'}; "
        f"30m21 {'above' if thirty_mean.above else 'below'}; "
        f"15m8 {'above' if fifteen_trigger.above else 'below'}"
    )
    note = (
        "Fractal EMA stack is aligned for execution."
        if score >= 0.80
        else "Setup can stay on watchlist, but timing trigger is incomplete."
    )
    return EmaTimingSnapshot(
        score=round(score, 3),
        label=label,
        trigger=trigger,
        alignment=alignment,
        note=note,
    )


@dataclass(frozen=True)
class _EmaState:
    above: bool
    rising: bool


def _download(symbol: str, *, period: str, interval: str) -> pd.DataFrame:
    import yfinance as yf  # type: ignore[import-untyped]

    frame = cast(
        pd.DataFrame,
        yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
        ),
    )
    if frame.empty:
        raise ValueError(f"No {interval} timing data returned for {symbol}")
    return frame


def _ema_state(frame: pd.DataFrame, span: int) -> _EmaState:
    close = _close_series(frame)
    if len(close) < span + 2:
        return _EmaState(False, False)
    ema = close.ewm(span=span, adjust=False).mean()
    return _EmaState(
        above=float(close.iloc[-1]) > float(ema.iloc[-1]),
        rising=float(ema.iloc[-1]) > float(ema.iloc[-2]),
    )


def _close_series(frame: pd.DataFrame) -> pd.Series:
    if isinstance(frame.columns, pd.MultiIndex):
        close_data = frame.xs("Close", axis=1, level=0, drop_level=True)
        if isinstance(close_data, pd.Series):
            return close_data.astype(float).dropna()
        return close_data.iloc[:, 0].astype(float).dropna()
    columns = {str(column).strip().lower(): column for column in frame.columns}
    close_column = columns.get("close")
    if close_column is None:
        raise ValueError("Timing data missing close column")
    return frame[close_column].astype(float).dropna()


def _timing_label(score: float) -> str:
    if score >= 0.80:
        return "Aligned"
    if score >= 0.50:
        return "Setting Up"
    return "Not Ready"
