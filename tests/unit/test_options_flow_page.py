import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from qx.ui.pages import options_flow
from tests.unit.test_rectangle import _clean_rectangle_bars


def test_options_flow_requires_upload_before_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_fetch(*args: object) -> pd.DataFrame:
        raise AssertionError("Missing upload must not fetch market data")

    monkeypatch.setattr(options_flow, "_load_bars", unexpected_fetch)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.options_flow import render_options_flow_page\n"
        "render_options_flow_page(st)"
    ).run()
    flow_input = next(item for item in app.selectbox if item.label == "Flow input")
    assert flow_input.value == "CSV upload"
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert any("Select a CSV" in item.value for item in app.warning)


def test_sample_flow_is_labeled_and_not_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(options_flow, "_load_bars", lambda *args: _clean_rectangle_bars())

    def unexpected_save(*args: object) -> None:
        raise AssertionError("Sample flow must not be persisted")

    monkeypatch.setattr(options_flow.SQLiteOptionFlowRepository, "save_analysis", unexpected_save)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.options_flow import render_options_flow_page\n"
        "render_options_flow_page(st)"
    ).run()
    next(item for item in app.selectbox if item.label == "Flow input").select("Sample CSV")
    app.button[0].click().run(timeout=20)
    assert not app.exception
    assert not app.error
    assert app.session_state["options_flow_signal_id"] is None
    assert any("Sample data:" in item.value for item in app.warning)
