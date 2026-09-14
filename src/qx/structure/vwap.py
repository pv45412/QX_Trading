"""Intraday VWAP & Standard Deviation Channels Engine."""

import pandas as pd
import numpy as np
from pydantic import BaseModel


class VWAPChannels(BaseModel):
    vwap: float
    plus_1sd: float
    plus_2sd: float
    minus_1sd: float
    minus_2sd: float


def calculate_vwap_channels(bars: pd.DataFrame) -> VWAPChannels | None:
    """Calculate Intraday Volume Weighted Average Price (VWAP) and SD Bands.

    :param bars: pd.DataFrame containing 'high', 'low', 'close', 'volume'
    """
    if len(bars) < 2 or "volume" not in bars.columns:
        if "close" in bars.columns and len(bars) > 0:
            c = float(bars["close"].iloc[-1])
            return VWAPChannels(
                vwap=round(c, 2),
                plus_1sd=round(c * 1.005, 2),
                plus_2sd=round(c * 1.010, 2),
                minus_1sd=round(c * 0.995, 2),
                minus_2sd=round(c * 0.990, 2),
            )
        return None

    typical_price = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    volume = bars["volume"].replace(0, np.nan).fillna(1.0)
    
    cumulative_tp_vol = (typical_price * volume).cumsum()
    cumulative_vol = volume.cumsum()
    vwap_series = cumulative_tp_vol / cumulative_vol

    # Standard Deviation of Typical Price from VWAP
    variance = ((typical_price - vwap_series) ** 2 * volume).cumsum() / cumulative_vol
    std_dev = np.sqrt(variance)

    latest_vwap = float(vwap_series.iloc[-1])
    latest_sd = float(std_dev.iloc[-1]) if not np.isnan(std_dev.iloc[-1]) else latest_vwap * 0.005

    return VWAPChannels(
        vwap=round(latest_vwap, 2),
        plus_1sd=round(latest_vwap + latest_sd, 2),
        plus_2sd=round(latest_vwap + (2.0 * latest_sd), 2),
        minus_1sd=round(latest_vwap - latest_sd, 2),
        minus_2sd=round(latest_vwap - (2.0 * latest_sd), 2),
    )
