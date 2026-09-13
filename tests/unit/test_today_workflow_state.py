from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from qx.ui.pages import daily_workflow


def test_workflow_result_survives_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    builds = []

    def build(**kwargs: object) -> str:
        builds.append(kwargs)
        return "saved report"

    monkeypatch.setattr(daily_workflow, "build_daily_workflow_report", build)
    monkeypatch.setattr(daily_workflow, "build_fallback_market_data_provider", lambda source: object())
    monkeypatch.setattr(daily_workflow.SQLiteWorkflowRepository, "save", lambda self, report: 12)
    monkeypatch.setattr(daily_workflow, "_render_report", lambda st, report, **kwargs: st.text(report))
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.pages.daily_workflow import render_daily_workflow_page\n"
        "render_daily_workflow_page(st)"
    ).run()
    app.button[0].click().run()
    app.run()
    assert not app.exception
    assert len(builds) == 1
    assert any(item.value == "saved report" for item in app.text)
