import pandas as pd
import pytest
from qx.market.dashboard_metrics import metrics


def bars(values):
    return pd.DataFrame({'close': values}, index=pd.bdate_range('2026-01-01', periods=len(values)))


def test_constant_ratio_and_no_down_days():
    spy = bars(list(range(100, 130)))
    result = metrics(bars(list(range(200, 260, 2))), spy, spy, spy)
    assert result['rs_change'] == 0
    assert result['current_rs'] == 2
    assert result['days_off_high'] == 0
    assert result['up_down'] is None
    assert result['correction'] is None
    assert result['corr_qqq'] == pytest.approx(1)


def test_drawdown_window_and_defensive_performance():
    spy = bars([100] * 10 + [90] * 10 + [80] * 10)
    result = metrics(bars([100] * 30), spy)
    assert result['correction_excess'] == pytest.approx(.2)
    assert result['down_days'] == 2
    assert result['up_down'] == 0
    assert result['corr_dia'] is None


def test_mismatched_or_invalid_prices_rejected():
    spy = bars([100] * 30)
    changed = bars([100] * 30)
    changed.index = changed.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError):
        metrics(changed, spy)
    for bad in (0, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            metrics(bars([100] * 29 + [bad]), spy)


def test_missing_month_boundary_and_short_history():
    result = metrics(bars([100] * 22), bars([100] * 22))
    assert result['mtd'] is None
    with pytest.raises(ValueError):
        metrics(bars([100] * 21), bars([100] * 21))
