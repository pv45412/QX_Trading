from copy import deepcopy
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from streamlit.testing.v1 import AppTest

from qx.storage.sector_rotation import StoredSectorRotationSnapshot
from qx.ui.pages import sector_rotation as page


class _Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 11, 12, tzinfo=UTC)


def _snapshot(day=None, period="1y", identity=11):
    evidence = {} if day is None else {
        "session_date": day, "benchmark": "SPY", "period": period,
        "symbols": {symbol: {"session_date": day, "actual_source": "schwab"} for symbol in ["SPY", "XLK"]},
    }
    return StoredSectorRotationSnapshot(identity, "2026-07-28T12:00:00Z", "test", period, "schwab", "", {
        "benchmark": "SPY", "sectors": [{"sector": "Information Technology", "etf": "XLK"}],
        "extras": {"evidence": evidence},
    })


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(page, "datetime", _Clock)
    snapshots, rendered = [], []

    class Repo:
        def __init__(self, *args):
            pass

        def latest(self):
            return snapshots[0] if snapshots else None

        def list_snapshots(self, limit=10):
            return snapshots[:limit]

        def compare_latest(self):
            return []

        def save(self, *args, **kwargs):
            pytest.fail("Archive navigation attempted a payload write")

    monkeypatch.setattr(page, "SQLiteSectorRotationRepository", Repo)
    monkeypatch.setattr(page, "build_fallback_market_data_provider", lambda *args: pytest.fail("Archive navigation built a live provider"))
    monkeypatch.setattr(page, "_sector_candidates", lambda *args: pytest.fail("Historical archive loaded latest scanner"))
    monkeypatch.setattr(page, "_render_sector_dashboard", lambda st, *args: rendered.append(args))

    def render(query):
        app = AppTest.from_string(
            "import streamlit as st\n"
            "from qx.ui.pages.sector_rotation import render_sector_rotation_page\n"
            "render_sector_rotation_page(st)"
        )
        app.query_params.update(query)
        app.run()
        assert not app.exception
        return app

    return snapshots, rendered, render


def test_requested_date_mismatch_is_unavailable_and_refresh_disabled(archive):
    snapshots, rendered, render = archive
    snapshots.append(_snapshot("2026-07-27"))
    app = render({"as_of": "2026-07-28", "period": "1y", "universe": "nasdaq_100", "etf": "XLK"})
    assert any(item.value == "Sector Archive" for item in app.subheader)
    assert any("Historical sector data unavailable for 2026-07-28" in item.value for item in app.warning)
    assert any("nasdaq_100 is not applied" in item.value for item in app.warning)
    assert any("11 S&P 500 sector ETFs / SPY" in item.value for item in app.caption)
    assert any("XLK is not applied as a filter" in item.value for item in app.caption)
    assert app.button[0].disabled
    assert not rendered
    query = parse_qs(urlparse(app.get("link_button")[0].proto.url).query)
    assert "as_of" not in query
    assert query["period"] == ["1y"] and query["page"] == ["sector_rotation"]


def test_initial_undated_snapshot_remains_historical_warning_and_payload_unchanged(archive):
    snapshots, rendered, render = archive
    snapshot = _snapshot()
    snapshots.append(snapshot)
    before = deepcopy(snapshot.payload)
    app = render({})
    assert any("Historical / unverified sector snapshot" in item.value for item in app.warning)
    assert any("Bar/session date: not recorded" in item.value for item in app.warning)
    assert not app.button[0].disabled
    assert rendered[0][1].empty and rendered[0][3].empty
    assert snapshot.payload == before


def test_undated_snapshot_never_satisfies_requested_date_from_creation_time(archive):
    snapshots, rendered, render = archive
    snapshots.append(_snapshot())
    app = render({"as_of": "2026-07-28", "period": "1y"})
    assert any("Historical sector data unavailable" in item.value for item in app.warning)
    assert not rendered


def test_matching_older_evidence_selected_and_url_period_applied(archive):
    snapshots, rendered, render = archive
    snapshots.extend([_snapshot("2026-09-10", identity=12), _snapshot("2026-07-27", period="2y")])
    app = render({"as_of": "2026-07-27", "period": "2y"})
    assert app.selectbox(key="sector_history").value == "2y"
    assert len(rendered) == 1
    assert rendered[0][0].attrs["evidence"]["session_date"] == "2026-07-27"
    assert any("Saved snapshot 11" in item.value for item in app.caption)


def test_mixed_evidence_dates_do_not_match_archive_request(archive):
    snapshots, rendered, render = archive
    snapshot = _snapshot("2026-07-27")
    snapshot.payload["extras"]["evidence"]["symbols"]["XLK"]["session_date"] = "2026-07-24"
    snapshots.append(snapshot)
    app = render({"as_of": "2026-07-27", "period": "1y"})
    assert any("Historical sector data unavailable" in item.value for item in app.warning)
    assert not rendered
