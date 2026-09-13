from importlib import import_module
from html import escape
from urllib.parse import parse_qs, urlparse
from typing import Any, Callable, cast

from qx.data.universe import UNIVERSE_OPTIONS
from qx.ui.app_shell import AppPage, page_slug, render_page_header
from qx.ui.pages import PAGES
from qx.ui.workspace_context import markets_url, read_context, workspace_url


WORKSPACE_TABS = {
    "Today": ["Command Center", "Morning Report", "Daily Workflow"],
    "Scanner": ["Scanner", "Broad Watchlist", "Heatmap"],
    "Markets": ["SPX / NQ Futures", "Sector Rotation"],
    "Research": ["Ticker History", "Options Ideas", "Options Flow", "Liquidity Map", "Backtest", "Strategy Lab"],
    "Journal": ["Idea Tracking", "Outcome Journal"],
    "System": ["Data Cache", "Schwab API", "Jobs", "Run History", "Strategy Rules"],
}
WORKSPACE_CAPTIONS = dict.fromkeys(WORKSPACE_TABS, "")
PAGE_GROUPS = WORKSPACE_TABS


PAGE_ROUTE_TABS = {
    "command_center": "Command Center",
    "daily_workflow": "Daily Workflow",
    "broad_watchlist": "Broad Watchlist",
    "watchlist": "Broad Watchlist",
    "spx_nq_futures": "SPX / NQ Futures",
    "morning_report": "Morning Report",
    "scan": "Scanner",
    "qx": "Scanner",
    "scanner": "Scanner",
    "backtest": "Backtest",
    "strategy_lab": "Strategy Lab",
    "sector_rotation": "Sector Rotation",
    "heatmap": "Heatmap",
    "options_ideas": "Options Ideas",
    "ticker_history": "Ticker History",
    "options_flow": "Options Flow",
    "liquidity_map": "Liquidity Map",
    "liquidity": "Liquidity Map",
    "idea_tracking": "Idea Tracking",
    "performance": "Idea Tracking",
    "journal": "Outcome Journal",
    "jobs": "Jobs",
    "pipeline": "Jobs",
    "pipeline_control": "Jobs",
    "automation_control": "Jobs",
    "data_cache": "Data Cache",
    "schwab": "Schwab API",
    "strategy_rules": "Strategy Rules",
    "run_history": "Run History",
    "workflow_history": "Run History",
    "command_snapshots": "Run History",
    "history": "Run History",
}

DISPLAY_TITLES = {"Command Center": "Overview", "Morning Report": "Changes", "Daily Workflow": "Preparation",
                  "SPX / NQ Futures": "ES / NQ Context", "Sector Rotation": "Sector Archive",
                  "Ticker History": "Instrument", "Performance": "Idea Tracking"}
LEGACY_VIEWS = {"pipeline": ("job_view", "Pipeline"), "pipeline_control": ("job_view", "Pipeline"),
                "automation_control": ("job_view", "Schedule"), "history": ("history_view", "Scans"),
                "workflow_history": ("history_view", "Workflows"), "command_snapshots": ("history_view", "Snapshots")}


PAGE_ROUTE_TABS["spx_dashboard"] = "SPX / NQ Futures"
PAGE_ROUTE_ALIASES = {
    route: next(group for group, titles in WORKSPACE_TABS.items() if title in titles)
    for route, title in PAGE_ROUTE_TABS.items()
}


def main() -> None:
    """Run the optional Streamlit dashboard."""
    streamlit = cast(Any, import_module("streamlit"))

    route = _requested_route_key(streamlit)
    sidebar_routes = {"heatmap", "options_flow", "run_history", "history", "workflow_history", "command_snapshots",
                      "data_cache", "jobs", "pipeline", "pipeline_control", "automation_control"}
    streamlit.set_page_config(page_title="SCANNER", layout="wide", initial_sidebar_state="auto" if route in sidebar_routes else "collapsed")
    if route in LEGACY_VIEWS:
        key, value = LEGACY_VIEWS[route]
        streamlit.query_params[key] = value
    page = _select_page(streamlit, _workspace_pages(PAGES))
    navigation = streamlit.empty()
    _render_workspace_navigation(navigation, page.title, read_context(streamlit.query_params))
    render_page_header(streamlit, page.title, page.caption)
    render = cast(Callable[[Any], None], page.render)
    try:
        render(streamlit)
    finally:
        _render_workspace_navigation(navigation, page.title, read_context(streamlit.query_params))


def _render_workspace_navigation(streamlit: Any, current: str, context: dict[str, str] | None = None) -> None:
    destinations = [("Today", "command_center"), ("Markets", "relative_strength"), ("Scanner", "scan"),
                    ("Research", "ticker_history"), ("Journal", "idea_tracking"), ("System", "data_cache")]
    links = []
    for label, route in destinations:
        active = ' aria-current="page"' if label == current else ''
        url = markets_url(context) if route == "relative_strength" else workspace_url(route, context)
        links.append(f'<a href="{escape(url, quote=True)}" target="_self"{active}>{label}</a>')
    streamlit.markdown('''<style>
    .qx-workspace-nav {display:flex;flex-wrap:wrap;gap:4px 16px;border-bottom:1px solid #303640;padding:8px 0;}
    .qx-workspace-nav a {color:#b5bfcd!important;text-decoration:none;padding:6px 4px;font-size:13px;}
    .qx-workspace-nav a[aria-current="page"] {color:#74adff!important;border-bottom:2px solid #3478ff;}
    .qx-workspace-nav a:hover,.qx-workspace-nav a:focus-visible {text-decoration:underline;}
    .qx-view-nav {display:flex;flex-wrap:wrap;gap:4px 12px;margin:0 0 16px;border-bottom:1px solid #303640;}
    .qx-view-nav a {padding:8px 4px;color:#b5bfcd!important;text-decoration:none;font-size:13px;}
    .qx-view-nav a[aria-current="page"] {color:#74adff!important;border-bottom:2px solid #3478ff;}
    .qx-view-nav a:focus-visible {outline:2px solid #74adff;outline-offset:2px;}
    </style><nav class="qx-workspace-nav" aria-label="Workspace pages">'''
                       + ''.join(links) + '</nav>', unsafe_allow_html=True)


def _select_page(streamlit: Any, pages: list[AppPage]) -> AppPage:
    routed_page = _page_from_current_path(streamlit, pages)
    initial_page = routed_page if routed_page is not None else pages[0]
    streamlit.sidebar.markdown(
        """
        <div class="qx-sidebar-brand">SCANNER</div>
        <div class="qx-sidebar-caption">QuantX local trading workspace</div>
        """,
        unsafe_allow_html=True,
    )
    return initial_page


def _workspace_pages(pages: list[AppPage]) -> list[AppPage]:
    return [
        AppPage(
            title=workspace,
            caption=WORKSPACE_CAPTIONS[workspace],
            render=_workspace_renderer(tab_pages),
        )
        for workspace, tab_pages in _pages_by_group(pages).items()
    ]


def _pages_by_group(pages: list[AppPage]) -> dict[str, list[AppPage]]:
    pages_by_title = {page.title: page for page in pages}
    grouped: dict[str, list[AppPage]] = {}
    for group, titles in WORKSPACE_TABS.items():
        grouped[group] = [pages_by_title[title] for title in titles if title in pages_by_title]
    remaining = [page for page in pages if page.title not in {title for titles in WORKSPACE_TABS.values() for title in titles}]
    if remaining:
        grouped.setdefault("System", []).extend(remaining)
    return {group: group_pages for group, group_pages in grouped.items() if group_pages}


def _group_for_page(title: str) -> str:
    for group, titles in WORKSPACE_TABS.items():
        if title in titles:
            return group
    return "System"


def _workspace_renderer(pages: list[AppPage]) -> Callable[[Any], None]:
    def render(streamlit: Any) -> None:
        page_titles = [page.title for page in pages]
        requested_tab = _requested_tab_title(streamlit)
        selected_title = requested_tab if requested_tab in page_titles else page_titles[0]
        navigation = streamlit.empty()
        selected_page = pages[page_titles.index(selected_title)]
        page_render = cast(Callable[[Any], None], selected_page.render)
        def update_navigation() -> None:
            context = read_context(getattr(streamlit, "query_params", {}))
            links = []
            if selected_title in WORKSPACE_TABS["Markets"]:
                links.append(f'<a href="{escape(markets_url(context), quote=True)}" target="_self">Relative Strength</a>')
            for title in page_titles:
                route = next(key for key, value in PAGE_ROUTE_TABS.items() if value == title)
                active = ' aria-current="page"' if title == selected_title else ''
                url = escape(workspace_url(route, context), quote=True)
                links.append(f'<a href="{url}" target="_self"{active}>{escape(DISPLAY_TITLES.get(title, title))}</a>')
            navigation.markdown('<nav class="qx-view-nav" aria-label="Workspace views">' + ''.join(links) + '</nav>', unsafe_allow_html=True)
        update_navigation()
        try:
            if _accepts_universe(streamlit, selected_title):
                page_render(streamlit)
        finally:
            update_navigation()

    return render


def _accepts_universe(streamlit: Any, title: str) -> bool:
    indexes = set(UNIVERSE_OPTIONS.values())
    supported = {name: indexes | {"custom"} for name in
                 ("Scanner", "Options Ideas", "Backtest", "Strategy Lab")}
    supported["Broad Watchlist"] = indexes | {"custom", "scanner_review"}
    supported.update({name: indexes | {"scanner_review"} for name in
                      ("Command Center", "Morning Report", "Daily Workflow")})
    context = read_context(getattr(streamlit, "query_params", {}))
    universe = context.get("universe")
    if title not in supported or not universe or universe in supported[title]:
        return True
    streamlit.warning(f"The selected universe ({universe}) is not supported by {DISPLAY_TITLES.get(title, title)}. It has not been replaced.")
    route = next(key for key, value in PAGE_ROUTE_TABS.items() if value == title)
    streamlit.link_button("Use S&P 500", workspace_url(route, context, universe="sp500", snapshot=""))
    return False


def _sync_selected_route(streamlit: Any, title: str) -> None:
    route = next((key for key, value in PAGE_ROUTE_TABS.items() if value == title), None)
    query_params = getattr(streamlit, "query_params", None)
    if route is not None and query_params is not None:
        streamlit.session_state["_consumed_route"] = route
        if query_params.get("page") != route:
            query_params["page"] = route


def _module_selector(streamlit: Any, page_titles: list[str], default_title: str | None = None) -> str:
    default = default_title if default_title in page_titles else page_titles[0]
    key = "_view_" + page_slug(page_titles[0])
    if default_title in page_titles:
        streamlit.session_state[key] = default
    segmented_control = getattr(streamlit, "segmented_control", None)
    if callable(segmented_control):
        selected = segmented_control(
            "View",
            page_titles,
            default=default,
            key=key,
            label_visibility="collapsed",
        )
        return cast(str, selected or page_titles[0])
    return cast(
        str,
        streamlit.radio(
            "View",
            page_titles,
            horizontal=True,
            key=key,
            label_visibility="collapsed",
        ),
    )


def _initial_page_index(streamlit: Any, pages: list[AppPage]) -> int:
    routed_page = _page_from_current_path(streamlit, pages)
    if routed_page is not None:
        return pages.index(routed_page)
    return 0


def _page_from_current_path(streamlit: Any, pages: list[AppPage]) -> AppPage | None:
    path = _requested_route_key(streamlit)
    if not path:
        return None
    alias = PAGE_ROUTE_ALIASES.get(path)
    if alias is not None:
        titles = [page.title for page in pages]
        if alias in titles:
            return pages[titles.index(alias)]
    slugs = [page_slug(page.title) for page in pages]
    return pages[slugs.index(path)] if path in slugs else None


def _requested_route_key(streamlit: Any) -> str:
    query_params = getattr(streamlit, "query_params", {})
    query_page = query_params.get("page", "")
    if query_page:
        return str(query_page).strip().strip("/")
    current_url = getattr(getattr(streamlit, "context", None), "url", "")
    parsed = urlparse(str(current_url))
    path = parsed.path.strip("/")
    if path:
        return path
    query_page = parse_qs(parsed.query).get("page", [""])[0]
    if not query_page:
        query_params = getattr(streamlit, "query_params", {})
        try:
            query_page = query_params.get("page", "")
        except AttributeError:
            query_page = ""
    return str(query_page).strip().strip("/")


def _requested_tab_title(streamlit: Any) -> str | None:
    route_key = _requested_route_key(streamlit)
    return PAGE_ROUTE_TABS.get(route_key)


if __name__ == "__main__":
    main()
