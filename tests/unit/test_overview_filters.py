from qx.ui.command_overview import filter_watchlist
from streamlit.testing.v1 import AppTest


ROWS = [
    {"symbol": "AAPL", "name": "Apple", "sector": "Technology", "readiness_label": "Ready Now"},
    {"symbol": "XOM", "name": "Exxon", "sector": "Energy", "readiness_label": "Extended Risk"},
]


def test_watchlist_search_is_case_insensitive_and_combines_status() -> None:
    assert filter_watchlist(ROWS, "  tech ", "All statuses") == ROWS[:1]
    assert filter_watchlist(ROWS, "apple", "Ready Now") == ROWS[:1]
    assert filter_watchlist(ROWS, "apple", "Extended Risk") == []


def test_watchlist_empty_search_preserves_order_and_missing_fields() -> None:
    rows = [*ROWS, {"symbol": "TEST"}]
    assert filter_watchlist(rows, "", "All statuses") == rows
    assert filter_watchlist(rows, "TEST", "All statuses") == rows[-1:]
    assert rows[-1] == {"symbol": "TEST"}


def test_filter_interaction_and_empty_state() -> None:
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.command_overview import render_command_overview\n"
        f"render_command_overview(st, {{'watchlist': {ROWS!r}}})"
    ).run()
    assert not app.exception
    app.text_input[0].set_value("XOM").run()
    assert not app.exception
    assert app.selectbox(key="command_detail_symbol").value is None
    app.selectbox(key="command_detail_symbol").select("XOM").run()
    assert app.query_params["symbol"] == ["XOM"]
    app.text_input[0].set_value("missing").run()
    assert not app.exception
    assert any("No candidates match" in item.value for item in app.info)
    assert app.query_params["symbol"] == ["XOM"]


def test_filter_does_not_replace_carried_ticker() -> None:
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.command_overview import render_command_overview\n"
        f"render_command_overview(st, {{'watchlist': {ROWS!r}}})"
    )
    app.query_params["symbol"] = "MSFT"
    app.run()
    app.text_input[0].set_value("XOM").run()
    assert not app.exception
    assert app.selectbox(key="command_detail_symbol").value is None
    assert app.query_params["symbol"] == ["MSFT"]
    assert any("Navigation selection is unchanged" in item.value for item in app.caption)
