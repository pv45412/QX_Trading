from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from qx.ui.pages import spx_dashboard


def test_futures_retains_result_until_request_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls = []

    def build(*args: object, **kwargs: object) -> str:
        calls.append(kwargs)
        return "Futures result"

    monkeypatch.setattr(spx_dashboard, "build_spx_dashboard", build)
    monkeypatch.setattr(spx_dashboard, "build_fallback_market_data_provider", lambda source: object())
    monkeypatch.setattr(spx_dashboard, "build_quote_provider", lambda source: object())
    monkeypatch.setattr(spx_dashboard, "_render_dashboard", lambda st, result: st.text(result))
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.spx_dashboard import render_spx_dashboard_page\n"
        "render_spx_dashboard_page(st)"
    ).run()
    app.button[0].click().run()
    app.run()
    assert not app.exception
    assert len(calls) == 1
    assert any(item.value == "Futures result" for item in app.text)
    app.selectbox(key="spx_dashboard_history").select("1y").run()
    assert not any(item.value == "Futures result" for item in app.text)
    assert len(calls) == 1


def test_sector_changed_context_does_not_render_stale_frames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.sector_rotation import render_sector_rotation_page\n"
        "st.session_state['sector_board_frames'] = ('old',)\n"
        "st.session_state['sector_board_context'] = ('old',)\n"
        "render_sector_rotation_page(st)"
    ).run()
    assert not app.exception
    assert any("Settings changed" in item.value for item in app.warning)
