from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from qx.market.sector_rotation import SectorRotationResult
from qx.market.sessions import _schedule
from qx.models.market import BarDataRequest
from qx.storage.sector_rotation import SQLiteSectorRotationRepository, StoredSectorRotationSnapshot
from qx.ui.pages import sector_rotation as page


class _Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 11, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(page, "datetime", _Clock)


def _evidence(day="2026-09-10"):
    return {"session_date": day, "benchmark": "SPY", "period": "1y", "symbols": {
        symbol: {"session_date": day, "actual_source": "schwab", "retrieved_at": "2026-09-10T20:45:00+00:00"}
        for symbol in ["SPY", "XLK"]
    }}


def _frames():
    rotation = pd.DataFrame([{"sector": "Information Technology", "etf": "XLK"}])
    rotation.attrs["evidence"] = _evidence()
    candidates = pd.DataFrame([{"symbol": "AAPL", "sector": "Information Technology", "rank_score": 0.8,
                                "status": "Near Breakout", "session_date": "2026-09-10"}])
    candidates.attrs["evidence"] = {"session_date": "2026-09-10", "benchmark": "SPY", "period": "1y",
                                    "scan_run_id": 137, "universe": "sp500"}
    heavyweights = pd.DataFrame([{"sector": "Information Technology", "heavyweight_score": 1.}])
    heavyweights.attrs["evidence"] = _evidence()
    breadth = page._candidate_breadth(candidates)
    return rotation, candidates, heavyweights, breadth


class _UI:
    def __init__(self):
        self.messages = []

    def warning(self, text):
        self.messages.append(text)

    caption = warning

    def expander(self, text):
        return nullcontext()

    def dataframe(self, *args, **kwargs):
        pass


def _render(monkeypatch, frames):
    ui = _UI()
    output = []
    monkeypatch.setattr(page, "_render_sector_dashboard", lambda st, *args: output.append(args))
    page._render_trusted_dashboard(ui, *frames, [], created_at="2026-07-28T12:00:00Z")
    return ui, output[0]


def test_current_compatible_snapshot_joins_recorded_candidates_and_breadth(monkeypatch):
    ui, rendered = _render(monkeypatch, _frames())
    assert len(rendered[1]) == len(rendered[3]) == 1
    assert any("Scanner run 137" in text and "2026-09-10" in text for text in ui.messages)
    assert any("schwab" in text for text in ui.messages)
    assert "positive_20d_pct" not in rendered[3]
    assert rendered[3].iloc[0]["near_breakout_pct"] == 1


@pytest.mark.parametrize("damage", ["historical", "undated", "mixed_sector_dates", "missing_etf",
                                    "future", "missing_benchmark"])
def test_historical_or_mixed_sector_snapshot_withholds_joins(monkeypatch, damage):
    frames = _frames()
    evidence = frames[0].attrs["evidence"]
    if damage == "historical":
        frames[0].attrs["evidence"] = _evidence("2026-07-27")
    elif damage == "undated":
        frames[0].attrs["evidence"] = {}
    elif damage == "mixed_sector_dates":
        evidence["symbols"]["XLK"]["session_date"] = "2026-07-27"
    elif damage == "missing_etf":
        del evidence["symbols"]["XLK"]
    elif damage == "future":
        frames[0].attrs["evidence"] = _evidence("2026-09-14")
    elif damage == "missing_benchmark":
        del evidence["symbols"]["SPY"]
    ui, rendered = _render(monkeypatch, frames)
    assert rendered[1].empty and rendered[3].empty
    assert any("Historical / unverified" in text and "Jul 28, 2026 08:00 AM EDT" in text for text in ui.messages)


@pytest.mark.parametrize(("key", "value"), [
    ("session_date", "2026-07-27"), ("period", "2y"), ("benchmark", "QQQ"),
    ("scan_run_id", None), ("universe", ""),
])
def test_incompatible_candidate_context_is_not_joined(monkeypatch, key, value):
    rotation, candidates, heavyweights, _ = _frames()
    candidates.attrs["evidence"][key] = value
    ui, rendered = _render(monkeypatch, (rotation, candidates, heavyweights, pd.DataFrame()))
    assert rendered[1].empty and rendered[3].empty
    assert any("Scanner join withheld" in text for text in ui.messages)


def test_individual_candidate_dates_cannot_hide_behind_matching_context(monkeypatch):
    rotation, candidates, heavyweights, _ = _frames()
    candidates.loc[0, "session_date"] = "2026-07-27"
    _, rendered = _render(monkeypatch, (rotation, candidates, heavyweights, pd.DataFrame()))
    assert rendered[1].empty and rendered[3].empty


def test_stale_saved_breadth_is_replaced_only_with_compatible_candidate_subset(monkeypatch):
    frames = _frames()
    frames[3].attrs["evidence"] = {**frames[3].attrs["evidence"], "session_date": "2026-07-27"}
    frames[3].loc[0, "breadth_score"] = 0.
    _, rendered = _render(monkeypatch, frames)
    assert rendered[3].iloc[0]["breadth_score"] > 0
    assert rendered[3].attrs["evidence"]["session_date"] == "2026-09-10"


def test_saved_historical_page_never_loads_latest_scanner_or_provider(monkeypatch):
    snapshot = StoredSectorRotationSnapshot(11, "2026-07-28T12:00:00Z", "test", "1y", "schwab", "",
        {"benchmark": "SPY", "sectors": [{"sector": "Information Technology", "etf": "XLK"}], "extras": {}})

    class Repo:
        def __init__(self, *args):
            pass

        def latest(self):
            return snapshot

        def compare_latest(self):
            return []

    monkeypatch.setattr(page, "SQLiteSectorRotationRepository", Repo)
    monkeypatch.setattr(page, "_sector_candidates", lambda *args: pytest.fail("Historical page loaded latest candidates"))
    monkeypatch.setattr(page, "build_fallback_market_data_provider", lambda *args: pytest.fail("Read-only page built provider"))
    output = []
    monkeypatch.setattr(page, "_render_sector_dashboard", lambda st, *args: output.append(args))
    app = AppTest.from_string("import streamlit as st\nfrom qx.ui.pages.sector_rotation import render_sector_rotation_page\nrender_sector_rotation_page(st)").run()
    assert not app.exception
    assert any("Historical / unverified" in warning.value for warning in app.warning)
    assert output[0][1].empty and output[0][3].empty


def test_rerender_rechecks_completed_session_not_only_control_context(monkeypatch):
    frames = _frames()
    monkeypatch.setattr(page, "latest_completed_session", lambda *args: "2026-09-11")
    _, rendered = _render(monkeypatch, frames)
    assert rendered[1].empty and rendered[3].empty


def test_snapshot_evidence_roundtrip_preserves_utc_and_dated_extras(tmp_path):
    rotation, candidates, heavyweights, breadth = _frames()
    repository = SQLiteSectorRotationRepository(tmp_path / "trust-test.db")
    page._save_sector_snapshot(repository, SectorRotationResult("SPY", [], {}), period="1y", data_source="schwab",
                               heavyweight_frame=heavyweights, breadth_frame=breadth,
                               evidence=rotation.attrs["evidence"], candidates_frame=candidates)
    saved = repository.latest()
    assert saved.created_at.endswith("+00:00")
    restored = page._frames_from_sector_snapshot(saved.payload)
    assert restored[0].attrs["evidence"] == rotation.attrs["evidence"]
    assert saved.payload["extras"]["scanner_candidates"][0]["session_date"] == "2026-09-10"
    assert saved.payload["extras"]["scanner_evidence"]["scan_run_id"] == 137


def test_malformed_snapshot_extras_fail_closed():
    frames = page._frames_from_sector_snapshot({"sectors": [None, 42], "extras": "bad"})
    assert all(frame.empty for frame in frames)
    assert not page._matching_evidence({"session_date": "2026-09-10", "symbols": None}, {})


def test_mixed_auxiliary_symbol_dates_fail_matching():
    left, right = _evidence(), deepcopy(_evidence())
    left["symbols"]["XLK"]["session_date"] = "2026-07-27"
    assert not page._matching_evidence(left, right)


def test_refresh_retains_exact_completed_inputs_and_utc_retrieval_without_repeat_loads(tmp_path):
    class Provider:
        calls = 0

        def get_daily_bars(self, request):
            self.calls += 1
            labels = _schedule(_Clock.now().date()).index[-30:]
            frame = pd.DataFrame({"open": 10., "high": 12., "low": 9., "close": 11., "volume": 1000.},
                                 index=pd.DatetimeIndex(labels, name="Date"))
            frame.attrs["provenance"] = {"schema_version": 1, "actual_source": "schwab", "fallback_used": False,
                                         "retrieved_at": "2026-09-11T08:00:00-04:00", "last_bar_label": str(frame.index[-1])}
            return frame

    source = Provider()
    provider = page._SessionEvidenceProvider(source, cache_dir=tmp_path, refresh=True)
    request = BarDataRequest(symbol="SPY", period="1y")
    bars = provider.get_daily_bars(request)
    provider.get_daily_bars(request)
    assert source.calls == 1
    assert str(bars.index[-1].date()) == "2026-09-10"
    evidence = provider.context(["SPY"], "1y", "SPY")
    assert evidence["symbols"]["SPY"]["retrieved_at"] == "2026-09-11T12:00:00+00:00"
    assert page._current_evidence(evidence)
    assert provider.context(["SPY", "MISSING"], "1y", "SPY") == {}
