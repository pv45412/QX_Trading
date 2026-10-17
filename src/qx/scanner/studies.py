"""Deterministic studies and factor scoring for the QX scanner.

The scoring model mirrors `.agents/skills/smc-rules-engine/resources/qx_rules_engine_spec.md`:

    QX Score = 0.25*SMC + 0.20*Phases + 0.20*CVD_Absorption
             + 0.15*VScore + 0.10*RS_Rank + 0.10*OptionsFlow

    score >= 70 -> LONG / BUY CALL
    score <= 30 -> SHORT / BUY PUT
    otherwise   -> WAIT

Pure standard library so the same implementation serves the backend app and the
DSH plugin worker. No I/O here.
"""
from __future__ import annotations

import statistics

RULE_VERSION = "core_v1+qx_smc_1.0"

SCORE_WEIGHTS = {
    "SMC": 0.25,
    "Phases": 0.20,
    "CVD_Absorption": 0.20,
    "VScore": 0.15,
    "RS_Rank": 0.10,
    "OptionsFlow": 0.10,
}

LONG_THRESHOLD = 70.0
SHORT_THRESHOLD = 30.0

# The 11 SPDR sector ETFs — the declared sector universe.
SECTOR_ETFS: tuple[tuple[str, str], ...] = (
    ("XLK", "Technology"),
    ("XLF", "Financials"),
    ("XLV", "Health Care"),
    ("XLY", "Consumer Discretionary"),
    ("XLP", "Consumer Staples"),
    ("XLE", "Energy"),
    ("XLI", "Industrials"),
    ("XLB", "Materials"),
    ("XLU", "Utilities"),
    ("XLRE", "Real Estate"),
    ("XLC", "Communication Services"),
)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #

def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out: list[float] = []
    prev: float | None = None
    for index, value in enumerate(values):
        prev = value if prev is None else prev + k * (value - prev)
        out.append(prev)
    return out


def sma(values: list[float], period: int) -> float | None:
    return sum(values[-period:]) / period if len(values) >= period else None


def stdev(values: list[float]) -> float:
    return statistics.pstdev(values) if len(values) >= 2 else 0.0


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for index in range(1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def macd(closes: list[float]) -> dict | None:
    if len(closes) < 35:
        return None
    fast = ema(closes, 12)
    slow = ema(closes, 26)
    line = [a - b for a, b in zip(fast, slow)]
    signal = ema(line, 9)
    hist = line[-1] - signal[-1]
    prev_hist = line[-2] - signal[-2]
    return {"macd": line[-1], "signal": signal[-1], "hist": hist, "hist_rising": hist > prev_hist}


def atr(bars: list[dict], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    true_ranges = []
    for index in range(1, len(bars)):
        high, low, prev_close = bars[index]["high"], bars[index]["low"], bars[index - 1]["close"]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    value = sum(true_ranges[:period]) / period
    for index in range(period, len(true_ranges)):
        value = (value * (period - 1) + true_ranges[index]) / period
    return value


def anchored_vscore(bars: list[dict]) -> float | None:
    """Anchored VWAP sigma position mapped to 0..100."""
    window = bars[-60:] if len(bars) >= 10 else bars
    if not window:
        return None
    total_pv = 0.0
    total_volume = 0.0
    for bar in window:
        volume = bar["volume"] or 0.0
        total_pv += ((bar["high"] + bar["low"] + bar["close"]) / 3.0) * volume
        total_volume += volume
    if total_volume <= 0:
        return None
    avwap = total_pv / total_volume
    sd = stdev([bar["close"] for bar in window])
    if sd <= 0:
        return None
    z = (bars[-1]["close"] - avwap) / sd
    return 50.0 + clamp(z, -3.0, 3.0) * (50.0 / 3.0)


# --------------------------------------------------------------------------- #
# Factors (0..100 each)
# --------------------------------------------------------------------------- #

def factor_smc(bars: list[dict]) -> float:
    closes = [bar["close"] for bar in bars]
    if len(closes) < 40:
        return 50.0
    last = closes[-1]
    swing_high = max(bar["high"] for bar in bars[-21:-1])
    swing_low = min(bar["low"] for bar in bars[-21:-1])
    fast, slow = ema(closes, 20), ema(closes, 50)
    score = 50.0
    if last > swing_high:
        score += 25
    elif last < swing_low:
        score -= 25
    if last > max(closes[-6:-1]):
        score += 10
    if closes[-2] < closes[-1]:
        score += 8
    score += 7 if fast[-1] > slow[-1] else -7
    return clamp(score)


def factor_phases(bars: list[dict]) -> float:
    closes = [bar["close"] for bar in bars]
    if len(closes) < 50:
        return 50.0
    fast, slow = ema(closes, 20), ema(closes, 50)
    last = closes[-1]
    fast_slope = fast[-1] - fast[-6] if len(fast) >= 6 else 0.0
    slow_slope = slow[-1] - slow[-6] if len(slow) >= 6 else 0.0
    score = 50.0
    if slow_slope > 0 and last > slow[-1]:
        score += 30
    elif slow_slope < 0 and last < slow[-1]:
        score -= 30
    if fast_slope > 0 and last > fast[-1]:
        score += 12
    elif fast_slope < 0 and last < fast[-1]:
        score -= 12
    return clamp(score)


def factor_cvd(bars: list[dict]) -> float:
    if len(bars) < 20:
        return 50.0
    window = bars[-30:]
    cumulative = 0.0
    series: list[float] = []
    for bar in window:
        cumulative += (1.0 if bar["close"] >= bar["open"] else -1.0) * (bar["volume"] or 0.0)
        series.append(cumulative)
    sd = stdev(series) or 1.0
    z = series[-1] / sd if sd > 0 else 0.0
    last = bars[-1]
    span = last["high"] - last["low"]
    wick = 0.0 if span <= 0 else (span - abs(last["close"] - last["open"])) / span
    score = 50.0 + clamp(z, -2.5, 2.5) * 12.0
    if wick > 0.6:
        score += 10 if last["close"] >= last["open"] else -10
    return clamp(score)


def factor_vscore(bars: list[dict]) -> float:
    value = anchored_vscore(bars)
    return 50.0 if value is None else value


def factor_rs(bars: list[dict], benchmark: list[dict]) -> float:
    if len(bars) < 20 or len(benchmark) < 20:
        return 50.0

    def ret(series: list[dict], periods: int) -> float | None:
        if len(series) <= periods or series[-1 - periods]["close"] == 0:
            return None
        return series[-1]["close"] / series[-1 - periods]["close"] - 1.0

    score = 50.0
    for periods in (10, 60, 252):
        own, bench = ret(bars, periods), ret(benchmark, periods)
        if own is None or bench is None:
            continue
        score += clamp((own - bench) * 200.0, -8.0, 8.0)
    return clamp(score)


def factor_options_flow(quote: dict | None, bars: list[dict]) -> float:
    if not bars:
        return 50.0
    closes = [bar["close"] for bar in bars[-30:]]
    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]
    tilt = clamp((stdev(returns) - 0.01) * 400.0, -10.0, 10.0)
    return clamp(50.0 + tilt)


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #

def score_factors(
    bars: list[dict],
    benchmark_bars: list[dict],
    quote: dict | None = None,
) -> dict:
    """Return factors, aggregate score, signal, side and per-rule alerts."""
    factors = {
        "SMC": round(factor_smc(bars), 1),
        "Phases": round(factor_phases(bars), 1),
        "CVD_Absorption": round(factor_cvd(bars), 1),
        "VScore": round(factor_vscore(bars), 1),
        "RS_Rank": round(factor_rs(bars, benchmark_bars), 1),
        "OptionsFlow": round(factor_options_flow(quote, bars), 1),
    }
    score = round(sum(SCORE_WEIGHTS[name] * value for name, value in factors.items()), 1)
    if score >= LONG_THRESHOLD:
        signal, side = "LONG / BUY CALL", "LONG"
    elif score <= SHORT_THRESHOLD:
        signal, side = "SHORT / BUY PUT", "SHORT"
    else:
        signal, side = "WAIT", None

    alerts = []
    for name, value in factors.items():
        if value >= 70:
            alerts.append(f"{name} bullish ({value})")
        elif value <= 30:
            alerts.append(f"{name} bearish ({value})")
    if side:
        alerts.append(f"QX_SCORE {signal} ({score})")
    return {"factors": factors, "score": score, "signal": signal, "side": side, "alerts": alerts}
