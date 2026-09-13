from pathlib import Path
from sqlite3 import DatabaseError
from typing import Any

import pandas as pd

from qx.storage.command_center import SQLiteCommandCenterSnapshotRepository
from qx.ui.app_shell import ensure_app_styles, render_bullet_list
from qx.ui.formatting import display_frame, format_timestamp
from qx.ui.today_state import render_today_identity, selected_today_context, today_snapshots
from qx.ui.workspace_context import workspace_url


def watchlist_changes(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, Any]]:
    def keyed(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(row["symbol"]): row for row in payload.get("watchlist", []) if isinstance(row, dict) and row.get("symbol")}
    latest, earlier = keyed(current), keyed(previous)
    rows = []
    for symbol in sorted(latest.keys() | earlier.keys()):
        before, after = earlier.get(symbol), latest.get(symbol)
        state_before = (before or {}).get("readiness_label", "Not listed")
        state_after = (after or {}).get("readiness_label", "Not listed")
        change = "Added" if before is None else "Removed" if after is None else "State changed" if state_before != state_after else "Unchanged"
        if change != "Unchanged":
            rows.append({"symbol": symbol, "change": change, "previous_state": state_before, "current_state": state_after})
    return rows


def _load(streamlit: Any) -> tuple[Any, Any, dict[str, str]]:
    ensure_app_styles(streamlit)
    context = selected_today_context(streamlit)
    repository = SQLiteCommandCenterSnapshotRepository(Path("data/scanner_history.db"))
    try:
        rows = today_snapshots(repository, context)
    except (ValueError, OSError, DatabaseError):
        streamlit.error("Saved report could not be read. No current data is substituted.")
        return repository, None, context
    if not rows:
        streamlit.info("No saved report matches this universe, period, date, and snapshot selection.")
        streamlit.link_button("Overview", workspace_url("command_center", context))
        return repository, None, context
    render_today_identity(streamlit, rows[0])
    return repository, rows[0], context


def render_changes_page(streamlit: Any) -> None:
    streamlit.subheader("Changes")
    repository, snapshot, context = _load(streamlit)
    if snapshot is None:
        return
    try:
        previous = today_snapshots(repository, context, previous_to=snapshot)
    except (ValueError, OSError, DatabaseError):
        streamlit.error("The earlier saved report could not be read. Comparison is unavailable.")
        return
    if not previous:
        streamlit.info("No earlier report with the same universe, period, and requested source is available.")
        return
    earlier = previous[0]
    streamlit.caption(f"Compared with report #{earlier.id}, created {format_timestamp(earlier.created_at)}. Changes describe saved outputs, not verified market moves.")
    summary = [{"field": key, "previous": earlier.payload.get("summary", {}).get(key), "current": snapshot.payload.get("summary", {}).get(key)}
               for key in ("regime_label", "risk_level", "spx_bias", "volatility_context")]
    streamlit.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)
    rows = watchlist_changes(snapshot.payload, earlier.payload)
    streamlit.subheader("Watchlist changes")
    if rows:
        streamlit.dataframe(display_frame(pd.DataFrame(rows), columns=list(rows[0])), width="stretch", hide_index=True)
    else:
        streamlit.info("No additions, removals, or readiness-state changes between these reports.")
    streamlit.link_button("Scan history", workspace_url("run_history", context, history_view="Scans"))


def render_preparation_page(streamlit: Any) -> None:
    streamlit.subheader("Preparation")
    _, snapshot, context = _load(streamlit)
    if snapshot is not None:
        render_bullet_list(streamlit, [str(item) for item in snapshot.payload.get("action_plan", [])], empty="No preparation actions were recorded in this report.")
        with streamlit.expander("Report priorities"):
            render_bullet_list(streamlit, [str(item) for item in snapshot.payload.get("priorities", [])])
    links = streamlit.columns(3)
    links[0].link_button("Preparation jobs", workspace_url("jobs", context, job_view="Pipeline"))
    links[1].link_button("Schedule", workspace_url("jobs", context, job_view="Schedule"))
    links[2].link_button("Run history", workspace_url("run_history", context, history_view="Workflows"))
