from types import SimpleNamespace
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from qx.ui.pages import command_center


def test_refresh_live_bypasses_cache_without_loading_on_page_open(monkeypatch, tmp_path):
    monkeypatch.setattr(command_center, "SCAN_HISTORY_DB", tmp_path / "qx.db")
    snapshots = SimpleNamespace(list_snapshots=lambda **kwargs: [], save=Mock(return_value=1))
    monkeypatch.setattr(command_center, "SQLiteCommandCenterSnapshotRepository", lambda *args: snapshots)
    monkeypatch.setattr(command_center, "_render_pipeline_status", lambda *args: None)
    monkeypatch.setattr(command_center, "_watchlist_symbols_for_mode", lambda *args: ["TEST"])
    upstream = object()
    factory = Mock(return_value=upstream)
    monkeypatch.setattr(command_center, "build_fallback_market_data_provider", factory)
    for name in ("build_options_chain_provider", "build_fundamental_provider", "build_ema_timing_provider"):
        monkeypatch.setattr(command_center, name, lambda *args: None)
    build = Mock(return_value=object())
    monkeypatch.setattr(command_center, "build_command_center", build)
    monkeypatch.setattr(command_center, "command_center_payload", lambda *args: {})
    monkeypatch.setattr(command_center, "render_command_overview", lambda *args: None)
    app = AppTest.from_string('''
import streamlit as st
from qx.ui.pages.command_center import render_command_center_page
render_command_center_page(st)
''').run(timeout=30)
    assert not app.exception
    factory.assert_not_called()
    build.assert_not_called()
    refresh = next(button for button in app.button if button.label == "Refresh live")
    refresh.click().run(timeout=30)
    assert not app.exception
    provider = build.call_args.kwargs["provider"]
    assert provider.provider is upstream
    assert provider.refresh is True
    assert snapshots.save.call_count == 1
