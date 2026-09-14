"""Fair Value Gap (FVG) Detection Module."""

import pandas as pd
from pydantic import BaseModel


class FairValueGap(BaseModel):
    gap_type: str  # "BULLISH_FVG" or "BEARISH_FVG"
    top_price: float
    bottom_price: float
    bar_index: int


def detect_fair_value_gaps(
    high: pd.Series,
    low: pd.Series,
    min_gap_pct: float = 0.05,
) -> list[FairValueGap]:
    """Detect Fair Value Gaps (FVG) across 3-bar sequences.

    Bullish FVG: Low of Bar 3 > High of Bar 1
    Bearish FVG: High of Bar 3 < Low of Bar 1
    """
    fvgs: list[FairValueGap] = []
    if len(high) < 3:
        return fvgs

    h = high.to_numpy()
    l = low.to_numpy()

    for i in range(2, len(h)):
        # Bullish FVG
        if l[i] > h[i - 2]:
            gap_size = l[i] - h[i - 2]
            gap_pct = (gap_size / h[i - 2]) * 100.0
            if gap_pct >= min_gap_pct:
                fvgs.append(
                    FairValueGap(
                        gap_type="BULLISH_FVG",
                        top_price=round(float(l[i]), 2),
                        bottom_price=round(float(h[i - 2]), 2),
                        bar_index=i,
                    )
                )
        # Bearish FVG
        elif h[i] < l[i - 2]:
            gap_size = l[i - 2] - h[i]
            gap_pct = (gap_size / l[i - 2]) * 100.0
            if gap_pct >= min_gap_pct:
                fvgs.append(
                    FairValueGap(
                        gap_type="BEARISH_FVG",
                        top_price=round(float(l[i - 2]), 2),
                        bottom_price=round(float(h[i]), 2),
                        bar_index=i,
                    )
                )
    return fvgs
