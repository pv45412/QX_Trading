from datetime import datetime, timezone
from types import SimpleNamespace
import pandas as pd
import pandas_market_calendars as mcal
from qx.data.stock_refresh import StockRefresh


def test_stock_refresh_atomic_and_membership_bound(tmp_path):
    membership = tmp_path / "sp100_symbols.csv"
    membership.write_text("symbol\nAAA\nBBB\n")
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-06-01", end_date="2026-09-09").index
    frame = pd.DataFrame({"open":100., "high":101., "low":99., "close":100., "volume":1e6}, index=dates)
    provider = SimpleNamespace(get_daily_bars=lambda request: frame.copy())
    refresh = StockRefresh(tmp_path / "bars", lambda: provider, "sp100")
    assert refresh.reserve()
    assert not refresh.reserve()
    now = datetime(2026, 9, 9, 22, tzinfo=timezone.utc)
    refresh.run(now)
    assert refresh.status()["status"] == "succeeded"
    published = refresh.active_cache()
    assert len(list(published.glob("*_1y.csv"))) == 3
    assert (published / "symbols.csv").read_bytes() == membership.read_bytes()
    assert not (tmp_path / "bars").exists()
    provider.get_daily_bars = lambda request: frame.iloc[:-1].copy()
    assert refresh.reserve()
    refresh.run(now)
    assert refresh.status()["status"] == "failed"
    assert refresh.active_cache() == published


def test_membership_change_prevents_publication(tmp_path):
    membership = tmp_path / "sp100_symbols.csv"
    membership.write_text("symbol\nAAA\n")
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-06-01", end_date="2026-09-09").index
    frame = pd.DataFrame({"open":100., "high":101., "low":99., "close":100., "volume":1e6}, index=dates)
    def get(request):
        membership.write_text("symbol\nBBB\n")
        return frame.copy()
    refresh = StockRefresh(tmp_path / "bars", lambda: SimpleNamespace(get_daily_bars=get), "sp100")
    refresh.reserve()
    refresh.run(datetime(2026, 9, 9, 22, tzinfo=timezone.utc))
    assert refresh.status()["status"] == "failed"
    assert refresh.active_cache() == tmp_path / "bars"
