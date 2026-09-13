import pandas as pd
import pytest

from qx.market.dashboard_metrics import metrics


def test_daily_return_and_excess_are_distinct():
    dates = pd.bdate_range("2026-01-01", periods=30)
    stock = pd.DataFrame({"close": [100.] * 29 + [99.]}, index=dates)
    spy = pd.DataFrame({"close": [100.] * 29 + [98.]}, index=dates)
    result = metrics(stock, spy)
    assert result["return_1d"] == pytest.approx(-0.01)
    assert result["excess_1d"] == pytest.approx(0.01)
