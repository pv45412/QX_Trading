import html
import re
from urllib.parse import parse_qs, urlparse

import pytest

from qx.ui.pages import jobs, run_history


class NavigationUI:
    def __init__(self, query):
        self.query_params = dict(query)
        self.markdowns = []
        self.sidebar = self

    def set_page_config(self, **kwargs):
        pass

    def empty(self):
        return self

    def markdown(self, body, **kwargs):
        self.markdowns.append(body)

    def subheader(self, *args):
        pass


@pytest.mark.parametrize(("page", "view_key", "selected", "module", "renderer"), [
    (jobs, "job_view", "Pipeline", "pipeline", "render_pipeline_page"),
    (jobs, "job_view", "Schedule", "automation_control", "render_automation_control_page"),
    (run_history, "history_view", "Scans", "history", "render_history_page"),
    (run_history, "history_view", "Workflows", "workflow_history", "render_workflow_history_page"),
    (run_history, "history_view", "Snapshots", "snapshot_history", "render_snapshot_history_page"),
])
def test_native_view_navigation_preserves_context_and_renders_only_selection(
    page, view_key, selected, module, renderer, monkeypatch,
) -> None:
    calls = []

    def lazy(module_name, function_name):
        calls.append(("load", module_name, function_name))
        return lambda ui: calls.append(("render", module_name, function_name))

    monkeypatch.setattr(page, "lazy_page_renderer", lazy)
    monkeypatch.setattr(page, "ensure_app_styles", lambda ui: None)
    query = {view_key: selected, "symbol": "TEST", "snapshot": "7", "period": "2y",
             "sector": "Health Care", "as_of": "2026-09-10", "universe": "sp500"}
    ui = NavigationUI(query)
    render = page.render_jobs_page if page is jobs else page.render_run_history_page
    render(ui)
    assert calls == [
        ("load", f"qx.ui.pages.{module}", renderer),
        ("render", f"qx.ui.pages.{module}", renderer),
    ]
    assert ui.query_params == query
    markup = ui.markdowns[0]
    assert markup.count('aria-current="page"') == 1
    assert f'aria-current="page">{selected}</a>' in markup
    for url in re.findall(r'href="([^"]+)"', markup):
        params = parse_qs(urlparse(html.unescape(url)).query)
        assert params["page"] == ["jobs" if page is jobs else "run_history"]
        assert params["symbol"] == ["TEST"]
        assert params["snapshot"] == ["7"]
        assert params["sector"] == ["Health Care"]
        assert params["as_of"] == ["2026-09-10"]
        assert params["universe"] == ["sp500"]
        assert params["period"] == ["2y"]


@pytest.mark.parametrize(("page", "view_key", "default_module"), [
    (jobs, "job_view", "pipeline"), (run_history, "history_view", "history"),
])
def test_invalid_view_is_read_only_and_defaults_to_single_renderer(
    page, view_key, default_module, monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(page, "ensure_app_styles", lambda ui: None)
    monkeypatch.setattr(page, "lazy_page_renderer",
                        lambda module, name: lambda ui: calls.append(module))
    render = page.render_jobs_page if page is jobs else page.render_run_history_page
    ui = NavigationUI({view_key: '<script>alert("test")</script>'})
    render(ui)
    assert calls == [f"qx.ui.pages.{default_module}"]
    assert "<script>" not in ui.markdowns[0]


def test_url_view_changes_are_not_overridden_by_stale_widget_state(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(jobs, "ensure_app_styles", lambda ui: None)
    monkeypatch.setattr(jobs, "lazy_page_renderer",
                        lambda module, name: lambda ui: calls.append(module))
    ui = NavigationUI({"job_view": "Pipeline"})
    jobs.render_jobs_page(ui)
    ui.query_params["job_view"] = "Schedule"
    jobs.render_jobs_page(ui)
    ui.query_params["job_view"] = "Pipeline"
    jobs.render_jobs_page(ui)
    assert calls == ["qx.ui.pages.pipeline", "qx.ui.pages.automation_control",
                     "qx.ui.pages.pipeline"]


@pytest.mark.parametrize(("route", "view_key", "view", "expected_module"), [
    ("pipeline", "job_view", "Pipeline", "pipeline"),
    ("pipeline_control", "job_view", "Pipeline", "pipeline"),
    ("automation_control", "job_view", "Schedule", "automation_control"),
    ("history", "history_view", "Scans", "history"),
    ("workflow_history", "history_view", "Workflows", "workflow_history"),
    ("command_snapshots", "history_view", "Snapshots", "snapshot_history"),
    ("jobs", "job_view", "Schedule", "automation_control"),
    ("run_history", "history_view", "Snapshots", "snapshot_history"),
])
def test_parent_navigation_aliases_reach_only_the_matching_component(
    route, view_key, view, expected_module, monkeypatch,
) -> None:
    from qx.ui import streamlit_app

    query = {"page": route, "symbol": "TEST", "snapshot": "7"}
    if route in ("jobs", "run_history"):
        query[view_key] = view
    ui = NavigationUI(query)
    calls = []
    monkeypatch.setattr(streamlit_app, "import_module", lambda name: ui)
    monkeypatch.setattr(streamlit_app, "render_page_header", lambda *args: None)
    for page in (jobs, run_history):
        monkeypatch.setattr(page, "ensure_app_styles", lambda ui: None)
        monkeypatch.setattr(page, "lazy_page_renderer",
                            lambda module, name: lambda ui: calls.append(module))
    streamlit_app.main()
    assert calls == [f"qx.ui.pages.{expected_module}"]
    assert ui.query_params[view_key] == view
    assert ui.query_params["symbol"] == "TEST"
    assert ui.query_params["snapshot"] == "7"


@pytest.mark.parametrize(("route", "module", "renderer"), [
    ("performance", "performance", "render_performance_page"),
    ("idea_tracking", "performance", "render_performance_page"),
    ("journal", "journal", "render_journal_page"),
])
def test_parent_journal_routes_keep_ideas_and_outcomes_distinct(
    route, module, renderer, monkeypatch,
) -> None:
    from importlib import import_module
    from qx.ui import streamlit_app

    ui = NavigationUI({"page": route, "symbol": "TEST", "snapshot": "7"})
    calls = []
    monkeypatch.setattr(streamlit_app, "import_module", lambda name: ui)
    monkeypatch.setattr(streamlit_app, "render_page_header", lambda *args: None)
    monkeypatch.setattr(import_module(f"qx.ui.pages.{module}"), renderer,
                        lambda ui: calls.append(renderer))
    streamlit_app.main()
    assert calls == [renderer]
    assert ui.query_params["symbol"] == "TEST"
