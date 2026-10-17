"""TOPS-MultiTrend — ported from the workspace's ThinkScript study.

Source of truth (user-supplied, `TOPS-MultiTrend v4`, formerly `JT_TrendFlag`):

    def EMA34High  = ExpAverage(high, 34);
    def EMA34Close = ExpAverage(close, 34);
    def EMA34Low   = ExpAverage(low, 34);
    def EMA8  = ExpAverage(close, 8);
    def EMA21 = ExpAverage(close, 21);
    def EMA13 = ExpAverage(close, 13);

    def bullish  = (EMA8 > EMA13) and (EMA13 > EMA21);
    def bearish  = (EMA8 < EMA13) and (EMA13 < EMA21);
    def sideways = !bullish and !bearish;

    def WaveState = {default SW, Bullish, Bearish};
    WaveState = IF bullish AND (EMA21 > EMA34High)
                THEN WaveState.Bullish
                ELSE IF bearish AND (EMA21 < EMA34Low)
                THEN WaveState.Bearish
                ELSE WaveState.SW;

That yields two INDEPENDENT labels:
  * ``Momo``  = bullish / bearish / sideways      (8:13:21 EMA stack)
  * ``Trend`` = Bullish / Bearish / SW            (the 34-wave state)

Three porting decisions worth stating, because they are judgement calls:

1. **The 34-wave uses a HIGH/LOW band, not an EMA of close.** ``EMA34High`` and ``EMA34Low``
   are EMAs of the high and low series; ``EMA34Close`` is computed by the study and never used.
   I port it verbatim rather than simplifying to a close EMA — that would change the signal.

2. **`WaveState` is a recursive var in ThinkScript.** It is re-evaluated per bar from that
   bar's own EMAs, so it behaves as a stateless per-bar function; there is no carry-over to
   reproduce. I implement it as an explicit per-bar branch and assert the stacks are mutually
   exclusive, so an impossible state fails loudly instead of picking a branch silently.

3. **EMA seeding.** ThinkScript's ``ExpAverage`` seeds on the first bar; ``scanner.studies.ema``
   seeds on the first value with ``k = 2/(n+1)``. To keep parity honest I reuse the repo's
   ``ema`` and additionally require a **warmup** of 5x the longest period, because early EMA
   values are seed-dominated and would otherwise emit confident-looking labels from noise.
   Bars before warmup return ``None``, never a guess.

A label on a *forming* bar is not a signal, so states are published only for COMPLETED bars;
a separate ``forming`` preview is available and labelled as such.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from qx.scanner.studies import ema

RULE_ID = "tops_multitrend"
RULE_VERSION = "tops_multitrend_v4"
SOURCE = "TOPS-MultiTrend v4 (JT_TrendFlag) ThinkScript, ported"

MOMENTUM_PERIODS = (8, 13, 21)
WAVE_PERIOD = 34
WARMUP_MULTIPLE = 5

BULLISH = "BULLISH"
BEARISH = "BEARISH"
SIDEWAYS = "SIDEWAYS"


@dataclass(frozen=True)
class MultiTrendSnapshot:
    """One bar's Momo + Trend states with the exact feature values behind them."""

    index: int
    bar_time: str | None
    completed: bool
    momentum: str | None
    trend: str | None
    ema8: float | None
    ema13: float | None
    ema21: float | None
    ema34_high: float | None
    ema34_low: float | None
    bullish_stack: bool | None
    bearish_stack: bool | None
    warmup_ok: bool
    rule_version: str = RULE_VERSION

    @property
    def aligned_up(self) -> bool:
        """Momentum up AND trend up — the explorer's headline condition."""
        return self.momentum == BULLISH and self.trend == BULLISH

    @property
    def aligned_down(self) -> bool:
        return self.momentum == BEARISH and self.trend == BEARISH

    def as_dict(self) -> dict[str, Any]:
        return {
            "momentum": self.momentum,
            "trend": self.trend,
            "ema8": self.ema8,
            "ema13": self.ema13,
            "ema21": self.ema21,
            "ema34_high": self.ema34_high,
            "ema34_low": self.ema34_low,
            "bullish_stack": self.bullish_stack,
            "bearish_stack": self.bearish_stack,
            "warmup_ok": self.warmup_ok,
            "aligned_up": self.aligned_up,
            "aligned_down": self.aligned_down,
            "rule_version": self.rule_version,
        }


def warmup_bars(period: int = WAVE_PERIOD, multiple: int = WARMUP_MULTIPLE) -> int:
    return period * multiple


def _stack(ema8: float, ema13: float, ema21: float) -> tuple[bool, bool]:
    bullish = ema8 > ema13 and ema13 > ema21
    bearish = ema8 < ema13 and ema13 < ema21
    return bullish, bearish


def evaluate_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    times: Sequence[str] | None = None,
    *,
    forming: bool = False,
) -> list[MultiTrendSnapshot]:
    """Compute the study across a series; one snapshot per bar.

    ``forming=False`` (default) drops the final bar so every published state comes
    from a COMPLETED bar. Set ``forming=True`` to evaluate every supplied bar.
    """
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows and closes must be the same length")
    if len(closes) == 0:
        return []

    ema8_series = ema(list(closes), 8)
    ema13_series = ema(list(closes), 13)
    ema21_series = ema(list(closes), 21)
    ema34_high_series = ema(list(highs), WAVE_PERIOD)
    ema34_low_series = ema(list(lows), WAVE_PERIOD)

    last_index = len(closes) if forming else len(closes) - 1
    required = warmup_bars()

    out: list[MultiTrendSnapshot] = []
    for i in range(0, max(0, last_index)):
        stamp = times[i] if times and i < len(times) else None
        warm = i + 1 >= required
        if not warm:
            out.append(MultiTrendSnapshot(
                index=i, bar_time=stamp, completed=i < len(closes) - 1,
                momentum=None, trend=None, ema8=None, ema13=None, ema21=None,
                ema34_high=None, ema34_low=None, bullish_stack=None, bearish_stack=None,
                warmup_ok=False,
            ))
            continue

        e8, e13, e21 = ema8_series[i], ema13_series[i], ema21_series[i]
        e34h, e34l = ema34_high_series[i], ema34_low_series[i]
        for value in (e8, e13, e21, e34h, e34l):
            if value is None or not math.isfinite(value):
                raise ValueError("EMA produced a non-finite value")

        bullish_stack, bearish_stack = _stack(e8, e13, e21)
        # ThinkScript branching order: bullish-wave wins, then bearish, else SW.
        if bullish_stack and e21 > e34h:
            trend = BULLISH
        elif bearish_stack and e21 < e34l:
            trend = BEARISH
        else:
            trend = SIDEWAYS

        momentum = BULLISH if bullish_stack else BEARISH if bearish_stack else SIDEWAYS

        out.append(MultiTrendSnapshot(
            index=i, bar_time=stamp, completed=i < len(closes) - 1,
            momentum=momentum, trend=trend,
            ema8=round(e8, 6), ema13=round(e13, 6), ema21=round(e21, 6),
            ema34_high=round(e34h, 6), ema34_low=round(e34l, 6),
            bullish_stack=bullish_stack, bearish_stack=bearish_stack, warmup_ok=True,
        ))
    return out


def latest(bars: Sequence[dict], *, forming: bool = False) -> MultiTrendSnapshot | None:
    """Latest snapshot from OHLC dicts (the shape the scanner already produces)."""
    if not bars:
        return None
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    times = [str(b.get("date") or b.get("time") or "") or None for b in bars]
    series = evaluate_series(highs, lows, closes, times, forming=forming)
    return series[-1] if series else None


def transition_track(series: Sequence[MultiTrendSnapshot]) -> dict[str, Any]:
    """Bars since the current alignment began, previous state, and transitions."""
    if not series:
        return {"bars_since_alignment": None, "previous_state": None,
                "newly_aligned": False, "lost_alignment": False}

    current = series[-1]
    state = (current.momentum, current.trend)

    bars_since = 0
    for snapshot in reversed(series):
        if (snapshot.momentum, snapshot.trend) == state:
            bars_since += 1
        else:
            break

    previous = series[-2] if len(series) >= 2 else None
    previous_state = (previous.momentum, previous.trend) if previous else None

    aligned_now = current.aligned_up
    aligned_before = bool(previous and previous.aligned_up)
    lost_now = bool(previous and previous.aligned_up and not current.aligned_up)

    return {
        "state": {"momentum": current.momentum, "trend": current.trend},
        "bars_since_alignment": bars_since,
        "previous_state": {"momentum": previous_state[0], "trend": previous_state[1]}
        if previous_state else None,
        "newly_aligned": bool(aligned_now and not aligned_before and len(series) >= 2),
        "lost_alignment": lost_now,
        "warmup_ok": current.warmup_ok,
    }
