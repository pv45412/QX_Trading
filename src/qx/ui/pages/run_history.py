from html import escape
from typing import Any

from qx.ui.app_shell import ensure_app_styles, lazy_page_renderer, run_standalone_page
from qx.ui.workspace_context import workspace_url


HISTORY_VIEWS = {
    "Scans": ("qx.ui.pages.history", "render_history_page"),
    "Workflows": ("qx.ui.pages.workflow_history", "render_workflow_history_page"),
    "Snapshots": ("qx.ui.pages.snapshot_history", "render_snapshot_history_page"),
}


def render_run_history_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    query = getattr(streamlit, "query_params", {})
    requested = query.get("history_view", "Scans")
    selected = requested if isinstance(requested, str) and requested in HISTORY_VIEWS else "Scans"
    streamlit.subheader("Run History")
    links = []
    for label in HISTORY_VIEWS:
        url = workspace_url("run_history", query, history_view=label)
        active = ' aria-current="page"' if label == selected else ''
        links.append(f'<a href="{escape(url, quote=True)}" target="_self"{active}>{label}</a>')
    streamlit.markdown(
        '<nav class="qx-workspace-nav" aria-label="Run history views">'
        + " &nbsp; ".join(links) + '</nav>',
        unsafe_allow_html=True,
    )
    module, renderer = HISTORY_VIEWS[selected]
    lazy_page_renderer(module, renderer)(streamlit)


run_standalone_page("Run History", "", render_run_history_page)
