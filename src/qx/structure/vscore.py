"""Anchored VScore & Pressure Oscillator Engine.

Translates TOS QX_ANCHORED_VSCORE and QX_VSCORE_PRESSURE_OSCILLATOR into Python:
- Volume-Weighted Z-Score: VScore = (Price - AVWAP) / StdDev(AVWAP)
- Session Auto-Anchors (Globex 18:00 vs RTH 09:30)
- Momentum Regimes (Selling Easing, Buying Easing, Bull Control, Extreme Stretch)
"""

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field


class VScoreResult(BaseModel):
    vscore: float
    avwap: float
    std_dev: float
    regime: str  # "EXTREME_BULL", "BULL_CONTROL", "NEUTRAL", "BEAR_CONTROL", "EXTREME_BEAR"
    momentum_state: str  # "SELLING_EASING", "BUYING_EASING", "BUYERS_STRENGTHENING", "SELLERS_STRENGTHENING", "STABLE"
    rvol: float
    participation_state: str  # "LOW", "NORMAL", "CONFIRMED", "HIGH"


def calculate_anchored_vscore(bars: pd.DataFrame, session_anchor_idx: int = 0) -> VScoreResult:
    """Calculate Anchored VScore & Pressure momentum state for an OHLCV DataFrame.

    :param bars: DataFrame containing 'high', 'low', 'close', 'volume'
    :param session_anchor_idx: Bar index where session AVWAP resets (default 0 / start of dataframe)
    """
    if len(bars) < 5:
        p = float(bars["close"].iloc[-1]) if len(bars) > 0 else 100.0
        return VScoreResult(
            vscore=0.0,
            avwap=p,
            std_dev=1.0,
            regime="NEUTRAL",
            momentum_state="STABLE",
            rvol=1.0,
            participation_state="NORMAL",
        )

    # Slice from session anchor index
    session_bars = bars.iloc[max(0, session_anchor_idx) :]
    h = session_bars["high"].to_numpy()
    l = session_bars["low"].to_numpy()
    c = session_bars["close"].to_numpy()
    v = session_bars["volume"].to_numpy()

    # Typical price
    tp = (h + l + c) / 3.0
    v_clean = np.where(np.isnan(v) | (v <= 0), 1.0, v)

    cum_vol = np.cumsum(v_clean)
    cum_pv = np.cumsum(tp * v_clean)
    cum_p2v = np.cumsum((tp**2) * v_clean)

    avwap_series = cum_pv / cum_vol
    var_series = np.maximum(0.0, (cum_p2v / cum_vol) - (avwap_series**2))
    std_series = np.sqrt(var_series)

    curr_p = float(c[-1])
    curr_avwap = float(avwap_series[-1])
    curr_std = float(std_series[-1]) if std_series[-1] > 1e-4 else 1.0

    raw_vscore = (curr_p - curr_avwap) / curr_std
    vscore = round(float(np.clip(raw_vscore, -4.0, 4.0)), 2)

    # Calculate prior vscore for slope
    if len(session_bars) >= 2:
        prior_p = float(c[-2])
        prior_avwap = float(avwap_series[-2])
        prior_std = float(std_series[-2]) if std_series[-2] > 1e-4 else 1.0
        prior_vscore = (prior_p - prior_avwap) / prior_std
    else:
        prior_vscore = vscore

    slope = vscore - prior_vscore
    rising = slope > 0

    # Participation RVOL
    lookback = min(20, len(bars))
    recent_vol = bars["volume"].iloc[-lookback:].to_numpy()
    avg_vol = np.mean(recent_vol[:-1]) if len(recent_vol) > 1 else np.mean(recent_vol)
    curr_vol = float(bars["volume"].iloc[-1])
    rvol = round(float(curr_vol / avg_vol), 2) if avg_vol > 0 else 1.0

    if rvol < 0.80:
        participation = "LOW"
    elif rvol < 1.30:
        participation = "NORMAL"
    elif rvol < 1.80:
        participation = "CONFIRMED"
    else:
        participation = "HIGH"

    # Regime Classification
    if vscore >= 2.0:
        regime = "EXTREME_BULL"
    elif vscore >= 0.75:
        regime = "BULL_CONTROL"
    elif vscore <= -2.0:
        regime = "EXTREME_BEAR"
    elif vscore <= -0.75:
        regime = "BEAR_CONTROL"
    else:
        regime = "NEUTRAL"

    # Momentum State
    if vscore < 0 and rising:
        momentum = "SELLING_EASING"
    elif vscore > 0 and not rising:
        momentum = "BUYING_EASING"
    elif vscore >= 0 and rising:
        momentum = "BUYERS_STRENGTHENING"
    elif vscore <= 0 and not rising:
        momentum = "SELLERS_STRENGTHENING"
    else:
        momentum = "STABLE"

    return VScoreResult(
        vscore=vscore,
        avwap=round(curr_avwap, 2),
        std_dev=round(curr_std, 2),
        regime=regime,
        momentum_state=momentum,
        rvol=rvol,
        participation_state=participation,
    )
