"""QX MASTER AUTO FAST v5.2.4 — ported from the user's ThinkScript.

Source: `QX MASTER AUTO FAST`, Version 5.2.4 (FIXED VARIABLE ORDER & ARROWS),
supplied by the user. This study is NOT in the repository.

It is a COMPLETE signal system — regime, bias, trigger, entry, exit and trade plan —
so the port preserves the study's exact evaluation order and state semantics.

SEVEN SUBTLETIES THAT CHANGE THE SIGNALS IF PORTED NAIVELY
---------------------------------------------------------
1. **VWave is a movement-weighted average, not a VWAP and not an EMA.**
   ``priceMovement = Max(high - low, |close - close[1]|)``; the value is
   ``Sum(source * movement, n) / Sum(movement, n)`` over a trailing window. So it is
   a *volatility-weighted* mean of an arbitrary source series (high / close / low).

2. **RVOL uses DIFFERENT bar offsets for live vs completed bars.**
   ``rvolLive      = volume       / Average(volume[1], n)``
   ``rvolCompleted = volume[1]    / Average(volume[2], n)``
   i.e. on the last bar the study compares the FORMING bar against the prior n-bar
   average, and elsewhere it compares the last COMPLETED bar against the average
   *ending one bar earlier*. This is deliberate; collapsing it to one formula
   silently shifts every volume gate.

3. **`bullRegime` requires ``waveSlow > waveHigh``** — the SLOW close-wave must be
   above the HIGH-wave. That is a strict, unusual condition (it implies the
   movement-weighted high-average is still below the slower close-average), and it is
   what makes ``callReady`` rare. Not a typo to "fix".

4. **`rsiBearish` is written against overbought, not oversold.**
   ``rsiBearish = rsiValue < 50 and !rsiOverboughtState`` — the study guards
   ``rsiOverboughtState`` in BOTH the bullish and bearish definitions. Reproduced
   verbatim; the label logic then ORs in the oversold state separately.

5. **`biasState` and `tradeDirection` are latched (CompoundValue) state machines.**
   Bias latches on the FIRST confirmed evidence in either direction and holds until
   the opposite confirms — it does not fall back to 0. Direction latches to 0 on the
   first exit condition. Order of the branches is load-bearing.

6. **`callActive` has two independent arms:**
   ``breaksUp OR (close > waveHigh and close[1] <= waveHigh[1])`` — a tick-buffered
   break of the recent high, OR a fresh cross above the high-wave. Dropping the
   second arm loses cross-without-break entries.

7. **`callCandidate` fires only on the rising EDGE** (``callActive and !callActive[1]``)
   and only when ``sessionOK``. Signals are transitions, never levels.

SuperTrend uses ``CompoundValue`` with ``close < superTrend[1]`` deciding which band
becomes the new line, seeded from ``stLower`` — this is the standard SuperTrend latch
and is reproduced exactly. Note the study's ATR for SuperTrend is a **Hull** moving
average of TrueRange, not Wilder's.

Forming-bar discipline: like the other ports, only COMPLETED bars are published by
default (``forming=False``), and every state carries ``rule_version``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

RULE_ID = "qx_master_auto_fast"
RULE_VERSION = "qx_master_auto_fast_v5_2_4"
SOURCE = "QX MASTER AUTO FAST v5.2.4 (user-supplied ThinkScript)"

# ---- defaults mirroring the study's inputs -------------------------------------
DEFAULTS: dict[str, Any] = {
    "wave_length": 34,
    "fast_wave_length": 8,
    "mid_wave_length": 13,
    "slow_wave_length": 21,
    "use_vwap_filter": True,
    "use_volume_filter": True,
    "volume_length": 20,
    "rsi_length": 14,
    "rsi_overbought": 70.0,
    "rsi_oversold": 30.0,
    "atr_length": 14,
    "atr_stop_multiplier": 1.10,
    "target1_r": 1.00,
    "target2_r": 2.00,
    "use_auto_timeframe_settings": True,
    "min_relative_volume": 0.90,
    "strong_relative_volume": 1.20,
    "trigger_length": 5,
    "trigger_buffer_ticks": 1,
    "bias_slope_bars": 3,
    "use_supertrend_bias": True,
    "supertrend_atr_length_1m": 5,
    "supertrend_atr_length_5m": 8,
    "supertrend_multiplier_1m": 1.25,
    "supertrend_multiplier_5m": 1.75,
    "supertrend_fallback_atr_length": 8,
    "supertrend_fallback_multiplier": 1.75,
    "bias_flip_confirm_bars": 2,
    "entries_rth_only": False,
    "tick_size": 0.01,
}

# Autotimeframe overrides, verbatim from the study.
EFF_MIN_RVOL_1M, EFF_MIN_RVOL_5M = 0.85, 0.95
EFF_STRONG_RVOL_1M, EFF_STRONG_RVOL_5M = 1.15, 1.25

WARMUP_MULTIPLE = 4


def warmup_bars(config: dict[str, Any] | None = None) -> int:
    cfg = {**DEFAULTS, **(config or {})}
    longest = max(cfg["wave_length"], cfg["slow_wave_length"], cfg["volume_length"],
                  cfg["supertrend_fallback_atr_length"], cfg["atr_length"])
    return longest * WARMUP_MULTIPLE


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #

def _wilder(values: Sequence[float], period: int) -> list[float | None]:
    """MovingAverage(AverageType.WILDERS, ...): SMA seed then Wilder smoothing."""
    out: list[float | None] = [None] * len(values)
    if len(values) < period or period <= 0:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def _sma_series(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        if i + 1 >= period:
            out[i] = sum(values[i + 1 - period:i + 1]) / period
    return out


def _hull_ma(values: Sequence[float], period: int) -> list[float | None]:
    """Hull MA over a Series, reusing the verified port in market_phases."""
    from qx.explorer.market_phases import hull as hull_series

    return hull_series(list(values), period)


def vwave(source: Sequence[float], high: Sequence[float], low: Sequence[float],
          close: Sequence[float], length: int) -> list[float | None]:
    """VWave: Sum(source * movement, n) / Sum(movement, n), movement from H/L/C."""
    n = len(source)
    movement: list[float] = []
    for i in range(n):
        prev_close = close[i - 1] if i > 0 else close[i]
        movement.append(max(high[i] - low[i], abs(close[i] - prev_close)))

    out: list[float | None] = [None] * n
    for i in range(n):
        if i + 1 < length:
            continue
        window_move = movement[i + 1 - length:i + 1]
        total = sum(window_move)
        if total == 0:
            out[i] = source[i]                      # study: `else source`
        else:
            weighted = sum(s * m for s, m in zip(source[i + 1 - length:i + 1], window_move))
            out[i] = weighted / total
    return out


def rsi_wilder(closes: Sequence[float], period: int) -> list[float | None]:
    """The study's RSI: Wilder smoothing of up/down price change."""
    n = len(closes)
    adv_raw, dec_raw = [0.0] * n, [0.0] * n
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        adv_raw[i] = max(change, 0.0)
        dec_raw[i] = abs(min(change, 0.0))
    adv = _wilder(adv_raw, period)
    dec = _wilder(dec_raw, period)
    out: list[float | None] = [None] * n
    for i in range(n):
        a, d = adv[i], dec[i]
        if a is None or d is None:
            continue
        if d == 0:
            out[i] = 100.0
        elif a == 0:
            out[i] = 0.0
        else:
            out[i] = 100.0 - (100.0 / (1.0 + a / d))
    return out


def supertrend(high: Sequence[float], low: Sequence[float], close: Sequence[float],
               atr_series: Sequence[float | None], multiplier: float) -> list[float | None]:
    """CompoundValue latch: close < superTrend[1] ? upper : lower, seeded from lower."""
    n = len(close)
    out: list[float | None] = [None] * n
    prev: float | None = None
    for i in range(n):
        atr_value = atr_series[i]
        if atr_value is None or not math.isfinite(float(atr_value)):
            continue
        hl2 = (high[i] + low[i]) / 2.0
        upper = hl2 + multiplier * atr_value
        lower = hl2 - multiplier * atr_value
        if prev is None:
            prev = lower                            # seed = stLower
        else:
            prev = upper if close[i] < prev else lower
        out[i] = prev
    return out


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MasterSnapshot:
    index: int
    bar_time: str | None
    completed: bool
    # regime / waves
    wave_high: float | None
    wave_center: float | None
    wave_low: float | None
    wave_fast: float | None
    wave_mid: float | None
    wave_slow: float | None
    bull_stack: bool | None
    bear_stack: bool | None
    bull_regime: bool | None
    bear_regime: bool | None
    bull_build: bool | None
    bear_build: bool | None
    # study states
    rsi: float | None
    supertrend: float | None
    st_bull: bool | None
    bias_state: int | None
    bull_bias: bool | None
    bear_bias: bool | None
    vwap: float | None
    rvol_display: float | None
    volume_ok: bool | None
    volume_strong: bool | None
    # triggers and lifecycle
    call_trigger_price: float | None
    put_trigger_price: float | None
    call_watch: bool | None
    put_watch: bool | None
    bull_bounce: bool | None
    bear_pullback: bool | None
    call_ready: bool | None
    put_ready: bool | None
    call_active: bool | None
    put_active: bool | None
    call_signal: bool | None
    put_signal: bool | None
    trade_direction: int | None
    trade_entry: float | None
    trade_atr: float | None
    active_stop: float | None
    active_target1: float | None
    active_target2: float | None
    # presentation states (the study's price-colour cascade)
    price_state: str | None
    bias_label: str | None
    setup_label: str | None
    warmup_ok: bool
    rule_version: str = RULE_VERSION

    def as_dict(self) -> dict[str, Any]:
        payload = {k: v for k, v in self.__dict__.items()}
        payload["reward_risk_t1"] = self._rr(self.active_target1)
        payload["reward_risk_t2"] = self._rr(self.active_target2)
        return payload

    def _rr(self, target: float | None) -> float | None:
        if target is None or self.trade_entry is None or self.active_stop is None:
            return None
        risk = abs(self.trade_entry - self.active_stop)
        if risk <= 0:
            return None
        return round(abs(target - self.trade_entry) / risk, 4)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

def evaluate_series(
    bars: Sequence[dict],
    config: dict[str, Any] | None = None,
    *,
    forming: bool = False,
    minutes: int = 1440,
) -> list[MasterSnapshot]:
    """Evaluate QX MASTER AUTO across a bar series.

    ``bars`` are OHLCV dicts (the shape the scanner produces). ``minutes`` selects
    the autotimeframe branch: 1 -> one-minute, 5 -> five-minute, else fallback.
    """
    cfg = {**DEFAULTS, **(config or {})}
    # F07: drop the final bar only when it is GENUINELY still forming. The previous
    # rule (`n - 1`) discarded a completed final bar unconditionally. This must run
    # BEFORE the series arrays are built, so every feature sees the same bars.
    if not forming:
        from qx.explorer import bars as bars_mod

        bars = bars_mod.select_series(
            bars, interval=("1d" if minutes >= 1440 else f"{minutes}m"))
    n = len(bars)
    if n == 0:
        return []

    high = [float(b["high"]) for b in bars]
    low = [float(b["low"]) for b in bars]
    close = [float(b["close"]) for b in bars]
    open_ = [float(b.get("open", b["close"])) for b in bars]
    volume = [float(b.get("volume") or 0.0) for b in bars]
    times = [str(b.get("date") or b.get("time") or "") or None for b in bars]

    is_one_min = minutes <= 1
    is_five_min = 1 < minutes <= 5
    is_intraday = minutes < 1440

    wl, fwl, mwl, swl = cfg["wave_length"], cfg["fast_wave_length"], cfg["mid_wave_length"], cfg["slow_wave_length"]
    wave_high = vwave(high, high, low, close, wl)
    wave_center = vwave(close, high, low, close, wl)
    wave_low = vwave(low, high, low, close, wl)
    wave_fast = vwave(close, high, low, close, fwl)
    wave_mid = vwave(close, high, low, close, mwl)
    wave_slow = vwave(close, high, low, close, swl)

    rsi_series = rsi_wilder(close, cfg["rsi_length"])

    true_range = [0.0] * n
    for i in range(n):
        prev_close = close[i - 1] if i > 0 else close[i]
        true_range[i] = max(high[i] - low[i], abs(high[i] - prev_close), abs(low[i] - prev_close))

    st_atr_len = cfg["supertrend_atr_length_1m"] if is_one_min else (
        cfg["supertrend_atr_length_5m"] if is_five_min else cfg["supertrend_fallback_atr_length"])
    st_mult = cfg["supertrend_multiplier_1m"] if is_one_min else (
        cfg["supertrend_multiplier_5m"] if is_five_min else cfg["supertrend_fallback_multiplier"])
    st_atr = _hull_ma(true_range, st_atr_len) if st_atr_len > 1 else list(true_range)
    st_series = supertrend(high, low, close, st_atr, st_mult)

    atr_series = _sma_series(true_range, cfg["atr_length"])

    # Running VWAP over the supplied window (study uses session VWAP; the caller
    # supplies session-scoped bars for intraday).
    vwap_series: list[float | None] = [None] * n
    cum_pv = cum_v = 0.0
    for i in range(n):
        tp = (high[i] + low[i] + close[i]) / 3.0
        cum_pv += tp * volume[i]
        cum_v += volume[i]
        vwap_series[i] = (cum_pv / cum_v) if cum_v > 0 else None

    eff_min = cfg["min_relative_volume"]
    eff_strong = cfg["strong_relative_volume"]
    if cfg["use_auto_timeframe_settings"]:
        if is_one_min:
            eff_min, eff_strong = EFF_MIN_RVOL_1M, EFF_STRONG_RVOL_1M
        elif is_five_min:
            eff_min, eff_strong = EFF_MIN_RVOL_5M, EFF_STRONG_RVOL_5M

    vol_len = cfg["volume_length"]
    avg_vol_live = _sma_series(volume, vol_len)                 # Average(volume[1], n) shifted
    avg_vol_completed = _sma_series(volume, vol_len)

    bias_slope = cfg["bias_slope_bars"]
    confirm = cfg["bias_flip_confirm_bars"]
    trigger_len = 3 if is_one_min else (5 if is_five_min else cfg["trigger_length"])
    buffer_ticks = max(1, cfg["trigger_buffer_ticks"])
    tick = cfg["tick_size"]

    required = warmup_bars(cfg)
    # F07 selection already applied at the top of this function.
    last = n if forming else n - 1

    out: list[MasterSnapshot] = []
    bias_state = 0
    trade_direction = 0
    trade_entry: float | None = None
    trade_atr: float | None = None
    prev_call_active = False
    prev_put_active = False
    bull_evidence_hist: list[bool] = []
    bear_evidence_hist: list[bool] = []

    # F07: `last` is an EXCLUSIVE bound, so it must be `n` to evaluate every bar in
    # the series. Previously it was `n - 1`, which silently dropped the final bar
    # even after the completion rule above had correctly kept it.
    for i in range(0, max(0, n if forming else n)):
        warm = (i + 1 >= required) and i >= bias_slope

        def need(*values: Any) -> bool:
            return all(v is not None and math.isfinite(float(v)) for v in values)

        base_ready = warm and need(wave_high[i], wave_center[i], wave_low[i], wave_fast[i],
                                   wave_mid[i], wave_slow[i], rsi_series[i], atr_series[i],
                                   avg_vol_live[i], vwap_series[i], st_series[i])
        slope_ready = base_ready and i >= bias_slope and need(wave_center[i - bias_slope], wave_slow[i - bias_slope])

        if not slope_ready:
            # Keep the latches consistent, but publish no state.
            out.append(_blank(i, times[i], i < n - 1))
            continue

        wf, wm, ws = wave_fast[i], wave_mid[i], wave_slow[i]
        wh, wc, wlo = wave_high[i], wave_center[i], wave_low[i]
        bull_stack = wf > wm and wm > ws
        bear_stack = wf < wm and wm < ws
        bull_regime = bull_stack and ws > wh
        bear_regime = bear_stack and ws < wlo
        bull_build = bull_stack and close[i] > wc
        bear_build = bear_stack and close[i] < wc

        rsi_value = rsi_series[i]
        rsi_overbought = rsi_value >= cfg["rsi_overbought"]
        rsi_oversold = rsi_value <= cfg["rsi_oversold"]

        st_value = st_series[i]
        st_bull = close[i] > st_value
        st_bear = close[i] < st_value

        center_rising = wc > wave_center[i - bias_slope]
        center_falling = wc < wave_center[i - bias_slope]
        slow_rising = ws > wave_slow[i - bias_slope]
        slow_falling = ws < wave_slow[i - bias_slope]

        use_st = cfg["use_supertrend_bias"]
        bull_evidence = bool(center_rising and slow_rising and close[i] > wc and (not use_st or st_bull))
        bear_evidence = bool(center_falling and slow_falling and close[i] < wc and (not use_st or st_bear))
        bull_evidence_hist.append(bull_evidence)
        bear_evidence_hist.append(bear_evidence)

        bull_confirmed = bull_evidence and sum(bull_evidence_hist[-confirm:]) == confirm and len(bull_evidence_hist) >= confirm
        bear_confirmed = bear_evidence and sum(bear_evidence_hist[-confirm:]) == confirm and len(bear_evidence_hist) >= confirm

        # CompoundValue: latch, do not reset to 0.
        if bull_confirmed:
            bias_state = 1
        elif bear_confirmed:
            bias_state = -1
        bull_bias = bias_state == 1
        bear_bias = bias_state == -1

        vwap_value = vwap_series[i]
        vwap_call_ok = (not cfg["use_vwap_filter"]) or (not is_intraday) or close[i] > vwap_value
        vwap_put_ok = (not cfg["use_vwap_filter"]) or (not is_intraday) or close[i] < vwap_value

        # RVOL: the study's two-offset construction.
        #   rvolLive      = volume / Average(volume[1], n)     <- only on the LAST bar
        #   rvolCompleted = volume[1] / Average(volume[2], n)  <- every other bar
        # `is_last` is about the CHART's last bar, not the loop's last iteration: when
        # forming=False the final bar is excluded, so the last bar we visit is still a
        # completed bar and must use the completed offset.
        is_chart_last = (i == n - 1)
        if is_chart_last and forming:
            avg_live = avg_vol_live[i]
            rvol_display = (volume[i] / avg_live) if avg_live else 0.0
        else:
            # volume[i] compared against the n-bar average ENDING at i-1
            # (ThinkScript's Average(volume[2], n) evaluated on bar i).
            if i >= 1:
                window = volume[max(0, i - vol_len):i]
                avg_comp = (sum(window) / len(window)) if window else None
            else:
                avg_comp = None
            rvol_display = (volume[i] / avg_comp) if avg_comp else 0.0

        volume_ok = (not cfg["use_volume_filter"]) or rvol_display >= eff_min
        volume_strong = (not cfg["use_volume_filter"]) or rvol_display >= eff_strong

        local_high = max(high[i - trigger_len:i]) if i >= trigger_len else None
        local_low = min(low[i - trigger_len:i]) if i >= trigger_len else None
        call_trigger = (local_high + tick * buffer_ticks) if local_high is not None else None
        put_trigger = (local_low - tick * buffer_ticks) if local_low is not None else None

        breaks_up = call_trigger is not None and close[i] >= call_trigger
        breaks_down = put_trigger is not None and close[i] <= put_trigger
        bull_candle = close[i] > open_[i] and close[i] > close[i - 1]
        bear_candle = close[i] < open_[i] and close[i] < close[i - 1]

        call_watch = bull_build and vwap_call_ok
        put_watch = bear_build and vwap_put_ok
        bull_bounce = bear_bias and bull_build
        bear_pullback = bull_bias and bear_build

        call_ready = bull_regime and close[i] > wh and vwap_call_ok and volume_ok
        put_ready = bear_regime and close[i] < wlo and vwap_put_ok and volume_ok

        # Two independent arms, verbatim.
        cross_up = wh is not None and wave_high[i - 1] is not None and close[i] > wh and close[i - 1] <= wave_high[i - 1]
        cross_down = wlo is not None and wave_low[i - 1] is not None and close[i] < wlo and close[i - 1] >= wave_low[i - 1]
        call_active = bool(call_ready and bull_candle and (breaks_up or cross_up))
        put_active = bool(put_ready and bear_candle and (breaks_down or cross_down))

        call_candidate = bool(call_active and not prev_call_active)     # sessionOK assumed true
        put_candidate = bool(put_active and not prev_put_active)

        call_strong = bool(call_ready and volume_strong)
        put_strong = bool(put_ready and volume_strong)

        call_exit_base = bool(close[i] < wc or (cfg["use_vwap_filter"] and is_intraday and close[i] < vwap_value) or bear_stack)
        put_exit_base = bool(close[i] > wc or (cfg["use_vwap_filter"] and is_intraday and close[i] > vwap_value) or bull_stack)

        atr_value = atr_series[i]
        # CompoundValue direction latch.
        if trade_direction == 0 and call_candidate:
            trade_direction, trade_entry, trade_atr = 1, close[i], atr_value
        elif trade_direction == 0 and put_candidate:
            trade_direction, trade_entry, trade_atr = -1, close[i], atr_value
        elif trade_direction == 1 and call_exit_base:
            trade_direction = 0
        elif trade_direction == -1 and put_exit_base:
            trade_direction = 0

        signal_long = trade_direction == 1 and call_candidate
        signal_short = trade_direction == -1 and put_candidate

        mult = cfg["atr_stop_multiplier"]
        active_stop = active_t1 = active_t2 = None
        if trade_entry is not None and trade_atr is not None:
            if trade_direction == 1:
                active_stop = trade_entry - trade_atr * mult
                active_t1 = trade_entry + trade_atr * mult * cfg["target1_r"]
                active_t2 = trade_entry + trade_atr * mult * cfg["target2_r"]
            elif trade_direction == -1:
                active_stop = trade_entry + trade_atr * mult
                active_t1 = trade_entry - trade_atr * mult * cfg["target1_r"]
                active_t2 = trade_entry - trade_atr * mult * cfg["target2_r"]

        # Price-colour cascade, in the study's order.
        if call_active:
            price_state = "CALL_ACTIVE"
        elif put_active:
            price_state = "PUT_ACTIVE"
        elif call_strong:
            price_state = "CALL_READY"
        elif put_strong:
            price_state = "PUT_READY"
        elif call_watch:
            price_state = "CALL_BUILD"
        elif put_watch:
            price_state = "PUT_BUILD"
        else:
            price_state = "NEUTRAL"

        if bull_bias:
            bias_label = "BULL"
        elif bear_bias:
            bias_label = "BEAR"
        else:
            bias_label = "SIDE"

        if trade_direction == 1:
            setup_label = "LONG"
        elif trade_direction == -1:
            setup_label = "SHORT"
        elif call_ready:
            setup_label = "READY_LONG"
        elif put_ready:
            setup_label = "READY_SHORT"
        elif bull_bounce:
            setup_label = "BOUNCE"
        elif bear_pullback:
            setup_label = "PULLBACK"
        else:
            setup_label = "WAIT"

        out.append(MasterSnapshot(
            index=i, bar_time=times[i], completed=i < n - 1,
            wave_high=_r(wh), wave_center=_r(wc), wave_low=_r(wlo),
            wave_fast=_r(wf), wave_mid=_r(wm), wave_slow=_r(ws),
            bull_stack=bool(bull_stack), bear_stack=bool(bear_stack),
            bull_regime=bool(bull_regime), bear_regime=bool(bear_regime),
            bull_build=bool(bull_build), bear_build=bool(bear_build),
            rsi=_r(rsi_value), supertrend=_r(st_value), st_bull=bool(st_bull),
            bias_state=bias_state, bull_bias=bool(bull_bias), bear_bias=bool(bear_bias),
            vwap=_r(vwap_value), rvol_display=_r(rvol_display),
            volume_ok=bool(volume_ok), volume_strong=bool(volume_strong),
            call_trigger_price=_r(call_trigger), put_trigger_price=_r(put_trigger),
            call_watch=bool(call_watch), put_watch=bool(put_watch),
            bull_bounce=bool(bull_bounce), bear_pullback=bool(bear_pullback),
            call_ready=bool(call_ready), put_ready=bool(put_ready),
            call_active=bool(call_active), put_active=bool(put_active),
            call_signal=bool(signal_long), put_signal=bool(signal_short),
            trade_direction=trade_direction,
            trade_entry=_r(trade_entry), trade_atr=_r(trade_atr),
            active_stop=_r(active_stop), active_target1=_r(active_t1),
            active_target2=_r(active_t2),
            price_state=price_state, bias_label=bias_label, setup_label=setup_label,
            warmup_ok=True,
        ))
        prev_call_active, prev_put_active = call_active, put_active

    return out


def _r(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 6) if math.isfinite(number) else None


def _blank(index: int, stamp: str | None, completed: bool) -> MasterSnapshot:
    return MasterSnapshot(
        index=index, bar_time=stamp, completed=completed,
        wave_high=None, wave_center=None, wave_low=None, wave_fast=None, wave_mid=None,
        wave_slow=None, bull_stack=None, bear_stack=None, bull_regime=None, bear_regime=None,
        bull_build=None, bear_build=None, rsi=None, supertrend=None, st_bull=None,
        bias_state=None, bull_bias=None, bear_bias=None, vwap=None, rvol_display=None,
        volume_ok=None, volume_strong=None, call_trigger_price=None, put_trigger_price=None,
        call_watch=None, put_watch=None, bull_bounce=None, bear_pullback=None,
        call_ready=None, put_ready=None, call_active=None, put_active=None,
        call_signal=None, put_signal=None, trade_direction=None, trade_entry=None,
        trade_atr=None, active_stop=None, active_target1=None, active_target2=None,
        price_state=None, bias_label=None, setup_label=None, warmup_ok=False,
    )


def latest(bars: Sequence[dict], config: dict[str, Any] | None = None,
           *, forming: bool = False, minutes: int = 1440) -> MasterSnapshot | None:
    series = evaluate_series(bars, config, forming=forming, minutes=minutes)
    return series[-1] if series else None
