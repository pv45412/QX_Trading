from datetime import datetime, timezone

from qx.market.futures_snapshot import load_futures_context_snapshot, save_futures_context_snapshot
from qx.market.spx_dashboard import build_spx_dashboard
from tests.unit.test_spx_dashboard import StaticProvider, _bars


def test_futures_snapshot_round_trips_dashboard_and_request_metadata(tmp_path) -> None:
    symbols = ["SPY", "QQQ", "IWM", "ES=F", "NQ=F", "YM=F", "RTY=F", "ZN=F", "ZB=F", "DX-Y.NYB", "CL=F", "GC=F", "^VIX"]
    dashboard = build_spx_dashboard(StaticProvider({symbol: _bars(100.0, 0.1) for symbol in symbols}))
    path = tmp_path / "futures.json"
    saved = save_futures_context_snapshot(dashboard, path, period="6mo", requested_source="schwab", now=datetime(2026, 9, 12, tzinfo=timezone.utc))
    restored = load_futures_context_snapshot(path)

    assert restored == saved
    assert restored.dashboard.spy_close == dashboard.spy_close
    assert restored.dashboard.opening_gap.data_source == dashboard.opening_gap.data_source
