import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from streamlit.testing.v1 import AppTest

from qx.ui.streamlit_app import DISPLAY_TITLES, LEGACY_VIEWS, PAGE_ROUTE_ALIASES, PAGE_ROUTE_TABS
from qx.ui.workspace_context import CONTEXT_LABELS, ROUTE_ALIASES, read_context, sync_context, workspace_url


@pytest.fixture(scope="module")
def react_registry():
    node = shutil.which("node")
    assert node, "Node is required for the React/Streamlit route parity contract"
    result = subprocess.run(
        [node, "--input-type=module", "-e",
         "import {workspaceRoutes,routeAliases} from './src/workspace-routes.js';"
         "import {workspaceContextItems} from './src/workspace-context.js';"
         "console.log(JSON.stringify({routes:workspaceRoutes,aliases:routeAliases,"
         "labels:workspaceContextItems({universe:'u',symbol:'s',etf:'e',sector:'c',"
         "period:'p',as_of:'a',snapshot:'i'}).map(item=>item[0])}));"],
        cwd=Path(__file__).resolve().parents[2] / "web", text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def test_react_routes_cover_every_streamlit_view_with_matching_home_and_label(react_registry):
    routes = [route for route in react_registry["routes"] if route["page"] != "relative_strength"]
    assert {route["title"] for route in routes} == set(PAGE_ROUTE_TABS.values())
    for route in routes:
        assert PAGE_ROUTE_TABS[route["page"]] == route["title"]
        assert PAGE_ROUTE_ALIASES[route["page"]] == route["workspace"]
        assert DISPLAY_TITLES.get(route["title"], route["title"]) == route["label"]


def test_route_aliases_and_context_labels_match_both_apps(react_registry):
    assert react_registry["aliases"] == {key: list(value) for key, value in ROUTE_ALIASES.items()}
    assert react_registry["labels"] == [label for label, _ in CONTEXT_LABELS]
    for alias, target in ROUTE_ALIASES.items():
        assert PAGE_ROUTE_TABS[alias] == PAGE_ROUTE_TABS[target[0]]
        if len(target) == 3:
            assert LEGACY_VIEWS[alias] == target[1:]


@pytest.mark.parametrize("alias", ROUTE_ALIASES)
def test_legacy_links_are_canonical_and_keep_context(alias):
    context = dict(universe="sp500", symbol="MSFT", etf="XLK", period="2y",
                   as_of="2026-09-10", snapshot="92", secret="private")
    target = ROUTE_ALIASES[alias]
    query = parse_qs(urlparse(workspace_url(alias, context)).query)
    assert query["page"] == [target[0]]
    assert read_context({key: values[0] for key, values in query.items()}) == read_context(context)
    assert "secret" not in query
    if len(target) == 3:
        assert query[target[1]] == [target[2]]


def test_view_selectors_only_follow_their_own_page():
    context = {"job_view": "Schedule", "history_view": "Snapshots"}
    assert "job_view=Schedule" in workspace_url("jobs", context)
    assert "history_view=Snapshots" in workspace_url("run_history", context)
    assert "job_view" not in workspace_url("run_history", context)
    assert "history_view" not in workspace_url("jobs", context)
    assert "view=" not in workspace_url("scan", context)
    assert "view=" not in workspace_url("jobs", {"job_view": ["Schedule"]})
    assert workspace_url("relative_strength", {"symbol": "MSFT"}).startswith("http://127.0.0.1:5173/")


def test_explicit_context_clears_do_not_erase_unrelated_state():
    app = SimpleNamespace(query_params=dict(page="scan", universe="sp500", symbol="MSFT",
                                           as_of="2026-09-10", snapshot="92"))
    sync_context(app, as_of="", snapshot="", symbol="<invalid>")
    assert app.query_params == {"page": "scan", "universe": "sp500", "symbol": "MSFT"}


def test_shell_context_summary_updates_after_page_sync_and_before_stop():
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.app_shell import render_page_header\n"
        "from qx.ui.workspace_context import sync_context\n"
        "render_page_header(st, 'Research', '')\n"
        "sync_context(st, symbol='XLE', snapshot='93')\n"
        "st.stop()\n"
    )
    app.query_params.update(dict(universe="sp500", symbol="MSFT", etf="XLK", period="2y",
                                 as_of="2026-09-10", snapshot="92"))
    app.run()
    assert not app.exception
    summaries = [item.value for item in app.markdown if 'aria-label="Workspace context"' in item.value]
    assert len(summaries) == 1
    assert "Ticker: XLE" in summaries[0] and "Ticker: MSFT" not in summaries[0]
    assert "Report snapshot: 93" in summaries[0]
    assert "Universe: sp500" in summaries[0] and "As of: 2026-09-10" in summaries[0]


def test_shell_summary_clears_without_an_empty_markdown_element():
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from qx.ui.app_shell import render_page_header\n"
        "from qx.ui.workspace_context import sync_context\n"
        "render_page_header(st, 'Research', '')\n"
        "sync_context(st, symbol='')\n"
    )
    app.query_params.update({"symbol": "MSFT"})
    app.run()
    assert not app.exception
    assert not any('aria-label="Workspace context"' in item.value for item in app.markdown)
    assert len(app.markdown) == 1
