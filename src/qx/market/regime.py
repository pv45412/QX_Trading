from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

import pandas as pd

from qx.data.providers import MarketDataProvider
from qx.models.market import BarDataRequest
from qx.market.sessions import completed_mover_bars


@dataclass(frozen=True)
class MarketRegimeResult:
    label: str
    risk_level: str
    spy_close: float
    spy_sma50: float
    spy_sma200: float
    spy_return_20d: float
    spy_return_50d: float
    qqq_return_20d: float | None
    iwm_return_20d: float | None
    realized_vol_20d: float
    notes: list[str]

    @property
    def is_constructive(self) -> bool:
        return self.label in {"Risk On", "Constructive"}


def analyze_market_regime(
    provider: MarketDataProvider,
    *,
    period: str = "2y",
    spy_bars: pd.DataFrame | None = None,
    as_of: datetime | None = None,
) -> MarketRegimeResult:
    """Classify broad market conditions from liquid index ETFs."""
    spy = spy_bars if spy_bars is not None else provider.get_daily_bars(BarDataRequest(symbol="SPY", period=period))
    if as_of is not None:
        if not isinstance(spy.index, pd.DatetimeIndex):
            raise ValueError("SPY freshness requires dated bars")
        spy = completed_mover_bars(spy, as_of)
    qqq = _safe_bars(provider, "QQQ", period)
    iwm = _safe_bars(provider, "IWM", period)

    _validate_rows("SPY", spy, 220)
    spy_close = _last(spy["close"])
    spy_sma50 = _last(spy["close"].rolling(50).mean())
    spy_sma200 = _last(spy["close"].rolling(200).mean())
    spy_return_20d = _return_over_bars(spy, 20)
    spy_return_50d = _return_over_bars(spy, 50)
    qqq_return_20d = _aligned_return(qqq, spy, as_of)
    iwm_return_20d = _aligned_return(iwm, spy, as_of)
    realized_vol_20d = _realized_vol(spy, 20)

    above_50 = spy_close > spy_sma50
    above_200 = spy_close > spy_sma200
    qqq_leading = qqq_return_20d is not None and qqq_return_20d > spy_return_20d
    small_caps_confirm = iwm_return_20d is not None and iwm_return_20d > spy_return_20d * 0.5

    notes: list[str] = []
    if qqq_return_20d is None:
        notes.append("QQQ confirmation unavailable: missing, invalid or misaligned history.")
    if iwm_return_20d is None:
        notes.append("IWM confirmation unavailable: missing, invalid or misaligned history.")
    if above_50:
        notes.append("SPY is above the 50-day average.")
    else:
        notes.append("SPY is below the 50-day average.")
    if above_200:
        notes.append("SPY is above the 200-day average.")
    else:
        notes.append("SPY is below the 200-day average.")
    if qqq_leading:
        notes.append("QQQ is leading SPY over 20 days.")
    if iwm_return_20d is not None and not small_caps_confirm:
        notes.append("Small caps are not confirming broad risk appetite.")

    if above_50 and above_200 and spy_return_20d > 0 and qqq_leading:
        label = "Risk On"
        risk_level = "Low"
    elif above_200 and spy_return_20d >= -0.02:
        label = "Constructive"
        risk_level = "Medium"
    elif not above_200 or spy_return_20d < -0.05:
        label = "Risk Off"
        risk_level = "High"
    else:
        label = "Choppy"
        risk_level = "Medium"

    if realized_vol_20d > 0.25:
        risk_level = "High"
        notes.append("20-day realized volatility is elevated.")

    return MarketRegimeResult(
        label=label,
        risk_level=risk_level,
        spy_close=round(spy_close, 2),
        spy_sma50=round(spy_sma50, 2),
        spy_sma200=round(spy_sma200, 2),
        spy_return_20d=round(spy_return_20d, 4),
        spy_return_50d=round(spy_return_50d, 4),
        qqq_return_20d=round(qqq_return_20d, 4) if qqq_return_20d is not None else None,
        iwm_return_20d=round(iwm_return_20d, 4) if iwm_return_20d is not None else None,
        realized_vol_20d=round(realized_vol_20d, 4),
        notes=notes,
    )


def _aligned_return(bars: pd.DataFrame | None, spy: pd.DataFrame, as_of: datetime | None) -> float | None:
    if bars is None:
        return None
    try:
        if as_of is not None:
            if not isinstance(bars.index, pd.DatetimeIndex):
                return None
            bars = completed_mover_bars(bars, as_of)
        _validate_rows("Benchmark", bars, 21)
        if not bars.index[-21:].equals(spy.index[-21:]):
            return None
        return _return_over_bars(bars, 20)
    except (ValueError, TypeError, KeyError):
        return None


def market_regime_frame(result: MarketRegimeResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "regime": result.label,
                "risk": result.risk_level,
                "spy_close": result.spy_close,
                "spy_sma50": result.spy_sma50,
                "spy_sma200": result.spy_sma200,
                "spy_20d": result.spy_return_20d,
                "spy_50d": result.spy_return_50d,
                "qqq_20d": result.qqq_return_20d,
                "iwm_20d": result.iwm_return_20d,
                "realized_vol_20d": result.realized_vol_20d,
            }
        ]
    )


def _safe_bars(provider: MarketDataProvider, symbol: str, period: str) -> pd.DataFrame | None:
    try:
        return provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
    except Exception:
        return None


def _validate_rows(symbol: str, bars: pd.DataFrame, minimum: int) -> None:
    if len(bars) < minimum:
        raise ValueError(f"{symbol} needs at least {minimum} daily bars, got {len(bars)}")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing or bars.index.hasnans:
        raise ValueError(f"{symbol} history must have unique ascending indices")
    if "close" not in bars.columns:
        raise ValueError(f"{symbol} history requires close prices")
    closes = pd.to_numeric(bars["close"], errors="coerce")
    if not closes.map(lambda value: math.isfinite(value) and value > 0).all():
        raise ValueError(f"{symbol} close prices must be finite and positive")


def _last(series: pd.Series[float]) -> float:
    value = series.dropna().iloc[-1]
    return float(value)


def _return_over_bars(bars: pd.DataFrame, bars_back: int) -> float:
    if len(bars) <= bars_back:
        return 0.0
    current = float(bars["close"].iloc[-1])
    previous = float(bars["close"].iloc[-bars_back - 1])
    if previous <= 0:
        return 0.0
    return (current / previous) - 1.0


def _realized_vol(bars: pd.DataFrame, window: int) -> float:
    returns = bars["close"].pct_change().dropna().tail(window)
    if returns.empty:
        return 0.0
    return float(returns.std() * (252**0.5))
