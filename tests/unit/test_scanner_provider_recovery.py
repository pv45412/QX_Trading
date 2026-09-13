from qx.core.engine import ScannerEngine, _write_failure_cache, _read_failure_cache
from tests.unit.test_engine import MixedProvider
import pytest


def test_provider_scope_does_not_share_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("qx.core.engine.SCANNER_FAILURE_CACHE", tmp_path / "failures.csv")
    first = ScannerEngine(MixedProvider(), failure_cache_scope="source-one")
    second = ScannerEngine(MixedProvider(), failure_cache_scope="source-two")
    _write_failure_cache("2y", {"GOOD": "No price data"}, first.failure_cache_path)
    assert first.scan_symbols(["GOOD"]).failed_symbols == 1
    assert len(second.scan_symbols(["GOOD"]).candidates) == 1


def test_retry_recovers_and_clears_successful_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("qx.core.engine.SCANNER_FAILURE_CACHE", tmp_path / "failures.csv")
    engine = ScannerEngine(MixedProvider())
    _write_failure_cache("2y", {"GOOD": "No price data", "OTHER": "No price data"}, engine.failure_cache_path)
    assert len(engine.scan_symbols(["GOOD"], retry_failed=True).candidates) == 1
    assert _read_failure_cache("2y", engine.failure_cache_path) == {"OTHER": "No price data"}
    assert len(engine.scan_symbols(["GOOD"]).candidates) == 1


@pytest.mark.parametrize("operation", ["_write_failure_cache", "_remove_failure_entries"])
def test_cooldown_storage_failure_keeps_results(tmp_path, monkeypatch, caplog, operation):
    monkeypatch.setattr("qx.core.engine.SCANNER_FAILURE_CACHE", tmp_path / "failures.csv")
    def fail(*args):
        raise OSError("private storage detail")
    monkeypatch.setattr(f"qx.core.engine.{operation}", fail)
    result = ScannerEngine(MixedProvider()).scan_symbols(["GOOD", "BAD"], retry_failed=True)
    assert len(result.candidates) == 1
    assert result.failed_symbols == 1
    assert "scan results retained" in caplog.text
    assert "private storage detail" not in caplog.text
