from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from qx.models.scan import ScanRunResult
from qx.ui.pages import scan


def test_scanner_controls_and_result_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls = []
    retries = []

    def run(self: object, symbols: list[str], period: str, *, retry_failed: bool = False) -> ScanRunResult:
        calls.append(symbols)
        retries.append(retry_failed)
        return ScanRunResult(candidates=[], total_symbols=len(symbols), passed_symbols=0, failed_symbols=0, errors=[])

    monkeypatch.setattr(scan, "_cache_health_label", lambda *args: "Test cache")
    monkeypatch.setattr(scan, "_render_cache_warning", lambda *args: None)
    monkeypatch.setattr(scan, "build_fallback_market_data_provider", lambda source: object())
    monkeypatch.setattr(scan, "analyze_market_regime", lambda *args, **kwargs: None)
    monkeypatch.setattr(scan.ScannerEngine, "scan_symbols", run)
    monkeypatch.setattr(scan, "_render_scan_result", lambda st, **kwargs: st.text("Retained result"))
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.scan import render_scan_page\n"
        "render_scan_page(st)"
    ).run()
    assert not any(x.label == "Timeframe" for x in app.selectbox)
    assert any(x.value == "Daily bars" for x in app.caption)
    assert next(x for x in app.selectbox if x.label == "Scan Type").options == list(scan.SCAN_TYPE_OPTIONS)
    app.button[0].click().run()
    assert not app.exception
    app.run()
    assert not app.exception
    assert len(calls) == 1
    assert retries == [False]
    assert any(item.value == "Retained result" for item in app.text)
    next(x for x in app.selectbox if x.label == "History").select("3y").run()
    assert not any(item.value == "Retained result" for item in app.text)
    assert len(calls) == 1
    next(x for x in app.checkbox if x.label == "Refresh live bars").check().run()
    app.button[0].click().run()
    assert not app.exception
    assert retries == [False, True]
