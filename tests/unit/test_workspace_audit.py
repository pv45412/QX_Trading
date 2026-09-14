from types import SimpleNamespace
from pathlib import Path
import tomllib

import pandas as pd
import pytest

from qx.ui.pages.history import history_changes_frame
from qx.ui.app_shell import inject_app_styles
from qx.ui.relative_strength_theme import apply_relative_strength_theme
from qx.ui.streamlit_app import PAGE_ROUTE_TABS, _requested_tab_title, _sync_selected_route


@pytest.mark.parametrize("title", sorted(set(PAGE_ROUTE_TABS.values())))
def test_selected_view_round_trips_through_url(title):
    app = SimpleNamespace(query_params={"keep": "value"}, session_state={},
                          context=SimpleNamespace(url="http://localhost/?page=command_center"))
    _sync_selected_route(app, title)
    assert _requested_tab_title(app) == title
    assert app.query_params["keep"] == "value"
    assert app.session_state["_consumed_route"] == app.query_params["page"]


def test_history_retains_comparison_evidence():
    frame = pd.DataFrame([dict(symbol="TEST", current_score=0.8, previous_score=0.6,
                               score_change=0.2, current_quality="A", previous_quality="B")])
    display = history_changes_frame(frame)
    assert list(display.columns) == ["Symbol", "Current Score", "Previous Score", "Score Change",
                                     "Current Quality", "Previous Quality"]
    assert frame.loc[0, "score_change"] == 0.2


def test_native_and_custom_themes_share_dashboard_palette():
    root = Path(__file__).resolve().parents[2]
    config_path = root / ".streamlit/config.toml"
    if not config_path.exists():
        pytest.skip(".streamlit/config.toml not present")
    theme = tomllib.loads(config_path.read_text())["theme"]
    assert theme["base"] == "dark"
    assert theme["backgroundColor"] == "#0e1117"
    assert theme["textColor"] == "#e6e9ee"
    captured = []
    app = SimpleNamespace(markdown=lambda body, **kwargs: captured.append(body))
    inject_app_styles(app)
    assert "--qx-bg: #0e1117" in captured[-1]
    assert "--qx-ink: #e6e9ee" in captured[-1]
    apply_relative_strength_theme(app)
    assert ":root" not in captured[-1]
    assert "var(--qx-panel)" in captured[-1]
