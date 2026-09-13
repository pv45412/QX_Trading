"""
QX Intraday Pattern Engine: VWAP, Standard Deviation Bands, and Opening Range Breakouts (ORB).
Tailored for Day Traders monitoring intraday momentum, VWAP retests, and ORB 5m/15m triggers.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IntradayBreakoutSnapshot:
    symbol: str
    last_price: float
    vwap: float
    vwap_upper_1std: float
    vwap_lower_1std: float
    vwap_upper_2std: float
    vwap_lower_2std: float
    orb_5m_high: float
    orb_5m_low: float
    orb_15m_high: float
    orb_15m_low: float
    orb_status: str  # 'Bullish ORB Breakout', 'Bearish ORB Breakdown', 'Inside Range'
    ema_stack_9_20_50: str  # 'Aligned Bullish', 'Aligned Bearish', 'Mixed'
    intraday_volume_surge_ratio: float


def analyze_intraday_setup(symbol: str, intraday_bars: pd.DataFrame) -> IntradayBreakoutSnapshot:
    """
    Analyzes intraday bar data (1-min or 5-min OHLCV) to calculate VWAP, SD Bands, ORB levels, and EMA stacks.
    intraday_bars expected columns: ['open', 'high', 'low', 'close', 'volume'] indexed by Timestamp.
    """
    if intraday_bars.empty or len(intraday_bars) < 3:
        return _empty_intraday_snapshot(symbol)

    df = intraday_bars.copy()
    last_price = float(df["close"].iloc[-1])

    # Calculate Volume Weighted Average Price (VWAP)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    vwap = cum_tp_vol / cum_vol.replace(0, float("nan"))
    
    # Calculate VWAP Standard Deviation Bands
    variance = ((typical_price - vwap) ** 2 * df["volume"]).cumsum() / cum_vol.replace(0, float("nan"))
    std_dev = np.sqrt(variance.clip(lower=0.0))

    last_vwap = float(vwap.iloc[-1])
    last_std = float(std_dev.iloc[-1]) if not np.isnan(std_dev.iloc[-1]) else 0.0

    vwap_u1 = last_vwap + last_std
    vwap_l1 = last_vwap - last_std
    vwap_u2 = last_vwap + (2.0 * last_std)
    vwap_l2 = last_vwap - (2.0 * last_std)

    # Opening Range (First 5 mins and 15 mins)
    orb_5m = df.head(5) if len(df) >= 5 else df
    orb_15m = df.head(15) if len(df) >= 15 else df

    orb_5m_high = float(orb_5m["high"].max())
    orb_5m_low = float(orb_5m["low"].min())
    orb_15m_high = float(orb_15m["high"].max())
    orb_15m_low = float(orb_15m["low"].min())

    # Determine ORB status
    if last_price > orb_15m_high:
        orb_status = "Bullish 15m ORB Breakout"
    elif last_price > orb_5m_high:
        orb_status = "Bullish 5m ORB Breakout"
    elif last_price < orb_15m_low:
        orb_status = "Bearish 15m ORB Breakdown"
    elif last_price < orb_5m_low:
        orb_status = "Bearish 5m ORB Breakdown"
    else:
        orb_status = "Inside Opening Range"

    # Intraday EMA stack (9, 20, 50)
    ema9 = float(df["close"].ewm(span=9, adjust=False).mean().iloc[-1]) if len(df) >= 9 else last_price
    ema20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1]) if len(df) >= 20 else last_price
    ema50 = float(df["close"].ewm(span=50, adjust=False).mean().iloc[-1]) if len(df) >= 50 else last_price

    if last_price > ema9 > ema20 > ema50:
        ema_stack = "Aligned Bullish (9 > 20 > 50)"
    elif last_price < ema9 < ema20 < ema50:
        ema_stack = "Aligned Bearish (9 < 20 < 50)"
    else:
        ema_stack = "Mixed / Chop"

    # Intraday Volume Surge Ratio (last 5 bars vs trailing 20 bars)
    recent_vol = float(df["volume"].tail(5).mean()) if len(df) >= 5 else float(df["volume"].mean())
    avg_vol = float(df["volume"].mean()) if not df["volume"].empty else 1.0
    volume_surge = recent_vol / avg_vol if avg_vol > 0 else 1.0

    return IntradayBreakoutSnapshot(
        symbol=symbol.upper(),
        last_price=round(last_price, 2),
        vwap=round(last_vwap, 2),
        vwap_upper_1std=round(vwap_u1, 2),
        vwap_lower_1std=round(vwap_l1, 2),
        vwap_upper_2std=round(vwap_u2, 2),
        vwap_lower_2std=round(vwap_l2, 2),
        orb_5m_high=round(orb_5m_high, 2),
        orb_5m_low=round(orb_5m_low, 2),
        orb_15m_high=round(orb_15m_high, 2),
        orb_15m_low=round(orb_15m_low, 2),
        orb_status=orb_status,
        ema_stack_9_20_50=ema_stack,
        intraday_volume_surge_ratio=round(volume_surge, 2),
    )


def _empty_intraday_snapshot(symbol: str) -> IntradayBreakoutSnapshot:
    return IntradayBreakoutSnapshot(
        symbol=symbol.upper(),
        last_price=0.0,
        vwap=0.0,
        vwap_upper_1std=0.0,
        vwap_lower_1std=0.0,
        vwap_upper_2std=0.0,
        vwap_lower_2std=0.0,
        orb_5m_high=0.0,
        orb_5m_low=0.0,
        orb_15m_high=0.0,
        orb_15m_low=0.0,
        orb_status="No Data",
        ema_stack_9_20_50="Unavailable",
        intraday_volume_surge_ratio=0.0,
    )
