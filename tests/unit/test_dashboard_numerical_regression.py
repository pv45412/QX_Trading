import math
import random
from statistics import correlation

import pandas as pd
import pytest

from qx.market.dashboard_metrics import metrics


@pytest.mark.parametrize("seed", range(20))
def test_metrics_against_independent_scalar_calculations(seed):
    rng = random.Random(seed)
    dates = pd.bdate_range("2025-11-03", periods=100)
    prices = []
    for start in [100, 200, 80]:
        series = [float(start)]
        for _ in range(99):
            series.append(series[-1] * (1 + rng.uniform(-0.04, 0.045)))
        prices.append(series)
    sector, spy, qqq = prices
    frames = [pd.DataFrame({"close": p}, index=dates) for p in prices]
    result = metrics(frames[0], frames[1], frames[2])
    sr = [sector[i] / sector[i-1] - 1 for i in range(79, 100)]
    br = [spy[i] / spy[i-1] - 1 for i in range(79, 100)]
    qr = [qqq[i] / qqq[i-1] - 1 for i in range(79, 100)]
    ratios = [a / b for a, b in zip(sector, spy, strict=True)]
    assert result["rs_change"] == pytest.approx(ratios[-1] / ratios[-22] - 1)
    assert result["rs_days"] == sum(a > b for a, b in zip(sr, br, strict=True))
    down = sum(b < 0 for b in br)
    up = sum(a > 0 and b < 0 for a, b in zip(sr, br, strict=True))
    assert result["down_days"] == down
    assert result["up_days"] == up
    assert result["up_down"] == pytest.approx(up / down) if down else result["up_down"] is None
    assert result["corr_qqq"] == pytest.approx(correlation(sr, qr))
    prior = max(i for i, d in enumerate(dates) if (d.year, d.month) < (dates[-1].year, dates[-1].month))
    assert result["mtd"] == pytest.approx(sector[-1] / sector[prior] - 1)
    # Exhaustively enumerate peak/trough pairs, independently of cummax/argmin.
    drawdown, peak, trough = min((spy[j] / spy[i] - 1, i, j) for j in range(100) for i in range(j+1))
    assert result["correction"]["spy_return"] == pytest.approx(drawdown)
    assert result["correction_excess"] == pytest.approx(sector[trough] / sector[peak] - 1 - drawdown)
    high = max(ratios[-22:])
    assert result["days_off_high"] == next(i for i, value in enumerate(reversed(ratios[-22:])) if value == high)


@pytest.mark.parametrize("kind", ["duplicate", "reversed", "missing", "nan", "infinity", "negative"])
def test_corrupt_sector_data_never_produces_metrics(kind):
    frame = pd.DataFrame({"close": range(100, 140)}, index=pd.bdate_range("2026-01-01", periods=40))
    bad = frame.copy()
    if kind == "duplicate":
        bad.index = pd.DatetimeIndex([bad.index[0]] * 40)
    elif kind == "reversed":
        bad = bad.iloc[::-1]
    elif kind == "missing":
        bad = bad.drop(bad.index[-3])
    else:
        bad = bad.astype(float)
        bad.iloc[-1, 0] = {"nan": math.nan, "infinity": math.inf, "negative": -1}[kind]
    with pytest.raises(ValueError):
        metrics(bad, frame)
