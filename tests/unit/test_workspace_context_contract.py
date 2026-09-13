import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from streamlit.testing.v1 import AppTest

from qx.storage.command_center import SQLiteCommandCenterSnapshotRepository
from qx.ui.pages.today_views import watchlist_changes
from qx.ui.today_state import today_snapshots
from qx.ui.workspace_context import markets_url, read_context, workspace_url


def test_navigation_context_is_allowlisted_and_encoded() -> None:
    context = {"symbol": "brk.b", "universe": "sp500", "sector": "Information Technology", "as_of": "2026-09-10", "period": "2y", "snapshot": "92", "secret": "not-for-links"}
    for url in (workspace_url("ticker_history", context), markets_url(context)):
        query = parse_qs(urlparse(url).query)
        assert query["symbol"] == ["BRK.B"]
        assert query["sector"] == ["Information Technology"]
        assert query["as_of"] == ["2026-09-10"]
        assert query["snapshot"] == ["92"]
        assert "secret" not in query
    assert "as_of=" not in workspace_url("scan", context, as_of="")
    assert "history_view=Scans" in workspace_url("run_history", context, history_view="Scans")


def test_invalid_context_does_not_break_or_escape_navigation() -> None:
    assert read_context({"symbol": "<script>", "universe": "made-up", "as_of": "2026-02-30", "snapshot": "9" * 5000}) == {}
    assert read_context({"snapshot": "0", "period": "garbage", "as_of": "9999-12-31"}) == {}
    assert read_context({"symbol": "/ES", "etf": "xle"}) == {"symbol": "/ES", "etf": "XLE"}


def _add(repository: SQLiteCommandCenterSnapshotRepository, *, universe: str = "S&P 500", period: str = "2y", source: str = "schwab", created: str = "2026-09-11T03:00:00+00:00") -> int:
    repository.initialize()
    with sqlite3.connect(repository.database_path) as connection:
        cursor = connection.execute("""INSERT INTO command_center_snapshots
            (created_at, source, period, data_source, universe, regime_label, risk_level, spx_bias,
             volatility_context, watchlist_count, option_ideas_count, saved_options_count, payload_json)
             VALUES (?, 'test', ?, ?, ?, '', '', '', '', 0, 0, 0, ?)""", (created, period, source, universe, json.dumps({})))
        return int(cursor.lastrowid)


def test_today_views_select_same_compatible_report_and_et_cutoff(tmp_path: Path) -> None:
    repository = SQLiteCommandCenterSnapshotRepository(tmp_path / "history.db")
    first = _add(repository)
    _add(repository, universe="NASDAQ 100")
    _add(repository, period="5y")
    _add(repository, created="2026-09-11T05:00:00+00:00")
    context = {"universe": "sp500", "period": "2y", "as_of": "2026-09-10"}
    assert today_snapshots(repository, context)[0].id == first
    assert today_snapshots(repository, context | {"snapshot": "999"}) == []
    assert today_snapshots(repository, context | {"snapshot": str(first), "universe": "nasdaq_100"}) == []


def test_today_comparison_never_uses_another_universe_period_or_source(tmp_path: Path) -> None:
    repository = SQLiteCommandCenterSnapshotRepository(tmp_path / "history.db")
    first = _add(repository)
    _add(repository, source="yfinance")
    _add(repository, universe="NASDAQ 100")
    current_id = _add(repository)
    context = {"universe": "sp500", "period": "2y", "snapshot": str(current_id)}
    current = today_snapshots(repository, context)[0]
    assert today_snapshots(repository, context, previous_to=current)[0].id == first


def test_changes_compare_saved_states_without_fabricating_price_moves() -> None:
    old = {"watchlist": [{"symbol": "A", "readiness_label": "Watch"}, {"symbol": "B"}]}
    new = {"watchlist": [{"symbol": "A", "readiness_label": "Ready"}, {"symbol": "C"}]}
    changes = watchlist_changes(new, old)
    assert [(row["symbol"], row["change"]) for row in changes] == [("A", "State changed"), ("B", "Removed"), ("C", "Added")]
    assert all("return" not in row for row in changes)


def test_view_navigation_survives_a_stopped_page() -> None:
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.app_shell import AppPage\n"
        "from qx.ui.streamlit_app import _workspace_renderer\n"
        "_workspace_renderer([AppPage('Scanner', '', lambda s: s.stop()), "
        "AppPage('Broad Watchlist', '', lambda s: None)])(st)"
    ).run()
    assert not app.exception
    assert any('aria-label="Workspace views"' in item.value and 'Broad Watchlist' in item.value
               for item in app.markdown)


def test_unsupported_universe_is_not_silently_replaced() -> None:
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.app_shell import AppPage\n"
        "from qx.ui.streamlit_app import _workspace_renderer\n"
        "_workspace_renderer([AppPage('Scanner', '', lambda s: s.text('Wrong universe rendered'))])(st)"
    )
    app.query_params.update({"universe": "etfs", "symbol": "XLK", "as_of": "2026-09-01"})
    app.run()
    assert not app.exception
    assert not app.text
    assert any("It has not been replaced" in item.value for item in app.warning)
    assert app.query_params["universe"] == ["etfs"]
    assert app.query_params["as_of"] == ["2026-09-01"]
