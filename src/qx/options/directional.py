from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DirectionalSetupParameters:
    fast_ema: int = 21
    mid_ema: int = 50
    slow_ema: int = 200
    rsi_length: int = 14
    adx_length: int = 14
    min_adx: float = 20.0
    breakout_length: int = 20
    volume_length: int = 50
    min_rvol: float = 1.2
    max_iv_rank_for_buying: float = 55.0


@dataclass(frozen=True)
class DirectionalSetup:
    symbol: str
    bias: str
    setup_type: str
    normalized_score: float
    call_score: int
    put_score: int
    max_score: int
    rsi: float
    macd_value: float
    macd_average: float
    adx: float
    relative_volume: float
    iv_rank: float | None
    iv_available: bool
    notes: str


def analyze_directional_setup(
    symbol: str,
    bars: pd.DataFrame,
    params: DirectionalSetupParameters | None = None,
    *,
    iv_rank: float | None = None,
) -> DirectionalSetup:
    parameters = params or DirectionalSetupParameters()
    _validate_history(symbol, bars, parameters)

    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    volume = bars["volume"].astype(float)

    ema_fast = _ema(close, parameters.fast_ema)
    ema_mid = _ema(close, parameters.mid_ema)
    ema_slow = _ema(close, parameters.slow_ema)
    rsi = _rsi(close, parameters.rsi_length)
    macd_value, macd_average = _macd(close)
    adx = _adx(high, low, close, parameters.adx_length)
    avg_volume = volume.rolling(parameters.volume_length).mean()
    relative_volume = _safe_ratio(float(volume.iloc[-1]), float(avg_volume.iloc[-1]))

    current_close = float(close.iloc[-1])
    current_high = float(high.iloc[-1])
    current_low = float(low.iloc[-1])
    latest_fast = float(ema_fast.iloc[-1])
    latest_mid = float(ema_mid.iloc[-1])
    latest_slow = float(ema_slow.iloc[-1])
    latest_rsi = float(rsi.iloc[-1])
    latest_macd = float(macd_value.iloc[-1])
    latest_macd_avg = float(macd_average.iloc[-1])
    latest_adx = float(adx.iloc[-1])

    call_trend = current_close > latest_fast > latest_mid > latest_slow
    put_trend = current_close < latest_fast < latest_mid < latest_slow
    trend_strength = latest_adx >= parameters.min_adx
    volume_confirm = relative_volume >= parameters.min_rvol

    call_momentum = 50 < latest_rsi < 72 and latest_macd > latest_macd_avg
    put_momentum = 28 < latest_rsi < 50 and latest_macd < latest_macd_avg

    prior_high = float(high.shift(1).rolling(parameters.breakout_length).max().iloc[-1])
    prior_low = float(low.shift(1).rolling(parameters.breakout_length).min().iloc[-1])
    call_breakout = current_close > prior_high
    put_breakdown = current_close < prior_low

    call_pullback = (
        call_trend
        and current_low <= latest_fast
        and current_close > latest_fast
        and 45 <= latest_rsi <= 62
        and latest_macd >= latest_macd_avg
    )
    put_pullback = (
        put_trend
        and current_high >= latest_fast
        and current_close < latest_fast
        and 38 <= latest_rsi <= 55
        and latest_macd <= latest_macd_avg
    )

    iv_available = iv_rank is not None
    iv_good = bool(iv_rank is not None and iv_rank <= parameters.max_iv_rank_for_buying)
    max_score = 100 if iv_available else 85
    call_score = _score_direction(
        trend=call_trend,
        momentum=call_momentum,
        setup=call_breakout or call_pullback,
        volume_confirm=volume_confirm,
        trend_strength=trend_strength,
        iv_available=iv_available,
        iv_good=iv_good,
    )
    put_score = _score_direction(
        trend=put_trend,
        momentum=put_momentum,
        setup=put_breakdown or put_pullback,
        volume_confirm=volume_confirm,
        trend_strength=trend_strength,
        iv_available=iv_available,
        iv_good=iv_good,
    )
    selected_score = max(call_score, put_score)
    bias = _bias(call_score, put_score)
    setup_type = _setup_type(
        bias=bias,
        call_breakout=call_breakout,
        call_pullback=call_pullback,
        put_breakdown=put_breakdown,
        put_pullback=put_pullback,
    )

    return DirectionalSetup(
        symbol=symbol,
        bias=bias,
        setup_type=setup_type,
        normalized_score=round(selected_score / max_score, 3) if max_score else 0.0,
        call_score=call_score,
        put_score=put_score,
        max_score=max_score,
        rsi=round(latest_rsi, 2),
        macd_value=round(latest_macd, 4),
        macd_average=round(latest_macd_avg, 4),
        adx=round(latest_adx, 2),
        relative_volume=round(relative_volume, 3),
        iv_rank=round(iv_rank, 2) if iv_rank is not None else None,
        iv_available=iv_available,
        notes=_notes(volume_confirm, trend_strength, iv_available),
    )


def directional_setups_frame(setups: list[DirectionalSetup]) -> pd.DataFrame:
    return pd.DataFrame([setup.__dict__ for setup in setups])


def _validate_history(
    symbol: str,
    bars: pd.DataFrame,
    params: DirectionalSetupParameters,
) -> None:
    minimum_rows = max(params.slow_ema, params.volume_length, params.breakout_length) + 20
    if len(bars) < minimum_rows:
        raise ValueError(f"{symbol} needs at least {minimum_rows} daily bars, got {len(bars)}")


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - (100 / (1 + rs))).fillna(50)


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    value = _ema(close, 12) - _ema(close, 26)
    average = _ema(value, 9)
    return value, average


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    high_diff = high.diff()
    low_diff = -low.diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    average_true_range = true_range.ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / average_true_range
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / average_true_range
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    return dx.ewm(alpha=1 / length, adjust=False).mean().fillna(0)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _score_direction(
    *,
    trend: bool,
    momentum: bool,
    setup: bool,
    volume_confirm: bool,
    trend_strength: bool,
    iv_available: bool,
    iv_good: bool,
) -> int:
    return (
        (25 if trend else 0)
        + (20 if momentum else 0)
        + (20 if setup else 0)
        + (10 if volume_confirm else 0)
        + (10 if trend_strength else 0)
        + (10 if iv_good else 0)
        + (5 if iv_available else 0)
    )


def _bias(call_score: int, put_score: int) -> str:
    if call_score >= put_score + 10:
        return "Bullish"
    if put_score >= call_score + 10:
        return "Bearish"
    return "Neutral"


def _setup_type(
    *,
    bias: str,
    call_breakout: bool,
    call_pullback: bool,
    put_breakdown: bool,
    put_pullback: bool,
) -> str:
    if bias == "Bullish" and call_breakout:
        return "Call breakout"
    if bias == "Bullish" and call_pullback:
        return "Call pullback"
    if bias == "Bearish" and put_breakdown:
        return "Put breakdown"
    if bias == "Bearish" and put_pullback:
        return "Put pullback"
    return "No clean setup"


def _notes(volume_confirm: bool, trend_strength: bool, iv_available: bool) -> str:
    notes: list[str] = []
    notes.append("RVOL confirmed" if volume_confirm else "needs RVOL")
    notes.append("ADX trend" if trend_strength else "weak ADX")
    if not iv_available:
        notes.append("IV rank pending")
    return ", ".join(notes)
