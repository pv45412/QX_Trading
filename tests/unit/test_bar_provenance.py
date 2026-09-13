import json
from pathlib import Path

import pandas as pd
import pytest

from qx.data.cache import CachedMarketDataProvider
from qx.data.factory import FallbackMarketDataProvider
from qx.models.market import BarDataRequest, IntradayBarDataRequest


class Provider:
    def __init__(self, source: str, fail: bool = False):
        self.provider_name = source
        self.fail = fail

    def get_daily_bars(self, request):
        if self.fail:
            raise RuntimeError("Provider unavailable")
        return pd.DataFrame(
            {"open": [10.], "high": [11.], "low": [9.], "close": [10.], "volume": [100.]},
            index=pd.DatetimeIndex(["2026-01-02"]),
        )

    get_intraday_bars = get_daily_bars


@pytest.mark.parametrize("intraday", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_cache_preserves_actual_source(tmp_path: Path, fail: bool, intraday: bool):
    provider = FallbackMarketDataProvider(Provider("schwab", fail), Provider("yfinance"))
    cache = CachedMarketDataProvider(provider, tmp_path)
    request = (IntradayBarDataRequest(symbol="AAPL", period="5d", interval_minutes=5)
               if intraday else BarDataRequest(symbol="AAPL", period="2y"))
    get = cache.get_intraday_bars if intraday else cache.get_daily_bars
    live = get(request)
    saved = get(request)
    assert saved.attrs["provenance"] == live.attrs["provenance"]
    assert saved.attrs["provenance"]["actual_source"] == ("yfinance" if fail else "schwab")
    assert saved.attrs["provenance"]["fallback_used"] is fail
    assert saved.attrs["provenance"]["last_bar_label"] == "2026-01-02T00:00:00"


@pytest.mark.parametrize("damage", ["missing", "malformed", "changed_csv", "version"])
def test_unverified_cache_has_unknown_source(tmp_path: Path, damage: str):
    cache = CachedMarketDataProvider(Provider("schwab"), tmp_path)
    request = BarDataRequest(symbol="AAPL", period="2y")
    cache.get_daily_bars(request)
    metadata = tmp_path / "AAPL_2y.meta.json"
    if damage == "missing":
        metadata.unlink()
    elif damage == "malformed":
        metadata.write_text("[]", encoding="utf-8")
    elif damage == "changed_csv":
        path = tmp_path / "AAPL_2y.csv"
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        payload = json.loads(metadata.read_text())
        payload["provenance"]["schema_version"] = 2
        metadata.write_text(json.dumps(payload))
    assert cache.get_daily_bars(request).attrs["provenance"]["actual_source"] == "unknown"


def test_both_provider_failures_propagate():
    provider = FallbackMarketDataProvider(Provider("schwab", True), Provider("yfinance", True))
    with pytest.raises(RuntimeError):
        provider.get_daily_bars(BarDataRequest(symbol="AAPL", period="2y"))


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 1.0),
    ("actual_source", None), ("actual_source", " "), ("actual_source", []),
    ("retrieved_at", "yesterday"), ("retrieved_at", "2026-01-02T12:00:00"),
    ("retrieved_at", 123), ("fallback_used", "false"), ("fallback_used", 0),
    ("last_bar_label", "NaT"), ("last_bar_label", []),
])
def test_malformed_provenance_is_unknown_despite_valid_digest(tmp_path, field, value):
    cache = CachedMarketDataProvider(Provider("schwab"), tmp_path)
    request = BarDataRequest(symbol="AAPL", period="2y")
    cache.get_daily_bars(request)
    path = tmp_path / "AAPL_2y.meta.json"
    metadata = json.loads(path.read_text())
    metadata["provenance"][field] = value
    path.write_text(json.dumps(metadata))
    result = cache.get_daily_bars(request)
    assert result.attrs["provenance"]["actual_source"] == "unknown"
    assert result.attrs["provenance"]["retrieved_at"] is None


@pytest.mark.parametrize("field", [
    "schema_version", "actual_source", "retrieved_at", "fallback_used", "last_bar_label",
])
def test_incomplete_provenance_is_unknown(tmp_path, field):
    cache = CachedMarketDataProvider(Provider("schwab"), tmp_path)
    request = BarDataRequest(symbol="AAPL", period="2y")
    cache.get_daily_bars(request)
    path = tmp_path / "AAPL_2y.meta.json"
    metadata = json.loads(path.read_text())
    del metadata["provenance"][field]
    path.write_text(json.dumps(metadata))
    assert cache.get_daily_bars(request).attrs["provenance"]["actual_source"] == "unknown"
