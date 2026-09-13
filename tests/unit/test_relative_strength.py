import pandas as pd
import pytest

from qx.market.relative_strength import relative_strength


def bars():
    return pd.DataFrame({"close": [100.] * 26}, index=pd.bdate_range("2026-01-01", periods=26))


@pytest.mark.parametrize("last,prior,quadrant", [
    (110, 105, "LEADING"), (95, 90, "IMPROVING"),
    (105, 110, "WEAKENING"), (90, 95, "LAGGING"), (100, 100, "LAGGING"),
])
def test_exact_rs_momentum_and_quadrants(last, prior, quadrant):
    sector, benchmark = bars(), bars()
    sector.iloc[-1, 0] = last
    sector.iloc[-6, 0] = prior
    result = relative_strength(sector, benchmark)
    assert result.rs20 == pytest.approx(last / 100 - 1)
    assert result.momentum_5d == pytest.approx((last - prior) / 100)
    assert result.quadrant == quadrant
    assert result.status == "COMPUTED"


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), "bad"])
def test_invalid_prices_are_not_market_facts(bad):
    sector = bars().astype(object)
    sector.iloc[3, 0] = bad
    result = relative_strength(sector, bars())
    assert result.status == "INVALID_DATA"
    assert result.rs20 is None
    assert result.quadrant == "UNKNOWN"


def test_mismatched_sessions_are_rejected():
    sector = bars()
    sector.index = sector.index + pd.Timedelta(days=1)
    assert relative_strength(sector, bars()).status == "DATE_MISMATCH"


def test_short_history_is_not_zero():
    result = relative_strength(bars().iloc[:-1], bars())
    assert result.status == "INSUFFICIENT_HISTORY"
    assert result.momentum_5d is None


def test_duplicate_and_unsorted_dates_are_invalid():
    sector = bars()
    assert relative_strength(sector.iloc[::-1], bars()).status == "INVALID_DATA"
    sector.index = pd.DatetimeIndex([sector.index[0]] * 26)
    assert relative_strength(sector, bars()).status == "INVALID_DATA"
