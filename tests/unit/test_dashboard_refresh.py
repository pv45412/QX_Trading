from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pandas_market_calendars as mcal

from qx.data.dashboard_refresh import DashboardRefresh
from qx.interfaces.web import create_app
from fastapi import BackgroundTasks, HTTPException, Request
import pytest


def test_refresh_publishes_complete_generation_and_preserves_on_failure(tmp_path):
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-06-01", end_date="2026-09-09").index
    frame = pd.DataFrame({"open":100., "high":101., "low":99., "close":100., "volume":1e6}, index=dates)
    provider = SimpleNamespace(get_daily_bars=lambda request: frame)
    refresh = DashboardRefresh(tmp_path / "bars", lambda: provider)
    assert refresh.active_cache() == tmp_path / "bars"
    assert refresh.reserve()
    assert not refresh.reserve()
    refresh.run(datetime(2026, 9, 9, 22, tzinfo=timezone.utc))
    assert refresh.status()["status"] == "succeeded"
    published = refresh.active_cache()
    assert len(list(published.glob("*.csv"))) == 32
    provider.get_daily_bars = lambda request: frame.iloc[:-1]
    assert refresh.reserve()
    refresh.run(datetime(2026, 9, 9, 22, tzinfo=timezone.utc))
    assert refresh.status()["status"] == "failed"
    assert refresh.active_cache() == published
    assert refresh.status()["data_as_of"] == "2026-09-09"


def test_refresh_rejects_untrusted_posts(tmp_path):
    app = create_app(cache_dir=tmp_path / "bars")
    post = next(route.endpoint for route in app.routes if route.path == "/api/refresh" and "POST" in route.methods)
    for headers in [[], [(b'x-qx-refresh',b'1'), (b'sec-fetch-site',b'cross-site')]]:
        with pytest.raises(HTTPException) as error:
            post(Request({"type":"http", "headers":headers}), BackgroundTasks())
        assert error.value.status_code == 403
