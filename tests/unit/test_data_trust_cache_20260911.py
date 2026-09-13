import json
import os
from datetime import UTC, date, datetime
from hashlib import sha256

import pandas as pd
import pytest

from qx.data import cache_status
from qx.market.sessions import _schedule


NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


def _bars(end="2026-09-10"):
    labels = _schedule(date(2026, 9, 11)).loc[:end].index[-30:]
    return pd.DataFrame({"open": 10., "high": 12., "low": 9., "close": 11., "volume": 1000.},
                        index=pd.DatetimeIndex(labels, name="Date"))


def _write(root, symbol="AAPL", bars=None, verified=True):
    frame = _bars() if bars is None else bars
    path = root / f"{symbol}_2y.csv"
    frame.to_csv(path)
    if verified:
        metadata = {"sha256": sha256(path.read_bytes()).hexdigest(), "provenance": {
            "schema_version": 1, "actual_source": "schwab", "fallback_used": False,
            "retrieved_at": "2026-09-10T20:45:00+00:00", "last_bar_label": str(frame.index[-1]),
        }}
        path.with_suffix(".meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    return path


def _health(root, symbols=None, **kwargs):
    return cache_status.assess_cache_health(symbols or ["AAPL"], cache_dir=root, as_of=NOW, **kwargs)


def test_recent_one_file_cannot_mask_stale_requested_symbols(tmp_path):
    _write(tmp_path)
    _write(tmp_path, "MSFT", _bars("2026-09-08"))
    _write(tmp_path, "UNRELATED")
    health = _health(tmp_path, ["AAPL", "MSFT"])
    assert health.coverage == 1
    assert not health.ready and health.stale
    assert health.fresh_symbols == 1
    assert health.expected_session == "2026-09-10"
    assert [item.latest_eligible_session for item in health.symbol_evidence] == ["2026-09-10", "2026-09-08"]
    assert "File modification time is not bar freshness" in health.message


def test_old_mtime_is_not_stale_bar_evidence(tmp_path):
    path = _write(tmp_path)
    os.utime(path, (1, 1))
    health = _health(tmp_path, max_age_hours=0)
    assert health.ready and not health.stale
    assert health.source_verified_symbols == health.fresh_symbols == 1
    assert health.symbol_evidence[0].actual_source == "schwab"
    assert health.symbol_evidence[0].retrieved_at.endswith("+00:00")
    assert health.latest_modified_at.endswith("+00:00")


def test_requested_universe_coverage_does_not_read_csv(tmp_path, monkeypatch):
    _write(tmp_path, "BRK_B")
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: pytest.fail("Inventory parsed CSV"))
    coverage = cache_status.universe_cache_coverage(["brk.b", "BRK.B", "MSFT", " "], cache_dir=tmp_path)
    assert coverage.total == 2 and coverage.cached == 1
    assert coverage.missing_symbols == ["MSFT"]


@pytest.mark.parametrize("damage", ["empty", "no_dates", "missing_close", "bad_date", "nan", "infinite",
                                    "negative", "impossible_ohlc", "duplicate", "missing_session", "future"])
def test_malformed_or_missing_bars_never_ready(tmp_path, damage):
    bars = _bars()
    if damage == "empty":
        bars = bars.iloc[:0]
    elif damage == "no_dates":
        bars = bars.reset_index(drop=True)
    elif damage == "missing_close":
        bars = bars.drop(columns="close")
    elif damage == "bad_date":
        bars.index = [*map(str, bars.index[:-1]), "bad"]
    elif damage in {"nan", "infinite", "negative", "impossible_ohlc"}:
        bars.iloc[-1, bars.columns.get_loc("close")] = {
            "nan": float("nan"), "infinite": float("inf"), "negative": -1., "impossible_ohlc": 100.,
        }[damage]
    elif damage == "duplicate":
        bars = pd.concat([bars, bars.tail(1)])
    elif damage == "missing_session":
        bars = bars.drop(bars.index[-3])
    elif damage == "future":
        bars.loc[pd.Timestamp("2026-09-14")] = bars.iloc[-1]
    _write(tmp_path, bars=bars, verified=False)
    health = _health(tmp_path)
    assert health.coverage == 1
    assert not health.ready and health.stale
    assert health.symbol_evidence[0].detail


@pytest.mark.parametrize("metadata", [None, "broken", "wrong_digest", "naive_retrieval"])
def test_bar_freshness_is_separate_from_source_verification(tmp_path, metadata):
    path = _write(tmp_path, verified=metadata is not None)
    meta_path = path.with_suffix(".meta.json")
    if metadata == "broken":
        meta_path.write_text("{bad", encoding="utf-8")
    elif metadata in {"wrong_digest", "naive_retrieval"}:
        value = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata == "wrong_digest":
            value["sha256"] = "wrong"
        else:
            value["provenance"]["retrieved_at"] = "2026-09-10T20:45:00"
        meta_path.write_text(json.dumps(value), encoding="utf-8")
    health = _health(tmp_path)
    assert not health.ready and not health.stale
    assert health.fresh_symbols == 1 and health.source_verified_symbols == 0
    assert health.label == "Unverified"
    assert health.symbol_evidence[0].actual_source == "unknown"


def test_missing_requested_file_not_masked_by_unrelated_cache(tmp_path):
    _write(tmp_path, "UNRELATED")
    health = _health(tmp_path)
    assert health.label == "Missing" and health.latest_modified_at == ""
    assert health.symbol_evidence[0].status == "Missing"


def test_weekend_bar_is_not_reported_as_eligible(tmp_path):
    bars = _bars("2026-09-04")
    bars.loc[pd.Timestamp("2026-09-05")] = bars.iloc[-1]
    _write(tmp_path, bars=bars)
    health = _health(tmp_path)
    assert health.symbol_evidence[0].latest_eligible_session == "2026-09-04"
    assert health.symbol_evidence[0].status == "Invalid"


def test_completed_bar_assessment_rejects_naive_clock(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        cache_status.assess_cache_health(["AAPL"], cache_dir=tmp_path, as_of=datetime(2026, 9, 11))


def test_csv_inspection_reused_and_invalidated_by_bar_or_metadata_change(tmp_path, monkeypatch):
    path = _write(tmp_path)
    real_read = pd.read_csv
    calls = []

    def read(*args, **kwargs):
        calls.append(1)
        return real_read(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", read)
    assert _health(tmp_path).ready
    assert _health(tmp_path).ready
    cache_status.summarize_bar_cache(tmp_path)
    cache_status.list_bar_cache(tmp_path)
    assert len(calls) == 1
    path.with_suffix(".meta.json").write_text("{}", encoding="utf-8")
    assert not _health(tmp_path).ready
    assert len(calls) == 2
    _write(tmp_path, bars=_bars("2026-09-08"))
    assert _health(tmp_path).stale
    assert len(calls) == 3


@pytest.mark.parametrize(("instant", "expected"), [
    ("2026-09-11T20:29:00+00:00", "2026-09-10"),
    ("2026-09-11T20:30:00+00:00", "2026-09-11"),
    ("2026-09-07T21:00:00+00:00", "2026-09-04"),
    ("2026-11-27T18:29:00+00:00", "2026-11-25"),
    ("2026-11-27T18:30:00+00:00", "2026-11-27"),
])
def test_eligible_session_observes_buffer_holiday_and_early_close(instant, expected):
    assert cache_status.latest_completed_session(datetime.fromisoformat(instant)) == expected
