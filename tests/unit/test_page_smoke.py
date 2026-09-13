from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from qx.ui.pages import PAGES
from qx.ui.command_overview import WATCH_COLUMNS, overview_frame


@pytest.mark.parametrize("title", [page.title for page in PAGES])
def test_page_initial_render(title: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages import PAGES\n"
        f"next(page for page in PAGES if page.title == {title!r}).render(st)\n"
    ).run(timeout=30)
    assert not app.exception, [item.message for item in app.exception]


def test_overview_limits_columns_without_mutating_source() -> None:
    rows = [{"symbol": "TEST", "close": 100.0, "readiness_label": "Watch", "extra": 1}] * 12
    result = overview_frame(rows, WATCH_COLUMNS)
    assert len(result) == 8
    assert list(result) == ["Symbol", "Status", "Close"]
    assert rows[0]["extra"] == 1


def test_empty_overview() -> None:
    assert isinstance(overview_frame([], WATCH_COLUMNS), pd.DataFrame)
    assert overview_frame([], WATCH_COLUMNS).empty


def test_ticker_timeframe_switch_reuses_loaded_bars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from qx.ui.pages import ticker_history
    from tests.unit.test_rectangle import _clean_rectangle_bars

    calls = []

    class Provider:
        def get_daily_bars(self, request: object) -> pd.DataFrame:
            calls.append(request)
            frame = _clean_rectangle_bars().copy()
            frame.index = pd.date_range("2024-01-01", periods=len(frame))
            return frame

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ticker_history, "build_fallback_market_data_provider", lambda name: Provider())
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.ticker_history import render_ticker_history_page\n"
        "render_ticker_history_page(st)"
    ).run()
    app.button[0].click().run()
    assert not app.exception
    next(item for item in app.selectbox if item.label == "Chart timeframe").select("Weekly").run()
    assert not app.exception
    assert len(calls) == 1
    assert len(app.get("plotly_chart")) == 1
