from html import escape
from typing import Any

from qx.ui.app_shell import ensure_app_styles, lazy_page_renderer, run_standalone_page
from qx.ui.workspace_context import workspace_url


JOB_VIEWS = {
    "Pipeline": ("qx.ui.pages.pipeline", "render_pipeline_page"),
    "Schedule": ("qx.ui.pages.automation_control", "render_automation_control_page"),
}


def render_jobs_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    query = getattr(streamlit, "query_params", {})
    requested = query.get("job_view", "Pipeline")
    selected = requested if isinstance(requested, str) and requested in JOB_VIEWS else "Pipeline"
    streamlit.subheader("Jobs")
    links = []
    for label in JOB_VIEWS:
        url = workspace_url("jobs", query, job_view=label)
        active = ' aria-current="page"' if label == selected else ''
        links.append(f'<a href="{escape(url, quote=True)}" target="_self"{active}>{label}</a>')
    streamlit.markdown(
        '<nav class="qx-workspace-nav" aria-label="Job views">' + " &nbsp; ".join(links) + '</nav>',
        unsafe_allow_html=True,
    )
    module, renderer = JOB_VIEWS[selected]
    lazy_page_renderer(module, renderer)(streamlit)


run_standalone_page("Jobs", "", render_jobs_page)
