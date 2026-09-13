from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from qx.ui.pages import options_ideas, spx_dashboard, watchlist


@pytest.mark.parametrize("module,renderer,builder,button", [
    (options_ideas, "render_options_ideas_page", "_build_ideas_frame", "Build Ideas"),
    (watchlist, "render_watchlist_page", "build_broad_watchlist", "Build Watchlist"),
    (spx_dashboard, "render_spx_dashboard_page", "build_spx_dashboard", "Load Context"),
])
@pytest.mark.parametrize("historical", [False, True])
def test_navigation_does_not_start_expensive_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module, renderer: str,
    builder: str, button: str, historical: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(module, builder, lambda *args, **kwargs: calls.append(kwargs))
    app = AppTest.from_string(
        "import streamlit as st\n"
        f"from {module.__name__} import {renderer}\n"
        f"{renderer}(st)"
    )
    app.query_params.update({"universe": "custom", "symbol": "MSFT", "period": "1y"})
    if historical:
        app.query_params["as_of"] = "2026-09-01"
    app.run()
    app.run()
    assert not app.exception
    assert calls == []
    assert app.query_params["period"] == ["1y"]
    assert app.query_params["symbol"] == ["MSFT"]
    run_button = next(item for item in app.button if item.label == button)
    assert run_button.disabled == historical
    if historical:
        assert any("Requested date" in item.value for item in app.warning)


def test_options_failure_is_contained_and_old_results_not_substituted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    def unavailable(**kwargs):
        raise ConnectionError("private provider detail")

    monkeypatch.setattr(options_ideas, "_build_ideas_frame", unavailable)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.options_ideas import render_options_ideas_page\n"
        "render_options_ideas_page(st)"
    ).run()
    next(item for item in app.button if item.label == "Build Ideas").click().run()
    assert not app.exception
    assert any("No previous result is substituted" in item.value for item in app.error)
    assert not app.dataframe
    assert "options_ideas_frame" not in app.session_state
