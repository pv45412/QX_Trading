"""Validated navigation context shared by local workspace destinations."""

import re
from datetime import date
from html import escape
from typing import Any, Mapping
from urllib.parse import urlencode


CONTEXT_KEYS = ("universe", "sector", "symbol", "etf", "period", "as_of", "snapshot")
UNIVERSES = {"etfs", "custom", "sp500", "sp100", "nasdaq_100", "dow_jones", "russell_2000", "scanner_review"}
PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "3y", "5y", "max"}
ROUTE_ALIASES = {
    "qx": ("scan",), "scanner": ("scan",), "watchlist": ("broad_watchlist",),
    "spx_dashboard": ("spx_nq_futures",), "liquidity": ("liquidity_map",),
    "performance": ("idea_tracking",),
    "pipeline": ("jobs", "job_view", "Pipeline"),
    "pipeline_control": ("jobs", "job_view", "Pipeline"),
    "automation_control": ("jobs", "job_view", "Schedule"),
    "history": ("run_history", "history_view", "Scans"),
    "workflow_history": ("run_history", "history_view", "Workflows"),
    "command_snapshots": ("run_history", "history_view", "Snapshots"),
}
CONTEXT_LABELS = (("Universe", "universe"), ("Ticker", "symbol"), ("ETF", "etf"),
                  ("Sector", "sector"), ("Period", "period"), ("As of", "as_of"),
                  ("Report snapshot", "snapshot"))


def read_context(query: Mapping[str, Any]) -> dict[str, str]:
    context: dict[str, str] = {}
    for key in CONTEXT_KEYS:
        raw = query.get(key, "")
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if key in {"symbol", "etf"}:
            value = value.upper()
            valid = re.fullmatch(r"[A-Z0-9^/][A-Z0-9.^=/\-]{0,19}", value) is not None
        elif key == "universe":
            valid = value in UNIVERSES
        elif key == "period":
            valid = value in PERIODS
        elif key == "snapshot":
            valid = re.fullmatch(r"[0-9]{1,19}", value) is not None and 0 < int(value) < 2**63
        elif key == "as_of":
            try:
                parsed = date.fromisoformat(value)
                valid = parsed.isoformat() == value and 1900 <= parsed.year <= 2100
            except ValueError:
                valid = False
        else:
            valid = bool(value) and len(value) <= 80 and all(ch.isalnum() or ch in " &/().,-" for ch in value)
        if valid:
            context[key] = value
    return context


def workspace_url(page: str, context: Mapping[str, Any] | None = None, **updates: Any) -> str:
    values = {**(context or {}), **updates}
    route = ROUTE_ALIASES.get(page.strip().strip("/"), (page.strip().strip("/"),))
    if route[0] == "relative_strength":
        return markets_url(values)
    query = {"page": route[0], **read_context(values)}
    if len(route) == 3:
        values[route[1]] = route[2]
    for target, key, options in (("jobs", "job_view", {"Pipeline", "Schedule"}),
                                 ("run_history", "history_view", {"Scans", "Workflows", "Snapshots"})):
        if route[0] == target and isinstance(values.get(key), str) and values[key] in options:
            query[key] = values[key]
    return "?" + urlencode(query)


def markets_url(context: Mapping[str, Any] | None = None, **updates: Any) -> str:
    query = urlencode(read_context({**(context or {}), **updates}))
    return "http://127.0.0.1:5173/" + ("?" + query if query else "")


def render_context_links(streamlit: Any, symbol: str, *, snapshot: int | None = None) -> None:
    context = read_context(getattr(streamlit, "query_params", {}))
    updates: dict[str, Any] = {"symbol": symbol}
    if snapshot is not None:
        updates["snapshot"] = str(snapshot)
    links = [("Research", "ticker_history"), ("Options", "options_ideas"), ("Journal", "journal")]
    streamlit.markdown('<nav class="qx-context-links" aria-label="Selected instrument actions">' + " &nbsp; ".join(
        f'<a href="{escape(workspace_url(route, context, **(updates | ({"universe": "custom"} if route == "options_ideas" else {}))), quote=True)}" target="_self">{label}</a>'
        for label, route in links
    ) + "</nav>", unsafe_allow_html=True)


def sync_context(streamlit: Any, **updates: str) -> None:
    query = getattr(streamlit, "query_params", None)
    if query is None:
        return
    for key in CONTEXT_KEYS:
        if key in updates and updates[key] == "" and key in query:
            del query[key]
    for key, value in read_context(updates).items():
        if query.get(key) != value:
            query[key] = value
    placeholder = getattr(streamlit, "session_state", {}).get("_workspace_context_placeholder")
    if placeholder is not None:
        _render_context_summary(placeholder, read_context(query))


def _render_context_summary(target: Any, context: Mapping[str, str]) -> None:
    text = " | ".join(f"{label}: {context[key]}" for label, key in CONTEXT_LABELS if key in context)
    if not text:
        empty = getattr(target, "empty", None)
        if callable(empty):
            empty()
        return
    target.markdown(
        f'<p class="qx-workspace-context" aria-label="Workspace context">{escape(text)}</p>',
        unsafe_allow_html=True,
    )


def render_workspace_context(streamlit: Any) -> None:
    context = read_context(getattr(streamlit, "query_params", {}))
    empty = getattr(streamlit, "empty", None)
    state = getattr(streamlit, "session_state", None)
    if callable(empty) and state is not None:
        # Pages synchronize selections after the shell renders; keep this slot current.
        target = empty()
        state["_workspace_context_placeholder"] = target
    else:
        target = streamlit
    _render_context_summary(target, context)
