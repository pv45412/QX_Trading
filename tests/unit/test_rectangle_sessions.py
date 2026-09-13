from datetime import datetime, timezone

import pandas as pd
import pandas_market_calendars as mcal
import pytest

from qx.core.engine import ScannerEngine
from tests.unit.test_rectangle import _clean_rectangle_bars

NOW = datetime(2026, 9, 10, 14, tzinfo=timezone.utc)


def history():
    bars = _clean_rectangle_bars()
    sessions = mcal.get_calendar("NYSE").schedule(start_date="2025-01-01", end_date="2026-09-09").index
    bars.index = sessions[-len(bars):]
    return bars


class Provider:
    def __init__(self, bars):
        self.bars = bars

    def get_daily_bars(self, request):
        return self.bars.copy()


def test_live_scan_ignores_unfinished_bar(tmp_path, monkeypatch):
    monkeypatch.setattr("qx.core.engine.SCANNER_FAILURE_CACHE", tmp_path / "failures.csv")
    bars = history()
    baseline = ScannerEngine(Provider(bars), as_of=NOW).scan_symbols(["TEST"])
    partial = bars.tail(1).copy()
    partial.index = pd.DatetimeIndex(["2026-09-10"])
    partial["close"] *= 2
    result = ScannerEngine(Provider(pd.concat([bars, partial])), as_of=NOW).scan_symbols(["TEST"])
    assert result.candidates[0].model_dump() == baseline.candidates[0].model_dump()


@pytest.mark.parametrize("mode", ["stale", "missing"])
def test_live_scan_rejects_incomplete_sessions(mode):
    bars = history()
    bars = bars.iloc[:-1] if mode == "stale" else bars.drop(bars.index[-5])
    result = ScannerEngine(Provider(bars), as_of=NOW).scan_symbols_sequential(["TEST"])
    assert result.failed_symbols == 1
    assert not result.candidates


def test_live_scan_requires_aware_clock():
    with pytest.raises(ValueError, match="timezone"):
        ScannerEngine(Provider(history()), as_of=datetime(2026, 9, 10))
