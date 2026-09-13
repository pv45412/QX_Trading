from pathlib import Path

import pandas as pd

from qx.data.cache import CachedMarketDataProvider, _read_cached_bars
from qx.data.cache_status import (
    CacheCoverage,
    CacheHealth,
    assess_cache_health,
    cache_operational_actions,
    list_bar_cache,
    summarize_bar_cache,
    universe_cache_coverage,
)
from qx.models.market import BarDataRequest


def test_read_cached_bars_preserves_date_index(tmp_path: Path) -> None:
    cache_path = tmp_path / "AAPL_2y.csv"
    pd.DataFrame(
        {
            "Date": ["2026-01-02", "2026-01-05"],
            "open": [10.0, 10.5],
            "high": [11.0, 11.5],
            "low": [9.5, 10.0],
            "close": [10.8, 11.2],
            "volume": [1000, 1100],
        }
    ).to_csv(cache_path, index=False)

    bars = _read_cached_bars(cache_path)

    assert isinstance(bars.index, pd.DatetimeIndex)
    assert bars.index[0] == pd.Timestamp("2026-01-02")


def test_read_cached_bars_supports_legacy_cache_without_dates(tmp_path: Path) -> None:
    cache_path = tmp_path / "MSFT_2y.csv"
    pd.DataFrame(
        {
            "open": [10.0],
            "high": [11.0],
            "low": [9.5],
            "close": [10.8],
            "volume": [1000],
        }
    ).to_csv(cache_path, index=False)

    bars = _read_cached_bars(cache_path)

    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]


def test_cached_provider_refreshes_when_requested(tmp_path: Path) -> None:
    provider = _CountingProvider()
    cached_provider = CachedMarketDataProvider(provider, cache_dir=tmp_path, refresh=True)

    request = BarDataRequest(symbol="AAPL", period="2y")
    cached_provider.get_daily_bars(request)
    cached_provider.get_daily_bars(request)

    assert provider.calls == 2


def test_cached_provider_uses_existing_file_by_default(tmp_path: Path) -> None:
    provider = _CountingProvider()
    cached_provider = CachedMarketDataProvider(provider, cache_dir=tmp_path)

    request = BarDataRequest(symbol="AAPL", period="2y")
    cached_provider.get_daily_bars(request)
    cached_provider.get_daily_bars(request)

    assert provider.calls == 1


def test_cache_status_summarizes_bar_files(tmp_path: Path) -> None:
    _write_cache_file(tmp_path / "AAPL_2y.csv")
    _write_cache_file(tmp_path / "MSFT_2y.csv")
    _write_cache_file(tmp_path / "AAPL_5y.csv")

    summary = summarize_bar_cache(tmp_path)
    files = list_bar_cache(tmp_path)

    assert summary.total_files == 3
    assert summary.total_symbols == 2
    assert summary.periods == {"2y": 2, "5y": 1}
    assert files[0].rows == 1


def test_universe_cache_coverage_reports_missing_symbols(tmp_path: Path) -> None:
    _write_cache_file(tmp_path / "AAPL_2y.csv")

    coverage = universe_cache_coverage(["AAPL", "MSFT"], period="2y", cache_dir=tmp_path)

    assert coverage.total == 2
    assert coverage.cached == 1
    assert coverage.missing == 1
    assert coverage.missing_symbols == ["MSFT"]


def test_cache_file_availability_does_not_certify_dated_evidence(tmp_path: Path) -> None:
    _write_cache_file(tmp_path / "AAPL_2y.csv")
    _write_cache_file(tmp_path / "MSFT_2y.csv")

    health = assess_cache_health(["AAPL", "MSFT"], period="2y", cache_dir=tmp_path)

    assert not health.ready
    assert health.label == "Stale"
    assert health.coverage == 1.0


def test_cache_health_reports_partial_and_missing_states(tmp_path: Path) -> None:
    _write_cache_file(tmp_path / "AAPL_2y.csv")

    partial = assess_cache_health(["AAPL", "MSFT"], period="2y", cache_dir=tmp_path)
    missing = assess_cache_health(["AAPL"], period="5y", cache_dir=tmp_path)

    assert not partial.ready
    assert partial.label == "Incomplete"
    assert not missing.ready
    assert missing.label == "Missing"


def test_cache_operational_actions_cover_missing_stale_partial_and_ready() -> None:
    missing_health = CacheHealth(
        label="Missing",
        ready=False,
        coverage=0.0,
        latest_modified_at="",
        stale=True,
        message="No local bar cache exists for this period.",
    )
    stale_health = CacheHealth(
        label="Stale",
        ready=False,
        coverage=1.0,
        latest_modified_at="2026-06-01T11:48:51+00:00",
        stale=True,
        message="Cache exists, but it is older than the freshness threshold.",
    )
    partial_health = CacheHealth(
        label="Partial",
        ready=False,
        coverage=0.90,
        latest_modified_at="2026-06-03T11:48:51+00:00",
        stale=False,
        message="Cache is fresh but missing enough symbols to affect universe scans.",
    )
    ready_health = CacheHealth(
        label="Ready",
        ready=True,
        coverage=1.0,
        latest_modified_at="2026-06-03T11:48:51+00:00",
        stale=False,
        message="Cache is broad and fresh enough for fast local scanning.",
    )
    missing_coverage = CacheCoverage("2y", total=2, cached=0, missing=2, coverage=0.0, missing_symbols=["AAPL", "MSFT"])
    partial_coverage = CacheCoverage("2y", total=10, cached=9, missing=1, coverage=0.90, missing_symbols=["MSFT"])
    ready_coverage = CacheCoverage("2y", total=10, cached=10, missing=0, coverage=1.0, missing_symbols=[])

    assert "Warm the cache" in cache_operational_actions(health=missing_health, coverage=missing_coverage)[0]
    assert "forced cache refresh" in cache_operational_actions(health=stale_health, coverage=ready_coverage)[0]
    assert "Warm missing symbols" in cache_operational_actions(health=partial_health, coverage=partial_coverage)[0]
    assert "Cache is ready" in cache_operational_actions(health=ready_health, coverage=ready_coverage)[0]


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        self.calls += 1
        return pd.DataFrame(
            {
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "volume": [1000.0],
            },
            index=pd.DatetimeIndex(["2026-01-02"]),
        )


def _write_cache_file(path: Path) -> None:
    pd.DataFrame(
        {
            "Date": ["2026-01-02"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.5],
            "close": [10.5],
            "volume": [1000.0],
        }
    ).to_csv(path, index=False)
