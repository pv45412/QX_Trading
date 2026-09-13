from dataclasses import dataclass
from html import escape
from importlib import import_module
import sys
from textwrap import dedent
from typing import Any, Callable, Protocol, cast

from qx.ui.workspace_context import render_workspace_context


class StreamlitLike(Protocol):
    def markdown(self, body: str, unsafe_allow_html: bool = False) -> None: ...
    def caption(self, body: str) -> None: ...


@dataclass(frozen=True)
class AppPage:
    title: str
    caption: str
    render: object


def lazy_page_renderer(module_name: str, function_name: str) -> Callable[[Any], None]:
    def render(streamlit: Any) -> None:
        module = import_module(module_name)
        page_render = cast(Callable[[Any], None], getattr(module, function_name))
        page_render(streamlit)

    return render


def run_standalone_page(title: str, caption: str, render: Callable[[Any], None]) -> None:
    # Streamlit executes native page scripts as __main__; imports must never render UI.
    if sys._getframe(1).f_globals.get("__name__") != "__main__":
        return
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return
    if get_script_run_ctx() is None:
        return
    streamlit = import_module("streamlit")
    streamlit.set_page_config(page_title=title, layout="wide")
    render_page_header(cast(Any, streamlit), title, caption)
    render(streamlit)


def render_page_header(streamlit: StreamlitLike, title: str, caption: str) -> None:
    inject_app_styles(streamlit)
    render_workspace_context(streamlit)
    streamlit.markdown(
        f"""
        <section class="qx-page-header">
            <h1>{escape(title)}</h1>
            <p>{escape(caption)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(streamlit: StreamlitLike, title: str, caption: str = "") -> None:
    """Render a compact, consistent section heading inside app pages."""
    caption_html = f"<p>{escape(caption)}</p>" if caption else ""
    streamlit.markdown(
        f"""
        <section class="qx-section-header">
            <h2>{escape(title)}</h2>
            {caption_html}
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_bullet_list(streamlit: StreamlitLike, items: list[str] | tuple[str, ...], *, empty: str = "No items.") -> None:
    """Render a consistent compact action/note list."""
    if not items:
        streamlit.markdown(f'<div class="qx-empty">{escape(empty)}</div>', unsafe_allow_html=True)
        return
    rows = "\n".join(f"<li>{escape(str(item))}</li>" for item in items)
    streamlit.markdown(f'<ul class="qx-action-list">{rows}</ul>', unsafe_allow_html=True)


def ensure_app_styles(streamlit: StreamlitLike) -> None:
    inject_app_styles(streamlit)


def page_slug(title: str) -> str:
    return (
        title.lower()
        .replace("/", "")
        .replace("&", "and")
        .replace(" ", "_")
        .replace("__", "_")
    )


def inject_app_styles(streamlit: StreamlitLike) -> None:
    styles = dedent(
        """
        <style>
        :root {
            --qx-bg: #0e1117;
            --qx-sidebar-bg: #13181f;
            --qx-sidebar-border: #282e38;
            --qx-sidebar-ink: #e6e9ee;
            --qx-sidebar-muted: #9da8b8;
            --qx-ink: #e6e9ee;
            --qx-muted: #9da8b8;
            --qx-border: #282e38;
            --qx-panel: #13181f;
            --qx-panel-soft: #171c24;
            --qx-soft: #171c24;
            --qx-accent: #3478ff;
            --qx-accent-strong: #78b6ff;
            --qx-accent-soft: #182b3f;
            --qx-positive: #28c49a;
            --qx-warning: #d9bd7f;
            --qx-danger: #ee6975;
            --qx-active: #0891b2;
            --qx-admin: #7c3aed;
            --qx-shadow: none;
        }
        html, body, [data-testid="stAppViewContainer"] {
            background: var(--qx-bg);
        }
        .block-container {
            max-width: 100%;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
            padding-top: 3rem;
            padding-bottom: 1.4rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.72rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.72rem;
        }
        .stDeployButton,
        .stAppDeployButton,
        [data-testid="stHeaderActionElements"],
        [data-testid="stSidebarNav"],
        [data-testid="stToolbarActions"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu {
            display: none !important;
            height: 0 !important;
            visibility: hidden !important;
        }
        [data-testid="stHeader"] {
            background: var(--qx-bg);
            height: 2.5rem;
        }
        /* Streamlit places the reopen button inside stToolbar. Hide actions, not its parent. */
        [data-testid="stToolbar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            visibility: visible !important;
        }
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapseButton"] button {
            /* Keep essential controls usable after late component styles and font changes. */
            min-width: max(44px, 2.75rem) !important;
            min-height: max(44px, 2.75rem) !important;
        }
        [data-testid="stExpandSidebarButton"]:focus-visible,
        [data-testid="stSidebarCollapsedControl"] button:focus-visible,
        [data-testid="stSidebarCollapseButton"] button:focus-visible {
            outline: 2px solid var(--qx-accent-strong);
            outline-offset: 2px;
        }
        button[title="Deploy"],
        button[aria-label="Deploy"],
        a[title="Deploy"],
        a[aria-label="Deploy"] {
            display: none !important;
            visibility: hidden !important;
        }
        section[data-testid="stSidebar"] {
            background: var(--qx-sidebar-bg);
            border-right: 1px solid var(--qx-sidebar-border);
        }
        section[data-testid="stSidebar"] > div {
            padding-top: 0.65rem;
        }
        .qx-sidebar-brand {
            margin: 0.05rem 0 0.1rem;
            color: var(--qx-sidebar-ink);
            font-size: 1.02rem;
            font-weight: 800;
            letter-spacing: 0;
        }
        .qx-sidebar-caption {
            margin: 0 0 0.8rem;
            color: var(--qx-sidebar-muted);
            font-size: 0.74rem;
            line-height: 1.25;
        }
        section[data-testid="stSidebar"] * {
            color: var(--qx-sidebar-ink);
        }
        section[data-testid="stSidebar"] [role="radiogroup"] label,
        section[data-testid="stSidebar"] [data-baseweb="radio"] {
            color: var(--qx-sidebar-ink);
        }
        section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {
            border-color: #64748b;
        }
        section[data-testid="stSidebar"] [data-baseweb="radio"] [aria-checked="true"],
        section[data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div {
            border-color: var(--qx-accent);
        }
        section[data-testid="stSidebar"] label {
            color: var(--qx-sidebar-ink);
            font-weight: 600;
            font-size: 0.78rem;
        }
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
        section[data-testid="stSidebar"] textarea,
        section[data-testid="stSidebar"] input {
            border-radius: 8px;
            border-color: #263247;
            background-color: var(--qx-panel-soft);
            color: var(--qx-sidebar-ink);
        }
        div[data-testid="stSegmentedControl"] {
            margin: 0.15rem 0 0.65rem;
        }
        div[data-testid="stSegmentedControl"] button {
            border-radius: 8px;
            border-color: var(--qx-border);
            color: var(--qx-ink);
            font-weight: 700;
        }
        div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {
            background: var(--qx-accent);
            border-color: var(--qx-accent);
            color: #ffffff;
        }
        div[role="radiogroup"][aria-label="View"] {
            gap: 0.35rem;
            margin: 0.1rem 0 0.65rem;
        }
        div[role="radiogroup"][aria-label="View"] label {
            background: var(--qx-panel);
            border: 1px solid var(--qx-border);
            border-radius: 8px;
            padding: 0.28rem 0.55rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        div[role="radiogroup"][aria-label="View"] label:has(input:checked) {
            background: var(--qx-accent-soft);
            border-color: var(--qx-accent);
            color: var(--qx-accent-strong);
        }
        .qx-page-header {
            margin: 0 0 0.45rem;
            padding-bottom: 0.38rem;
            border-bottom: 1px solid var(--qx-border);
        }
        .qx-workspace-context {
            margin: 0.45rem 0;
            color: var(--qx-muted);
            font-size: 0.78rem;
            overflow-wrap: anywhere;
        }
        .qx-page-header h1 {
            margin: 0;
            color: var(--qx-ink);
            font-size: 1.55rem;
            font-weight: 800;
            line-height: 1.08;
            letter-spacing: 0;
        }
        .qx-page-header p {
            margin: 0.28rem 0 0;
            color: var(--qx-muted);
            font-size: 0.82rem;
        }
        .qx-section-header {
            margin: 0.55rem 0 0.42rem;
        }
        .qx-section-header h2 {
            margin: 0;
            color: var(--qx-ink);
            font-size: 1.18rem;
            font-weight: 800;
            line-height: 1.15;
            letter-spacing: 0;
        }
        .qx-section-header p {
            margin: 0.2rem 0 0;
            color: var(--qx-muted);
            font-size: 0.78rem;
            line-height: 1.35;
        }
        div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--qx-border);
            border-radius: 8px;
            background: var(--qx-panel);
            box-shadow: var(--qx-shadow);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 0.82rem 0.92rem;
        }
        div[data-testid="stMetric"] {
            background: var(--qx-panel);
            border: 0;
            border-left: 2px solid var(--qx-border);
            border-radius: 0;
            padding: 0.52rem 0.64rem;
            box-shadow: var(--qx-shadow);
        }
        div[data-testid="stMetric"] label {
            color: var(--qx-muted);
            font-size: 0.72rem;
            font-weight: 650;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--qx-ink);
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.18;
        }
        h2, h3 {
            color: var(--qx-ink);
            letter-spacing: 0;
        }
        h2 {
            font-size: 1.22rem;
            margin: 0.45rem 0 0.35rem;
        }
        h3 {
            font-size: 1.03rem;
            margin: 0.35rem 0 0.25rem;
        }
        div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] p {
            color: var(--qx-muted);
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--qx-border);
            border-radius: 8px;
            overflow: hidden;
            background: var(--qx-panel);
            box-shadow: var(--qx-shadow);
            font-size: 0.8rem;
        }
        div[data-testid="stDataFrame"] [role="columnheader"] {
            background: var(--qx-panel-soft);
            color: var(--qx-muted);
            font-weight: 700;
        }
        div[data-testid="stDataFrame"] [role="gridcell"],
        div[data-testid="stDataFrame"] [role="columnheader"] {
            line-height: 1.2;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.18rem;
            border-bottom: 1px solid var(--qx-border);
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 7px 7px 0 0;
            padding: 0.34rem 0.72rem;
            color: var(--qx-muted);
        }
        .stTabs [aria-selected="true"] {
            color: var(--qx-accent-strong);
            background: var(--qx-accent-soft);
        }
        div[data-testid="stExpander"] {
            border: 1px solid var(--qx-border);
            border-radius: 8px;
            background: var(--qx-panel);
            box-shadow: var(--qx-shadow);
        }
        div[data-testid="stExpander"] summary {
            min-height: 2.25rem;
        }
        .qx-action-list {
            margin: 0.25rem 0 1rem;
            padding: 0;
            list-style: none;
        }
        .qx-action-list li {
            margin: 0.32rem 0;
            padding: 0.48rem 0.66rem;
            border: 0;
            border-bottom: 1px solid var(--qx-border);
            border-radius: 0;
            background: transparent;
            color: var(--qx-ink);
            line-height: 1.35;
        }
        .qx-action-list li::before {
            content: "";
            display: inline-block;
            width: 0.45rem;
            height: 0.45rem;
            margin-right: 0.55rem;
            border-radius: 999px;
            background: var(--qx-accent);
            vertical-align: 0.08rem;
        }
        .qx-empty {
            margin: 0.25rem 0 1rem;
            padding: 0.58rem 0.72rem;
            border: 1px dashed var(--qx-border);
            border-radius: 7px;
            color: var(--qx-muted);
            background: var(--qx-soft);
        }
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 8px;
            font-weight: 650;
            border: 1px solid var(--qx-border);
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
            min-height: 2.25rem;
            padding: 0.35rem 0.75rem;
        }
        .stButton > button[kind="primary"],
        .stButton > button[data-testid="baseButton-primary"] {
            background: var(--qx-accent);
            border-color: var(--qx-accent);
            color: #ffffff;
        }
        .stButton > button[kind="primary"]:hover,
        .stButton > button[data-testid="baseButton-primary"]:hover {
            background: #2563eb;
            border-color: var(--qx-accent-strong);
            color: #ffffff;
        }
        div[data-testid="stAlert"] {
            border-radius: 6px;
            border-color: var(--qx-border);
        }
        div[data-testid="stMetricValue"] > div {
            white-space: normal;
            overflow-wrap: anywhere;
        }
        [data-testid="stMetricLabel"] p,
        button p {
            white-space: normal;
            overflow-wrap: anywhere;
        }
        .stTabs [data-baseweb="tab-list"] {
            overflow-x: auto;
            scrollbar-width: thin;
        }
        .stTabs [data-baseweb="tab"] { flex-shrink: 0; }
        @media (max-width: 760px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: min(100%, 280px); flex: 1 1 280px;
            }
        }
        .qx-note {
            padding: 0.58rem 0.72rem;
            border: 1px solid #bae6fd;
            border-radius: 8px;
            background: var(--qx-accent-soft);
            color: var(--qx-ink);
            line-height: 1.4;
        }
        .qx-badge {
            display: inline-block;
            padding: 0.18rem 0.5rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 750;
            line-height: 1.2;
        }
        .qx-bull {
            background: rgba(22, 163, 74, 0.12);
            border: 1px solid rgba(22, 163, 74, 0.25);
            color: var(--qx-positive);
        }
        .qx-bear {
            background: rgba(220, 38, 38, 0.12);
            border: 1px solid rgba(220, 38, 38, 0.25);
            color: var(--qx-danger);
        }
        .qx-watch {
            background: rgba(217, 119, 6, 0.12);
            border: 1px solid rgba(217, 119, 6, 0.25);
            color: var(--qx-warning);
        }
        .qx-active {
            background: rgba(8, 145, 178, 0.12);
            border: 1px solid rgba(8, 145, 178, 0.25);
            color: var(--qx-active);
        }
        .qx-admin {
            background: rgba(124, 58, 237, 0.12);
            border: 1px solid rgba(124, 58, 237, 0.25);
            color: var(--qx-admin);
        }
        .qx-neutral {
            background: rgba(100, 116, 139, 0.12);
            border: 1px solid rgba(100, 116, 139, 0.25);
            color: var(--qx-muted);
        }
        .qx-futures-context,
        .qx-futures-strip,
        .qx-market-strip,
        .qx-decision-grid,
        .qx-plan-grid,
        .qx-alternative-grid,
        .qx-at-glance-grid,
        .qx-opening-grid {
            display: grid;
            gap: 0.55rem;
            margin: 0.48rem 0;
        }
        .qx-futures-context {
            grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
        }
        .qx-futures-strip {
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        }
        .qx-futures-board { margin: 0.32rem 0 0.85rem; }
        .qx-product-header { display: flex; justify-content: space-between; align-items: baseline; gap: 0.8rem; margin: 0.1rem 0 0.25rem; padding-bottom: 0.45rem; border-bottom: 1px solid var(--qx-border); }
        .qx-product-header span { display: block; color: var(--qx-muted); font-size: 0.7rem; font-weight: 800; text-transform: uppercase; }
        .qx-product-header strong { display: block; margin-top: 0.1rem; color: var(--qx-ink); font-size: 1.25rem; }
        .qx-product-header em { color: var(--qx-muted); font-size: 0.73rem; font-style: normal; }
        .qx-workspace-banner { display: flex; justify-content: space-between; align-items: baseline; gap: 0.8rem; margin: 0.2rem 0 0.36rem; padding-bottom: 0.48rem; border-bottom: 1px solid var(--qx-border); }
        .qx-workspace-banner span { display: block; color: var(--qx-accent-strong); font-size: 0.78rem; font-weight: 800; text-transform: uppercase; }
        .qx-workspace-banner strong { display: block; margin-top: 0.15rem; color: var(--qx-ink); font-size: 1.2rem; }
        .qx-workspace-banner em { color: var(--qx-muted); font-size: 0.73rem; font-style: normal; }
        .qx-playbook { margin: 0.32rem 0 0.85rem; }
        .qx-playbook-intro { max-width: 58rem; margin: 0.1rem 0 0.75rem; color: var(--qx-muted); font-size: 0.84rem; line-height: 1.45; }
        .qx-playbook-summary { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0; border: 1px solid var(--qx-border); border-radius: 8px; background: var(--qx-panel-soft); }
        .qx-playbook-summary div { min-width: 0; padding: 0.66rem 0.78rem; border-right: 1px solid var(--qx-border); }
        .qx-playbook-summary div:last-child { border-right: 0; }
        .qx-playbook-summary span, .qx-playbook-card-head span { display: block; color: var(--qx-muted); font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
        .qx-playbook-summary strong { display: block; margin-top: 0.15rem; color: var(--qx-ink); font-size: 1.12rem; }
        .qx-playbook-summary em { display: block; margin-top: 0.12rem; color: var(--qx-muted); font-size: 0.72rem; font-style: normal; }
        .qx-playbook-card { margin-top: 0.62rem; padding: 0.8rem; border: 1px solid var(--qx-border); border-radius: 8px; background: var(--qx-panel); box-shadow: var(--qx-shadow); }
        .qx-playbook-card-head { display: flex; justify-content: space-between; gap: 0.8rem; align-items: flex-start; }
        .qx-playbook-card-head strong { display: block; margin-top: 0.15rem; color: var(--qx-ink); font-size: 1.03rem; }
        .qx-playbook-card-head em { color: var(--qx-muted); font-size: 0.72rem; font-style: normal; }
        .qx-playbook-requirements { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 0.7rem; border-top: 1px solid var(--qx-border); border-bottom: 1px solid var(--qx-border); }
        .qx-playbook-requirements div { min-width: 0; padding: 0.68rem; border-right: 1px solid var(--qx-border); }
        .qx-playbook-requirements div:last-child { border-right: 0; }
        .qx-playbook-requirements b { display: inline-flex; align-items: center; justify-content: center; width: 1.25rem; height: 1.25rem; margin-bottom: 0.36rem; border-radius: 50%; background: rgba(59, 130, 246, 0.16); color: var(--qx-accent-strong); font-size: 0.7rem; }
        .qx-playbook-requirements span { display: block; color: var(--qx-ink); font-size: 0.82rem; font-weight: 700; }
        .qx-playbook-requirements em { display: block; margin-top: 0.2rem; color: var(--qx-muted); font-size: 0.74rem; font-style: normal; line-height: 1.35; }
        .qx-playbook-empty { margin-top: 0.68rem; padding: 0.58rem 0.65rem; border-left: 3px solid var(--qx-accent); background: var(--qx-panel-soft); color: var(--qx-muted); font-size: 0.8rem; }
        .qx-board-heading { display: flex; justify-content: space-between; gap: 0.8rem; align-items: baseline; margin: 0.2rem 0 0.4rem; }
        .qx-board-heading span, .qx-snapshot-history > span, .qx-at-a-glance > span {
            display: block; color: var(--qx-muted); font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        }
        .qx-board-heading strong { display: block; margin-top: 0.12rem; color: var(--qx-ink); font-size: 1.1rem; }
        .qx-board-heading em { color: var(--qx-muted); font-size: 0.72rem; font-style: normal; text-align: right; }
        .qx-market-strip {
            grid-template-columns: repeat(5, minmax(0, 1fr));
            padding: 0.62rem 0.78rem;
            border: 1px solid var(--qx-border);
            border-radius: 8px;
            background: var(--qx-panel-soft);
        }
        .qx-market-strip div { min-width: 0; padding: 0 0.72rem; border-right: 1px solid var(--qx-border); }
        .qx-market-strip div:first-child { padding-left: 0; }
        .qx-market-strip div:last-child { padding-right: 0; border-right: 0; }
        .qx-market-strip span, .qx-verdict-card span, .qx-evidence-ladder > span, .qx-plan-head span,
        .qx-plan-grid span, .qx-alternative-section > span, .qx-alternative-card span {
            display: block; color: var(--qx-muted); font-size: 0.7rem; font-weight: 700; line-height: 1.15;
            text-transform: uppercase; letter-spacing: 0;
        }
        .qx-market-strip strong { display: block; margin-top: 0.18rem; color: var(--qx-ink); font-size: 0.94rem; line-height: 1.15; }
        .qx-decision-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
        .qx-verdict-card, .qx-evidence-ladder, .qx-plan-card, .qx-alternative-card {
            border: 1px solid var(--qx-border); border-radius: 8px; background: var(--qx-panel); box-shadow: var(--qx-shadow);
        }
        .qx-verdict-card { min-height: 12.2rem; padding: 1.15rem; border-left-width: 4px; }
        .qx-verdict-card strong { display: block; margin-top: 2rem; color: var(--qx-ink); font-size: 1.8rem; line-height: 1.1; }
        .qx-verdict-card p { margin: 0.55rem 0 0; color: var(--qx-muted); font-size: 0.82rem; line-height: 1.4; }
        .qx-evidence-ladder { padding: 0.8rem; }
        .qx-evidence-ladder > span { margin: 0.1rem 0 0.52rem; }
        .qx-gate-count { display: block; color: var(--qx-ink); font-size: 2rem; line-height: 1; margin: 0.18rem 0 0.58rem; }
        .qx-gate-count small { color: var(--qx-muted); font-size: 0.9rem; }
        .qx-ladder-row { display: flex; justify-content: space-between; gap: 0.6rem; padding: 0.5rem 0.58rem; margin-top: 0.32rem; border-radius: 5px; font-size: 0.8rem; }
        .qx-ladder-row b { font-size: 0.72rem; }
        .qx-ladder-ready { background: rgba(22, 163, 74, 0.12); color: var(--qx-positive); }
        .qx-ladder-pending { background: rgba(100, 116, 139, 0.12); color: var(--qx-muted); }
        .qx-plan-card { margin-top: 0.05rem; padding: 0.76rem; }
        .qx-plan-head { display: flex; justify-content: space-between; gap: 0.8rem; align-items: flex-start; }
        .qx-plan-head strong { display: block; margin-top: 0.18rem; color: var(--qx-ink); font-size: 1.03rem; }
        .qx-plan-head em { color: var(--qx-muted); font-size: 0.72rem; font-style: normal; }
        .qx-plan-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 0.72rem; }
        .qx-plan-grid div { min-width: 0; padding: 0.55rem 0.64rem; background: var(--qx-panel-soft); border-right: 1px solid var(--qx-border); }
        .qx-plan-grid div:first-child { border-radius: 5px 0 0 5px; }
        .qx-plan-grid div:last-child { border-radius: 0 5px 5px 0; border-right: 0; }
        .qx-plan-grid strong { display: block; margin-top: 0.18rem; color: var(--qx-ink); font-size: 0.95rem; line-height: 1.15; }
        .qx-plan-note, .qx-plan-empty { margin: 0.62rem 0 0; color: var(--qx-muted); font-size: 0.8rem; }
        .qx-snapshot-history { margin-top: 0.04rem; padding: 0.62rem 0.72rem; border: 1px solid var(--qx-border); border-radius: 8px; background: var(--qx-panel); }
        .qx-snapshot-history strong { display: inline-block; margin-top: 0.28rem; color: var(--qx-ink); font-size: 0.84rem; }
        .qx-snapshot-history em { display: block; margin-top: 0.28rem; color: var(--qx-muted); font-size: 0.75rem; font-style: normal; }
        .qx-at-a-glance { margin-top: 0.12rem; }
        .qx-at-a-glance > span { margin-bottom: 0.42rem; }
        .qx-at-glance-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        .qx-at-glance-card { min-height: 3.8rem; padding: 0.55rem 0.64rem; background: var(--qx-panel-soft); border-left: 3px solid var(--qx-border); }
        .qx-at-glance-card span { display: block; color: var(--qx-muted); font-size: 0.7rem; }
        .qx-at-glance-card strong { display: block; margin-top: 0.18rem; color: var(--qx-ink); font-size: 0.85rem; line-height: 1.18; }
        .qx-alternative-section { margin-top: 0.12rem; }
        .qx-alternative-section > span { margin-bottom: 0.42rem; }
        .qx-alternative-grid { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
        .qx-alternative-card { min-height: 4.1rem; padding: 0.55rem 0.64rem; }
        .qx-alternative-card strong { display: block; margin-top: 0.16rem; color: var(--qx-ink); font-size: 0.87rem; }
        .qx-alternative-card em { display: block; margin-top: 0.22rem; color: var(--qx-muted); font-size: 0.76rem; font-style: normal; }
        .qx-context-chip,
        .qx-future-tile,
        .qx-opening-read,
        .qx-opening-metric {
            border: 1px solid var(--qx-border);
            border-radius: 8px;
            background: var(--qx-panel);
            box-shadow: var(--qx-shadow);
        }
        .qx-opening-read {
            margin: 0.62rem 0;
            padding: 0.68rem 0.78rem;
            border-left-width: 4px;
        }
        .qx-opening-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.52rem;
        }
        .qx-opening-head span,
        .qx-opening-metric span {
            display: block;
            color: var(--qx-muted);
            font-size: 0.72rem;
            line-height: 1.2;
        }
        .qx-opening-head strong {
            display: block;
            margin-top: 0.1rem;
            color: var(--qx-ink);
            font-size: 1.16rem;
            line-height: 1.15;
        }
        .qx-opening-head em {
            color: var(--qx-muted);
            font-size: 0.72rem;
            font-style: normal;
            line-height: 1.2;
            text-align: right;
        }
        .qx-opening-grid {
            grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
        }
        .qx-opening-metric {
            box-shadow: none;
            min-height: 3.4rem;
            padding: 0.46rem 0.55rem;
        }
        .qx-opening-metric strong {
            display: block;
            margin-top: 0.16rem;
            color: var(--qx-ink);
            font-size: 0.98rem;
            line-height: 1.16;
        }
        .qx-opening-read p {
            margin: 0.48rem 0 0;
            color: var(--qx-muted);
            font-size: 0.82rem;
            line-height: 1.42;
        }
        .qx-context-chip {
            min-height: 3.05rem;
            padding: 0.5rem 0.62rem;
        }
        .qx-context-chip span,
        .qx-future-head span,
        .qx-future-sub {
            color: var(--qx-muted);
            font-size: 0.72rem;
            line-height: 1.2;
        }
        .qx-context-chip strong {
            display: block;
            margin-top: 0.16rem;
            color: var(--qx-ink);
            font-size: 0.92rem;
            line-height: 1.16;
        }
        .qx-future-tile {
            min-height: 5rem;
            padding: 0.58rem 0.66rem;
            border-left-width: 4px;
        }
        .qx-future-head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.45rem;
        }
        .qx-future-head strong {
            color: var(--qx-ink);
            font-size: 0.98rem;
        }
        .qx-future-main {
            margin-top: 0.22rem;
            color: var(--qx-ink);
            font-size: 1.2rem;
            font-weight: 800;
            line-height: 1.08;
        }
        .qx-future-status {
            display: inline-block;
            margin-top: 0.35rem;
            padding: 0.12rem 0.42rem;
            border-radius: 999px;
            background: rgba(100, 116, 139, 0.1);
            color: var(--qx-muted);
            font-size: 0.7rem;
            font-weight: 750;
        }
        .qx-tone-positive {
            border-left-color: var(--qx-positive);
        }
        .qx-tone-positive .qx-future-main,
        .qx-tone-positive .qx-future-status {
            color: var(--qx-positive);
        }
        .qx-tone-positive .qx-future-status {
            background: rgba(22, 163, 74, 0.11);
        }
        .qx-tone-negative {
            border-left-color: var(--qx-danger);
        }
        .qx-tone-negative .qx-future-main,
        .qx-tone-negative .qx-future-status {
            color: var(--qx-danger);
        }
        .qx-tone-negative .qx-future-status {
            background: rgba(220, 38, 38, 0.1);
        }
        .qx-tone-neutral {
            border-left-color: var(--qx-muted);
        }
        .qx-page-header { margin-bottom: 0.35rem; }
        .qx-page-header h1 { font-size: 1.5rem; letter-spacing: 0; }
        .qx-page-header p:empty { display: none; }
        [data-testid="stVerticalBlockBorderWrapper"] { box-shadow: none; }
        [data-testid="stMetric"] { box-shadow: none; border-radius: 0; }
        h2, h3 { letter-spacing: 0 !important; }
        @media (max-width: 768px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
            .qx-market-strip, .qx-plan-grid, .qx-at-glance-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .qx-market-strip div:nth-child(2) { border-right: 0; }
            .qx-market-strip div:nth-child(n + 3) { margin-top: 0.56rem; }
            .qx-market-strip div:nth-child(3) { padding-left: 0; }
            .qx-decision-grid { grid-template-columns: 1fr; }
            .qx-plan-grid div:nth-child(2) { border-right: 0; }
            .qx-plan-grid div:nth-child(n + 3) { margin-top: 1px; }
            .qx-plan-grid div:first-child, .qx-plan-grid div:last-child { border-radius: 0; }
            .qx-board-heading { align-items: flex-start; flex-direction: column; gap: 0.2rem; }
            .qx-board-heading em { text-align: left; }
            .qx-product-header { align-items: flex-start; flex-direction: column; gap: 0.18rem; }
            .qx-workspace-banner { align-items: flex-start; flex-direction: column; gap: 0.18rem; }
            .qx-playbook-summary { grid-template-columns: 1fr; }
            .qx-playbook-summary div { border-right: 0; border-bottom: 1px solid var(--qx-border); }
            .qx-playbook-summary div:last-child { border-bottom: 0; }
            .qx-playbook-requirements { grid-template-columns: 1fr; }
            .qx-playbook-requirements div { border-right: 0; border-bottom: 1px solid var(--qx-border); }
            .qx-playbook-requirements div:last-child { border-bottom: 0; }
        }
        </style>
        """
    )
    html = getattr(streamlit, "html", None)
    if callable(html):
        html(styles)
        return
    markdown = getattr(streamlit, "markdown")
    markdown(styles, unsafe_allow_html=True)
