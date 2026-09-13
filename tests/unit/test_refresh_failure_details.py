from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pandas_market_calendars as mcal
import pytest

from qx.data.dashboard_refresh import DashboardRefresh
from qx.data.stock_refresh import StockRefresh


NOW = datetime(2026, 9, 11, 21, tzinfo=timezone.utc)


def bars():
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-06-01", end_date=NOW.date()).index
    return pd.DataFrame({"open": 100., "high": 101., "low": 99., "close": 100., "volume": 1e6}, index=dates)


def coordinator(tmp_path, provider, stock):
    if stock:
        (tmp_path / "sp100_symbols.csv").write_text("symbol\nAAA\n")
        return StockRefresh(tmp_path / "bars", lambda: provider, "sp100")
    return DashboardRefresh(tmp_path / "bars", lambda: provider)


@pytest.mark.parametrize("stock", [False, True])
@pytest.mark.parametrize("first_symbol", [False, True])
@pytest.mark.parametrize("defect", ["stale", "gap", "too_short"])
def test_incomplete_sessions_explain_failure_without_replacing_publication(tmp_path, stock, first_symbol, defect):
    frame = bars()
    provider = SimpleNamespace(get_daily_bars=lambda request: frame.copy())
    refresh = coordinator(tmp_path, provider, stock)
    refresh.run(NOW)
    assert refresh.status()["status"] == "succeeded"
    pointer = (refresh.root / "current.json").read_bytes()
    failed_symbol = "SPY" if first_symbol else ("AAA" if stock else "QQQ")
    bad = frame.iloc[:-1] if defect == "stale" else frame.drop(frame.index[-10])
    if defect == "too_short":
        bad = frame.tail(21)
    requests = []

    def get(request):
        requests.append(request.symbol)
        return bad.copy() if request.symbol == failed_symbol else frame.copy()

    provider.get_daily_bars = get
    refresh.run(NOW)
    state = refresh.status()
    assert state["status"] == "failed"
    assert state["error_code"] == "incomplete_sessions"
    assert state["failed_symbol"] == failed_symbol
    assert state["expected_session"] == "2026-09-11"
    assert state["last_available_session"] == ("2026-09-10" if defect == "stale" else "2026-09-11")
    assert state["required_sessions"] == 22
    assert failed_symbol in state["error"]
    assert "22 completed NYSE sessions" in state["error"]
    assert "Previous data retained" in state["error"]
    assert requests[-1] == failed_symbol
    assert state["completed"] == (0 if first_symbol else 1)
    assert (refresh.root / "current.json").read_bytes() == pointer
    assert not (tmp_path / "bars").exists()
    provider.get_daily_bars = lambda request: frame.copy()
    assert refresh.reserve()
    assert "error_code" not in refresh.status()
    refresh.run(NOW)
    assert refresh.status()["status"] == "succeeded"
    assert "failed_symbol" not in refresh.status()


@pytest.mark.parametrize("stock", [False, True])
def test_provider_failure_never_exposes_exception_or_claims_stale_data(tmp_path, stock):
    def get(request):
        raise RuntimeError("Authorization: Bearer secret-token https://provider.invalid/?account=private")

    refresh = coordinator(tmp_path, SimpleNamespace(get_daily_bars=get), stock)
    refresh.run(NOW)
    state = refresh.status()
    assert state["status"] == "failed"
    assert "incomplete_sessions" not in str(state)
    assert "secret-token" not in str(state)
    assert "private" not in str(state)
    assert "expected_session" not in state
    assert not (refresh.root / "current.json").exists()
