from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pandas_market_calendars as mcal
import pytest

from qx.brokers.schwab import market_data, timing
from qx.data.cache import CachedMarketDataProvider, _write_cached_bars
from qx.market.ai_review import build_rs_evidence, inspect_rs_evidence, validate_rs_evidence
from qx.models.market import BarDataRequest, IntradayBarDataRequest


def candle(instant: str, price: float = 100.0) -> dict[str, float | int]:
    return {"datetime": int(pd.Timestamp(instant).timestamp() * 1000), "open": price,
            "high": price + 1, "low": price - 1, "close": price, "volume": 1_000_000}


@pytest.mark.parametrize("label,instant", [
    ("2026-01-09", "2026-01-09T06:00:00Z"),
    ("2026-03-06", "2026-03-06T06:00:00Z"),
    ("2026-03-09", "2026-03-09T05:00:00Z"),
    ("2026-10-30", "2026-10-30T05:00:00Z"),
    ("2026-11-02", "2026-11-02T06:00:00Z"),
    ("2026-09-08", "2026-09-09T00:30:00Z"),
])
def test_daily_label_uses_et_date_and_intraday_keeps_utc_instant(label, instant):
    for converter in (market_data._candles_frame, timing._candles_frame):
        daily = converter([candle(instant)], daily=True)
        intraday = converter([candle(instant)])
        assert daily.index[0] == pd.Timestamp(label)
        assert daily.index.tz is None
        assert intraday.index[0] == pd.Timestamp(instant)
        assert str(intraday.index.tz) == "UTC"
        assert daily.iloc[0].to_dict() == intraday.iloc[0].to_dict()


@pytest.mark.parametrize("host_offset", [-12, 0, 14])
def test_conversion_never_uses_computer_local_timezone(monkeypatch, host_offset):
    class HostDependentClock(datetime):
        @classmethod
        def fromtimestamp(cls, value, tz=None):
            if tz is None:
                return datetime.fromtimestamp(value, UTC).replace(tzinfo=None) + timedelta(hours=host_offset)
            return datetime.fromtimestamp(value, tz)

    monkeypatch.setattr(market_data, "datetime", HostDependentClock)
    result = market_data._candles_frame([candle("2026-09-09T00:30:00Z")], daily=True)
    assert result.index[0] == pd.Timestamp("2026-09-08")


@pytest.mark.parametrize("timestamp", [None, 0, -1, True, "1770000000000", float("nan"), float("inf"), 1770000000000.5, 10**100])
def test_invalid_epochs_fail_closed(timestamp):
    row = {**candle("2026-09-09T05:00:00Z"), "datetime": timestamp}
    with pytest.raises(ValueError, match="timestamp"):
        market_data._candles_frame([row], daily=True)


def test_invalid_record_order_and_duplicate_session_are_not_repaired():
    first, second = candle("2026-09-08T05:00:00Z"), candle("2026-09-09T05:00:00Z")
    for rows in ([None], [first, first], [second, first], [first, candle("2026-09-08T06:00:00Z")]):
        with pytest.raises(ValueError):
            market_data._candles_frame(rows, daily=True)


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def get(self, path, *, params):
        assert path == "/marketdata/v1/pricehistory"
        return {"candles": self.rows}


def test_daily_and_intraday_provider_paths_use_their_own_contract():
    rows = [candle("2026-09-09T05:00:00Z")]
    provider = market_data.SchwabMarketDataProvider(FakeClient(rows))
    assert provider.get_daily_bars(BarDataRequest(symbol="SPY")).index[0] == pd.Timestamp("2026-09-09")
    intraday = provider.get_intraday_bars(IntradayBarDataRequest(symbol="SPY"))
    assert intraday.index[0] == pd.Timestamp("2026-09-09T05:00:00Z")


def test_fall_back_hour_does_not_collapse_distinct_intraday_instants():
    rows = [candle("2026-11-01T05:30:00Z"), candle("2026-11-01T06:30:00Z")]
    bars = market_data._candles_frame(rows)
    assert bars.index.is_unique
    assert bars.index[1] - bars.index[0] == pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="same ET date"):
        market_data._candles_frame(rows, daily=True)


def test_newly_ingested_daily_bars_roundtrip_through_strict_ai_contract(tmp_path: Path, monkeypatch):
    class CaptureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 11, 14, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("qx.data.provenance.datetime", CaptureClock)
    dates = mcal.get_calendar("NYSE").schedule(start_date="2026-07-01", end_date="2026-09-10").index[-22:]
    rows = [candle(f"{day.date()}T05:00:00Z", 100 + index) for index, day in enumerate(dates)]
    provider = CachedMarketDataProvider(market_data.SchwabMarketDataProvider(FakeClient(rows)), cache_dir=tmp_path)
    for symbol in ("XLE", "SPY"):
        provider.get_daily_bars(BarDataRequest(symbol=symbol, period="1y"))
    now = datetime(2026, 9, 11, 15, tzinfo=UTC)
    evidence = build_rs_evidence("XLE", cache=tmp_path, now=now)
    validate_rs_evidence(evidence, now, symbol="XLE", require_live=True)
    assert evidence["facts"]["bar_date"] == "2026-09-10"
    assert evidence["facts"]["windows"]["XLE"]["dates"] == list(dates.strftime("%Y-%m-%d"))
    assert not evidence["facts"]["input_issues"]
    assert evidence["facts"]["sources"]["XLE"]["verified"] is True
    assert evidence["validation"]["live_eligible"] is True


def test_legacy_cache_is_not_normalized_or_recategorized_without_refresh(tmp_path: Path):
    rows = market_data._candles_frame([candle("2026-09-09T05:00:00Z")])
    rows.index = rows.index.tz_convert("America/New_York").tz_localize(None)
    provider = market_data.SchwabMarketDataProvider(FakeClient([]))
    path = tmp_path / "XLE_1y.csv"
    _write_cached_bars(path, rows, provider)
    original = path.read_bytes()
    cached = CachedMarketDataProvider(provider, cache_dir=tmp_path).get_daily_bars(BarDataRequest(symbol="XLE", period="1y"))
    assert cached.index[0] == pd.Timestamp("2026-09-09T01:00:00")
    assert path.read_bytes() == original
    evidence = inspect_rs_evidence("XLE", cache=tmp_path, now=datetime(2026, 9, 11, 15, tzinfo=UTC))
    assert evidence["validation"]["live_eligible"] is False
    assert any("XLE: missing or invalid raw cached dates/closes" in issue for issue in evidence["facts"]["input_issues"])
