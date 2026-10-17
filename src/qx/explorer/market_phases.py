"""James Boyd 5 Market Phases — ported from the repository's ThinkScript study.

Source of truth: ``.agents/skills/smc-rules-engine/resources/tos_james_boyd_market_phases.tos``
(the workspace already contains this study; the user's paste matches it verbatim).

    MA10  = movingaverage(averageType.EXPONENTIAL, close, 10)
    MA30  = movingaverage(averageType.SIMPLE,      close, 30)
    hull  = HullMovingAvg(price = close, length = 10)

    closeBelow10 = close < MA10
    closeAbove10 = close > MA10
    closeBelow30 = close < MA30
    closeAbove30 = close > MA30
    MA10gtMA30   = MA10 > MA30
    fallingHull  = hull <= hull[1]

    phase1 = closeBelow10 AND closeBelow30
    phase2 = closeAbove10 AND closeBelow30
    phase3 = closeAbove30 AND closeAbove10
    phase4 = phase3 AND MA10gtMA30 AND fallingHull      # subset of phase3
    phase5 = closeBelow10 AND closeAbove30

    label  = if phase4 "4" else if phase1 "1" else if phase2 "2"
             else if phase3 "3" else if phase5 "5" else " "

THREE SUBTLETIES A NAIVE PORT GETS WRONG — all reproduced deliberately:

1. **Phase 4 is a subset of Phase 3, and is tested FIRST.** The script says so in a
   comment ("Test for P4 up front, because it is a subset of P3"). Because
   ``phase3`` also evaluates true in a Phase 4 bar, ``phase3`` alone would label a
   distribution bar as a healthy trend. Priority is therefore P4 > P1 > P2 > P3 > P5,
   not numeric order.

2. **Phase 3 has two sub-states, and the background is the SAME for both.** The header
   comment documents pale-green vs dark-green depending on ``MA10gtMA30``, but the
   ``AssignBackgroundColor`` branches for ``phase3 and MA10gtMA30`` and
   ``Phase3 and !MA10gtMA30`` both resolve to ``Color.DARK_GREEN``. The *label* is
   "3" either way. The documented pale-green never renders in this revision. I expose
   ``phase3_ma_crossed`` as a separate boolean so the distinction is available to the
   UI without contradicting the study's actual colour behaviour.

3. **Strict inequalities leave a gap.** ``close == MA10`` satisfies neither
   ``closeAbove10`` nor ``closeBelow10``, so such a bar falls through the label chain
   to ``" "`` (blank). I return ``phase=None`` with reason ``INDETERMINATE`` rather
   than inventing a phase, matching the study's blank label.

Hull moving average: HMA(n) = WMA( 2*WMA(price, n/2) - WMA(price, n), sqrt(n) ), with
integer period rounding as ThinkScript applies it (n/2 = 5, sqrt(10) = 3).
``hull <= hull[1]`` reproduces ``fallingHull`` including the equality case.

Warmup: the longest lookback is the Hull chain (10 + sqrt(10) ~= 14 bars plus its own
WMA warmup), so I require 5x the longest period (50 bars) before publishing a phase,
and return ``None`` until then rather than guessing from seed-dominated averages.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

RULE_ID = "james_boyd_phases"
RULE_VERSION = "james_boyd_5_phases_v1"
SOURCE = ".agents/skills/smc-rules-engine/resources/tos_james_boyd_market_phases.tos"

FAST_PERIOD = 10
SLOW_PERIOD = 30
HULL_PERIOD = 10
WARMUP_MULTIPLE = 5

PHASE_1 = 1
PHASE_2 = 2
PHASE_3 = 3
PHASE_4 = 4
PHASE_5 = 5

PHASE_LABELS = {
    PHASE_1: "Phase 1 - Downtrend (below 10 EMA and 30 SMA)",
    PHASE_2: "Phase 2 - Early reversal (above 10 EMA, below 30 SMA)",
    PHASE_3: "Phase 3 - Strong uptrend (above both)",
    PHASE_4: "Phase 4 - Pullback warning (phase 3, MA10>MA30, falling Hull)",
    PHASE_5: "Phase 5 - Support bounce (below 10 EMA, above 30 SMA)",
}

INDETERMINATE = "INDETERMINATE"

# The study's own precedence: P4 is tested before the phase it subsumes.
PRIORITY = (PHASE_4, PHASE_1, PHASE_2, PHASE_3, PHASE_5)


def warmup_bars() -> int:
    return SLOW_PERIOD * WARMUP_MULTIPLE


def _wma(values: Sequence[float], period: int) -> list[float | None]:
    """Weighted moving average, ``None`` until the window is full."""
    out: list[float | None] = []
    if period <= 0:
        return [None] * len(values)
    weights = list(range(1, period + 1))
    denominator = sum(weights)
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
            continue
        window = values[i + 1 - period:i + 1]
        out.append(sum(w * v for w, v in zip(weights, window)) / denominator)
    return out


def hull(values: Sequence[float], period: int = HULL_PERIOD) -> list[float | None]:
    """Hull moving average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    half = max(1, period // 2)
    root = max(1, int(round(math.sqrt(period))))
    inner = _wma(values, half)
    outer = _wma(values, period)

    raw: list[float | None] = []
    for a, b in zip(inner, outer):
        raw.append(None if a is None or b is None else 2.0 * a - b)

    # WMA over the raw series, skipping the leading Nones by working on the tail.
    first = next((i for i, v in enumerate(raw) if v is not None), None)
    out: list[float | None] = [None] * len(raw)
    if first is None:
        return out
    tail = [float(v) for v in raw[first:]]
    smoothed = _wma(tail, root)
    for offset, value in enumerate(smoothed):
        out[first + offset] = value
    return out


def sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        out.append(None if i + 1 < period else sum(values[i + 1 - period:i + 1]) / period)
    return out


@dataclass(frozen=True)
class PhaseSnapshot:
    index: int
    bar_time: str | None
    completed: bool
    phase: int | None
    indeterminate_reason: str | None
    ma10: float | None
    ma30: float | None
    hull: float | None
    hull_falling: bool | None
    ma10_gt_ma30: bool | None
    phase3_ma_crossed: bool | None
    warmup_ok: bool
    rule_version: str = RULE_VERSION

    @property
    def label(self) -> str:
        return str(self.phase) if self.phase is not None else " "

    @property
    def description(self) -> str:
        return PHASE_LABELS.get(self.phase, INDETERMINATE) if self.phase else INDETERMINATE

    @property
    def bullish(self) -> bool:
        """Phases 2/3/5 are long-side contexts; 4 warns; 1 is a downtrend."""
        return self.phase in (PHASE_2, PHASE_3, PHASE_5)

    @property
    def warning(self) -> bool:
        return self.phase == PHASE_4

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "label": self.label,
            "description": self.description,
            "indeterminate_reason": self.indeterminate_reason,
            "ma10": self.ma10,
            "ma30": self.ma30,
            "hull": self.hull,
            "hull_falling": self.hull_falling,
            "ma10_gt_ma30": self.ma10_gt_ma30,
            "phase3_ma_crossed": self.phase3_ma_crossed,
            "bullish": self.bullish,
            "warning": self.warning,
            "warmup_ok": self.warmup_ok,
            "rule_version": self.rule_version,
        }


def evaluate_series(
    closes: Sequence[float],
    times: Sequence[str] | None = None,
    *,
    forming: bool = False,
) -> list[PhaseSnapshot]:
    """One phase snapshot per bar. Only COMPLETED bars are published by default."""
    if len(closes) == 0:
        return []

    from qx.scanner.studies import ema

    ma10_series = ema(list(closes), FAST_PERIOD)
    ma30_series = sma(list(closes), SLOW_PERIOD)
    hull_series = hull(list(closes), HULL_PERIOD)

    last = len(closes) if forming else len(closes) - 1
    required = warmup_bars()

    out: list[PhaseSnapshot] = []
    for i in range(0, max(0, last)):
        stamp = times[i] if times and i < len(times) else None
        completed = i < len(closes) - 1
        ma10, ma30, hv = ma10_series[i], ma30_series[i], hull_series[i]
        prev_hull = hull_series[i - 1] if i > 0 else None
        warm = (i + 1 >= required) and None not in (ma10, ma30, hv, prev_hull)

        if not warm:
            out.append(PhaseSnapshot(
                index=i, bar_time=stamp, completed=completed, phase=None,
                indeterminate_reason="INSUFFICIENT_WARMUP", ma10=None, ma30=None, hull=None,
                hull_falling=None, ma10_gt_ma30=None, phase3_ma_crossed=None, warmup_ok=False,
            ))
            continue

        close = closes[i]
        for value in (close, ma10, ma30, hv, prev_hull):
            if not math.isfinite(float(value)):
                raise ValueError("phase inputs must be finite")

        close_below10 = close < ma10
        close_above10 = close > ma10
        close_below30 = close < ma30
        close_above30 = close > ma30
        ma10_gt_ma30 = ma10 > ma30
        hull_falling = hv <= prev_hull

        flags = {
            PHASE_1: close_below10 and close_below30,
            PHASE_2: close_above10 and close_below30,
            PHASE_3: close_above30 and close_above10,
            PHASE_4: (close_above30 and close_above10) and ma10_gt_ma30 and hull_falling,
            PHASE_5: close_below10 and close_above30,
        }

        phase: int | None = None
        reason: str | None = None
        for candidate in PRIORITY:
            if flags[candidate]:
                phase = candidate
                break
        else:
            # Matches the study: strict inequalities can satisfy nothing, and the
            # label chain falls through to a blank.
            reason = INDETERMINATE

        out.append(PhaseSnapshot(
            index=i, bar_time=stamp, completed=completed, phase=phase,
            indeterminate_reason=reason,
            ma10=round(ma10, 6), ma30=round(ma30, 6), hull=round(hv, 6),
            hull_falling=hull_falling, ma10_gt_ma30=ma10_gt_ma30,
            phase3_ma_crossed=(ma10_gt_ma30 if phase == PHASE_3 else None),
            warmup_ok=True,
        ))
    return out


def latest(bars: Sequence[dict], *, forming: bool = False) -> PhaseSnapshot | None:
    """Latest phase snapshot from the OHLC dicts the scanner already produces."""
    if not bars:
        return None
    closes = [b["close"] for b in bars]
    times = [str(b.get("date") or b.get("time") or "") or None for b in bars]
    series = evaluate_series(closes, times, forming=forming)
    return series[-1] if series else None


def transition_track(series: Sequence[PhaseSnapshot]) -> dict[str, Any]:
    """Bars in the current phase, the previous phase, and phase transitions."""
    if not series:
        return {"bars_in_phase": None, "previous_phase": None,
                "phase_changed": False, "entered_warning": False, "left_warning": False}

    current = series[-1]
    bars_in_phase = 0
    for snapshot in reversed(series):
        if snapshot.phase == current.phase:
            bars_in_phase += 1
        else:
            break

    previous = series[-2] if len(series) >= 2 else None
    return {
        "phase": current.phase,
        "bars_in_phase": bars_in_phase,
        "previous_phase": previous.phase if previous else None,
        "phase_changed": bool(previous and previous.phase != current.phase),
        "entered_warning": bool(previous and previous.phase != PHASE_4 and current.phase == PHASE_4),
        "left_warning": bool(previous and previous.phase == PHASE_4 and current.phase != PHASE_4),
        "warmup_ok": current.warmup_ok,
    }
