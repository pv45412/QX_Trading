import pandas as pd

from qx.models.scan import WeeklyContext


def analyze_weekly_context(bars: pd.DataFrame) -> WeeklyContext:
    weekly = daily_to_weekly(bars)
    if len(weekly) < 30:
        raise ValueError(f"Need at least 30 weekly bars, got {len(weekly)}")

    current = weekly.iloc[-1]
    close = float(current["close"])
    sma10 = float(weekly["close"].tail(10).mean())
    sma30 = float(weekly["close"].tail(30).mean())
    avg_volume_10w = float(weekly["volume"].tail(10).mean())
    relative_volume_10w = float(current["volume"]) / avg_volume_10w if avg_volume_10w > 0 else 0.0
    distance_to_10w_pct = (close - sma10) / sma10 if sma10 > 0 else 0.0
    distance_to_30w_pct = (close - sma30) / sma30 if sma30 > 0 else 0.0
    is_above_10w = close > sma10
    is_above_30w = close > sma30
    is_10w_above_30w = sma10 > sma30
    is_extended = distance_to_10w_pct > 0.25 or distance_to_30w_pct > 0.60

    score = _weekly_score(
        is_above_10w=is_above_10w,
        is_above_30w=is_above_30w,
        is_10w_above_30w=is_10w_above_30w,
        is_extended=is_extended,
        distance_to_10w_pct=distance_to_10w_pct,
        relative_volume_10w=relative_volume_10w,
    )
    return WeeklyContext(
        status=_weekly_status(
            is_above_10w=is_above_10w,
            is_above_30w=is_above_30w,
            is_10w_above_30w=is_10w_above_30w,
            is_extended=is_extended,
        ),
        score=score,
        close=close,
        sma10=sma10,
        sma30=sma30,
        distance_to_10w_pct=distance_to_10w_pct,
        distance_to_30w_pct=distance_to_30w_pct,
        relative_volume_10w=relative_volume_10w,
        is_above_10w=is_above_10w,
        is_above_30w=is_above_30w,
        is_10w_above_30w=is_10w_above_30w,
        is_extended=is_extended,
    )


def daily_to_weekly(bars: pd.DataFrame) -> pd.DataFrame:
    dated_bars = bars.copy()
    if not isinstance(dated_bars.index, pd.DatetimeIndex):
        dated_bars.index = pd.bdate_range(
            end=pd.Timestamp("2026-05-29"),
            periods=len(dated_bars),
        )

    weekly = dated_bars.resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return weekly.dropna()


def _weekly_score(
    *,
    is_above_10w: bool,
    is_above_30w: bool,
    is_10w_above_30w: bool,
    is_extended: bool,
    distance_to_10w_pct: float,
    relative_volume_10w: float,
) -> float:
    score = 0.0
    score += 0.25 if is_above_10w else 0.0
    score += 0.25 if is_above_30w else 0.0
    score += 0.25 if is_10w_above_30w else 0.0
    score += 0.15 if relative_volume_10w >= 0.80 else 0.05
    if 0.0 <= distance_to_10w_pct <= 0.15:
        score += 0.10
    elif distance_to_10w_pct <= 0.25:
        score += 0.05
    if is_extended:
        score = min(score, 0.69)
    return max(0.0, min(1.0, score))


def _weekly_status(
    *,
    is_above_10w: bool,
    is_above_30w: bool,
    is_10w_above_30w: bool,
    is_extended: bool,
) -> str:
    if is_extended:
        return "Extended Leader"
    if is_above_10w and is_above_30w and is_10w_above_30w:
        return "Constructive Leader"
    if is_above_30w and is_10w_above_30w:
        return "Pullback In Uptrend"
    if not is_above_30w:
        return "Damaged"
    return "Neutral"
