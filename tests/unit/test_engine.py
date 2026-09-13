from pathlib import Path

import pandas as pd

from qx.core.engine import ScannerEngine
from qx.core.engine import _cacheable_error, _read_failure_cache, _write_failure_cache
from qx.models.market import BarDataRequest
from qx.storage.feature_cache import SQLiteFeatureCache
from tests.unit.test_rectangle import _clean_rectangle_bars


class MixedProvider:
    requests: list[BarDataRequest]

    def __init__(self) -> None:
        self.requests = []

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        self.requests.append(request)
        if request.symbol == "BAD":
            raise ValueError("missing data")
        return _clean_rectangle_bars()


class BenchmarkProvider:
    requests: list[BarDataRequest]

    def __init__(self, *, fail_benchmark: bool = False) -> None:
        self.requests = []
        self.fail_benchmark = fail_benchmark

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        self.requests.append(request)
        if request.symbol == "SPY":
            if self.fail_benchmark:
                raise ValueError("benchmark unavailable")
            return _flat_benchmark_bars()
        return _clean_rectangle_bars()


def test_engine_records_symbol_errors_without_stopping_scan() -> None:
    result = ScannerEngine(MixedProvider()).scan_symbols(["GOOD", "BAD"])

    assert result.total_symbols == 2
    assert len(result.candidates) == 1
    assert result.failed_symbols == 1
    assert result.errors[0].symbol == "BAD"


def test_engine_fetches_enough_history_for_200_bar_rules() -> None:
    provider = MixedProvider()

    ScannerEngine(provider).scan_symbols(["GOOD"], period="1y")

    assert all(request.period == "2y" for request in provider.requests)


def test_engine_labels_relative_strength_against_spy() -> None:
    provider = BenchmarkProvider()

    result = ScannerEngine(provider).scan_symbols(["GOOD"], period="2y", max_workers=1)

    assert result.candidates[0].metrics.rs_status == "Leading"


def test_engine_keeps_relative_strength_placeholder_when_benchmark_unavailable() -> None:
    provider = BenchmarkProvider(fail_benchmark=True)

    result = ScannerEngine(provider).scan_symbols(["GOOD"], period="2y", max_workers=1)

    assert result.candidates[0].metrics.rs_status == "Not checked"


def test_engine_reuses_feature_cache(tmp_path: Path) -> None:
    provider = MixedProvider()
    cache = SQLiteFeatureCache(tmp_path / "features.db")
    engine = ScannerEngine(provider, feature_cache=cache)

    first = engine.scan_symbols(["GOOD"], period="2y")
    second = engine.scan_symbols(["GOOD"], period="2y")

    assert first.candidates[0].model_dump() == second.candidates[0].model_dump()
    assert cache.count() == 1
    assert len(provider.requests) == 4


def test_engine_enriches_cached_candidate_with_relative_strength(tmp_path: Path) -> None:
    provider = BenchmarkProvider()
    cache = SQLiteFeatureCache(tmp_path / "features.db")
    engine = ScannerEngine(provider, feature_cache=cache)

    first = engine.scan_symbols(["GOOD"], period="2y", max_workers=1)
    second = engine.scan_symbols(["GOOD"], period="2y", max_workers=1)

    assert first.candidates[0].metrics.rs_status == "Leading"
    assert second.candidates[0].metrics.rs_status == "Leading"
    assert cache.count() == 1


def test_scanner_failure_cache_round_trips_by_period(tmp_path: Path) -> None:
    path = tmp_path / "scanner_failures.csv"

    _write_failure_cache("2y", {"DEAD": "No price data"}, path=path)
    _write_failure_cache("1y", {"OTHER": "No Schwab price history"}, path=path)

    assert _read_failure_cache("2y", path=path) == {"DEAD": "No price data"}
    assert _read_failure_cache("1y", path=path) == {"OTHER": "No Schwab price history"}


def test_scanner_uses_cached_failures_without_fetching(tmp_path: Path, monkeypatch) -> None:
    failure_path = tmp_path / "scanner_failures.csv"
    monkeypatch.setattr("qx.core.engine.SCANNER_FAILURE_CACHE", failure_path)
    provider = MixedProvider()
    engine = ScannerEngine(provider)
    _write_failure_cache("2y", {"BAD": "No price data"}, path=engine.failure_cache_path)

    result = engine.scan_symbols(["BAD"], period="2y")

    assert result.failed_symbols == 1
    assert result.errors[0].symbol == "BAD"
    assert provider.requests == []


def test_cacheable_error_only_caches_stable_data_failures() -> None:
    assert _cacheable_error("No price data returned by yfinance for BAD")
    assert _cacheable_error("No Schwab price history returned for BAD")
    assert not _cacheable_error("database is locked")


def _flat_benchmark_bars() -> pd.DataFrame:
    rows = [
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 10_000_000.0,
        }
        for _ in range(len(_clean_rectangle_bars()))
    ]
    return pd.DataFrame(rows)
