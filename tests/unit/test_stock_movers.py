from datetime import datetime, timezone
import pandas as pd
import pytest
from qx.market.stock_movers import stock_movers, _schedule


def test_cached_stock_universe_preserves_missing_coverage(tmp_path):
    cache = tmp_path / "bars"
    cache.mkdir()
    pd.DataFrame({"symbol": ["AAA", "BBB"]}).to_csv(tmp_path / "sp500_symbols.csv", index=False)
    now = datetime.now(timezone.utc)
    schedule = _schedule(now.date())
    dates = schedule.loc[schedule.market_close + pd.Timedelta(minutes=30) <= pd.Timestamp(now)].index[-22:] + pd.Timedelta(hours=1)
    for symbol, last in [("SPY", 98), ("AAA", 99)]:
        pd.DataFrame({"open":100., "high":101., "low":97., "close":[100.]*21+[last], "volume":1000}, index=dates).to_csv(cache / f"{symbol}_2y.csv")
    result = stock_movers(cache, "sp500")
    assert result["universe"] == 2
    assert result["rows"][0]["return_1d"] == pytest.approx(-.01)
    assert result["rows"][0]["excess_1d"] == pytest.approx(.01)
    assert "return_1d" not in result["rows"][1]
    with pytest.raises(ValueError):
        stock_movers(cache, "../../other")
