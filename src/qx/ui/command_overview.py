from typing import Any

import pandas as pd

from qx.ui.app_shell import render_bullet_list
from qx.ui.formatting import display_frame
from qx.ui.workspace_context import read_context, render_context_links, sync_context


WATCH_COLUMNS = ["symbol", "readiness_label", "close", "trigger_level", "distance_to_trigger_pct", "risk_score"]
SECTOR_COLUMNS = ["etf", "sector", "relative_5d", "relative_20d", "rotation_status"]
OPTION_COLUMNS = ["symbol", "strategy", "action", "setup_quality", "risk_note"]


def overview_frame(rows: list[dict[str, Any]], columns: list[str], limit: int = 8) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    return display_frame(frame, columns=columns, max_rows=limit)


def filter_watchlist(rows: list[dict[str, Any]], query: str, status: str) -> list[dict[str, Any]]:
    term = query.strip().casefold()
    return [row for row in rows
            if (status == "All statuses" or row.get("readiness_label") == status)
            and (not term or any(term in str(row.get(key, "")).casefold()
                                 for key in ("symbol", "name", "sector")))]


def render_command_overview(st: Any, payload: dict[str, Any]) -> None:
    summary = payload.get("summary", {})
    metrics = st.columns(4)
    for col, label, key in zip(metrics, ["Regime", "Risk", "SPX bias", "Volatility"],
                               ["regime_label", "risk_level", "spx_bias", "volatility_context"], strict=True):
        col.metric(label, str(summary.get(key) or "Unavailable"))

    st.subheader("Priority watchlist")
    rows = payload.get("watchlist", [])
    if rows:
        search_col, status_col = st.columns([2, 1])
        query = search_col.text_input("Search watchlist", placeholder="Symbol, company or sector", key="command_search")
        statuses = ["All statuses", *sorted({str(row["readiness_label"]) for row in rows if row.get("readiness_label")})]
        status = status_col.selectbox("Status", statuses, key="command_status")
        matches = filter_watchlist(rows, query, status)
        st.caption(f"{len(matches)} of {len(rows)} candidates")
        st.dataframe(overview_frame(matches, WATCH_COLUMNS, len(matches)), width="stretch", hide_index=True,
                     height=min(380, 36 * (len(matches) + 1) + 4))
        if not matches:
            st.info("No candidates match these filters.")
        symbols = list(dict.fromkeys(str(row["symbol"]) for row in matches if row.get("symbol")))
        if symbols:
            _render_selected_watchlist(st, symbols, matches)
    else:
        st.info("No watchlist candidates in this snapshot.")

    left, right = st.columns(2)
    with left:
        st.subheader("Sector leadership")
        sectors = payload.get("sectors", [])
        if sectors:
            st.dataframe(overview_frame(sectors, SECTOR_COLUMNS, 5), width="stretch", hide_index=True)
        else:
            st.info("Sector data unavailable.")
    with right:
        st.subheader("Priorities")
        render_bullet_list(st, [str(item) for item in payload.get("priorities", [])][:4])

    st.subheader("Options shortlist")
    options = payload.get("options", {})
    source = st.segmented_control("Ideas", ["Directional", "Rectangle", "Saved"], default="Directional",
                                  key="command_ideas_view")
    key = {"Directional": "directional_ideas", "Rectangle": "rectangle_ideas", "Saved": "saved_ideas"}.get(source, "directional_ideas")
    ideas = options.get(key, [])
    if ideas:
        st.dataframe(overview_frame(ideas, OPTION_COLUMNS), width="stretch", hide_index=True)
        with st.expander("Full idea evidence"):
            frame = pd.DataFrame(ideas)
            st.dataframe(display_frame(frame, columns=[str(c) for c in frame if c != "payload"]), width="stretch", hide_index=True)
    else:
        st.info("No ideas in this snapshot.")
    with st.expander("Operational checklist"):
        render_bullet_list(st, [str(item) for item in payload.get("action_plan", [])])


def _render_selected_watchlist(st: Any, symbols: list[str], matches: list[dict[str, Any]]) -> None:
    context = read_context(getattr(st, "query_params", {}))
    preferred = context.get("symbol")
    selected = st.selectbox("Symbol details", symbols, index=symbols.index(preferred) if preferred in symbols else None,
                            placeholder="Select a candidate", key="command_detail_symbol")
    if selected is None:
        if preferred:
            st.caption(f"{preferred} is not in this filtered shortlist. Navigation selection is unchanged.")
        return
    sync_context(st, symbol=str(selected))
    detail = next(row for row in matches if str(row.get("symbol")) == selected)
    st.write(f"**{selected}**")
    render_context_links(st, str(selected))
    st.caption(" / ".join(str(detail[key]) for key in ("name", "sector", "readiness_label") if detail.get(key)))
    detail_frame = overview_frame([detail], WATCH_COLUMNS)
    numbers = st.columns(3)
    for col, label in zip(numbers, ["Close", "Trigger", "To Trigger"], strict=True):
        col.metric(label, str(detail_frame.iloc[0].get(label, "Unavailable")))
    with st.expander(f"{selected} evidence", expanded=False):
        formatted = display_frame(pd.DataFrame([detail]), columns=list(detail))
        st.dataframe(pd.DataFrame({"Field": list(formatted), "Value": [str(v) for v in formatted.iloc[0]]}),
                     width="stretch", hide_index=True)
