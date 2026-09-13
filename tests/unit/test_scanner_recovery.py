from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from qx.core.engine import ScannerEngine, _read_failure_cache, _write_failure_cache
from tests.unit.test_engine import MixedProvider


@pytest.mark.parametrize("stamp", ["2000-01-01T00:00:00+00:00", "2999-01-01T00:00:00+00:00",
                                   "invalid", "2026-01-01T00:00:00"])
def test_invalid_or_expired_failure_is_retryable(tmp_path, stamp):
    path = tmp_path / "failures.csv"
    pd.DataFrame([dict(symbol="GOOD", period="2y", message="No price data", failed_at=stamp)]).to_csv(path, index=False)
    assert _read_failure_cache("2y", path) == {}


def test_legacy_failure_does_not_blacklist_symbol(tmp_path, monkeypatch):
    path = tmp_path / "failures.csv"
    path.write_text("symbol,period,message\nGOOD,2y,No price data\n")
    monkeypatch.setattr("qx.core.engine.SCANNER_FAILURE_CACHE", path)
    result = ScannerEngine(MixedProvider()).scan_symbols(["GOOD"])
    assert len(result.candidates) == 1


def test_writing_another_failure_preserves_original_age(tmp_path):
    path = tmp_path / "failures.csv"
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=50)).isoformat()
    pd.DataFrame([dict(symbol="OLD", period="2y", message="No price data", failed_at=stamp)]).to_csv(path, index=False)
    _write_failure_cache("2y", {"NEW": "No price data"}, path)
    frame = pd.read_csv(path).set_index("symbol")
    assert frame.loc["OLD", "failed_at"] == stamp


@pytest.mark.parametrize("method", ["scan_symbols", "scan_symbols_sequential"])
def test_duplicate_symbols_are_scanned_once(tmp_path, monkeypatch, method):
    monkeypatch.setattr("qx.core.engine.SCANNER_FAILURE_CACHE", tmp_path / "failures.csv")
    provider = MixedProvider()
    result = getattr(ScannerEngine(provider), method)(["GOOD", " good ", "", "GOOD"])
    assert result.total_symbols == 1
    assert len(result.candidates) == 1
    assert len([r for r in provider.requests if r.symbol == "GOOD"]) == 1
