from pathlib import Path
from typing import Any

import pandas as pd

from qx.storage.command_center import (
    SQLiteCommandCenterSnapshotRepository,
    StoredCommandCenterSnapshot,
    snapshot_freshness_label,
    snapshot_is_stale,
)
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame


SCAN_HISTORY_DB = Path("data/scanner_history.db")


def render_snapshot_history_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    limit = streamlit.sidebar.slider("Command snapshots", 5, 100, 25, 5)
    repository = SQLiteCommandCenterSnapshotRepository(SCAN_HISTORY_DB)
    snapshots = repository.list_snapshots(limit=int(limit))

    streamlit.subheader("Command Snapshot History")
    streamlit.caption("Audit saved Command Center snapshots and compare today vs the previous run.")

    if not snapshots:
        streamlit.info("No Command Center snapshots saved yet. Run Command Center refresh or the prep pipeline.")
        return

    latest = snapshots[0]
    if snapshot_is_stale(latest):
        streamlit.warning(f"{snapshot_freshness_label(latest)}. Snapshot is stale.")
    else:
        streamlit.success(f"{snapshot_freshness_label(latest)}. Snapshot is current.")

    streamlit.dataframe(display_frame(_snapshot_frame(snapshots)), width="stretch", hide_index=True)

    comparison = repository.compare_latest()
    streamlit.subheader("Latest Delta")
    if comparison.current is None:
        streamlit.info("No snapshot comparison available.")
    elif comparison.previous is None:
        streamlit.info("Only one snapshot exists so far.")
    else:
        cols = streamlit.columns(6)
        cols[0].metric("Regime Changed", "Yes" if comparison.regime_changed else "No")
        cols[1].metric("Risk Changed", "Yes" if comparison.risk_changed else "No")
        cols[2].metric("SPX Bias Changed", "Yes" if comparison.spx_bias_changed else "No")
        cols[3].metric("New Watchlist", len(comparison.new_watchlist_symbols))
        cols[4].metric("New Options", len(comparison.new_option_symbols))
        cols[5].metric("Sector Changes", len(comparison.new_top_sectors) + len(comparison.removed_top_sectors))

        delta_frame = _delta_frame(comparison)
        if delta_frame.empty:
            streamlit.success("No material Command Center changes between the latest two snapshots.")
        else:
            streamlit.dataframe(display_frame(delta_frame), width="stretch", hide_index=True)
        focus_delta = _sector_focus_delta_frame(comparison)
        if not focus_delta.empty:
            with streamlit.expander("Sector Focus Changes"):
                streamlit.dataframe(display_frame(focus_delta), width="stretch", hide_index=True)

    selected_id = streamlit.selectbox(
        "Snapshot detail",
        [snapshot.id for snapshot in snapshots],
        index=0,
    )
    selected = next(snapshot for snapshot in snapshots if snapshot.id == selected_id)
    _render_snapshot_detail(streamlit, selected)


def _snapshot_frame(snapshots: list[StoredCommandCenterSnapshot]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": snapshot.id,
                "created_at": snapshot.created_at,
                "fresh": not snapshot_is_stale(snapshot),
                "source": snapshot.source,
                "universe": snapshot.universe,
                "period": snapshot.period,
                "data_source": snapshot.data_source,
                "regime": snapshot.regime_label,
                "risk": snapshot.risk_level,
                "spx_bias": snapshot.spx_bias,
                "volatility": snapshot.volatility_context,
                "watchlist": snapshot.watchlist_count,
                "option_ideas": snapshot.option_ideas_count,
                "saved_options": snapshot.saved_options_count,
            }
            for snapshot in snapshots
        ]
    )


def _delta_frame(comparison: Any) -> pd.DataFrame:
    rows = (
        [{"type": "new_watchlist", "value": symbol} for symbol in comparison.new_watchlist_symbols]
        + [{"type": "removed_watchlist", "value": symbol} for symbol in comparison.removed_watchlist_symbols]
        + [{"type": "new_options", "value": symbol} for symbol in comparison.new_option_symbols]
        + [{"type": "removed_options", "value": symbol} for symbol in comparison.removed_option_symbols]
        + [{"type": "new_top_sector", "value": sector} for sector in comparison.new_top_sectors]
        + [{"type": "removed_top_sector", "value": sector} for sector in comparison.removed_top_sectors]
    )
    return pd.DataFrame(rows)


def _sector_focus_frame(payload: dict[str, Any]) -> pd.DataFrame:
    raw_focus = payload.get("sector_focus", [])
    if not isinstance(raw_focus, list):
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "lens": str(row.get("lens", "")),
                "symbols": str(row.get("symbols", "")),
                "read": str(row.get("read", "")),
            }
            for row in raw_focus
            if isinstance(row, dict)
        ]
    )


def _sector_focus_delta_frame(comparison: Any) -> pd.DataFrame:
    current = getattr(comparison, "current", None)
    previous = getattr(comparison, "previous", None)
    if current is None or previous is None:
        return pd.DataFrame()
    current_focus = _focus_by_lens(current.payload)
    previous_focus = _focus_by_lens(previous.payload)
    rows = []
    for lens in sorted(set(current_focus) | set(previous_focus)):
        current_symbols = current_focus.get(lens, "")
        previous_symbols = previous_focus.get(lens, "")
        if current_symbols != previous_symbols:
            rows.append(
                {
                    "lens": lens,
                    "previous": previous_symbols or "None",
                    "current": current_symbols or "None",
                }
            )
    return pd.DataFrame(rows)


def _focus_by_lens(payload: dict[str, Any]) -> dict[str, str]:
    frame = _sector_focus_frame(payload)
    if frame.empty:
        return {}
    return {
        str(row["lens"]): str(row["symbols"])
        for _, row in frame.iterrows()
        if str(row["lens"])
    }


def _render_snapshot_detail(streamlit: Any, snapshot: StoredCommandCenterSnapshot) -> None:
    payload = snapshot.payload
    options = payload.get("options", {}) if isinstance(payload.get("options", {}), dict) else {}
    streamlit.subheader(f"Snapshot {snapshot.id} Detail")
    tabs = streamlit.tabs(["Watchlist", "Sector Focus", "Sectors", "Options", "Action Plan", "Raw JSON"])
    with tabs[0]:
        streamlit.dataframe(
            display_frame(pd.DataFrame(payload.get("watchlist", []))),
            width="stretch",
            hide_index=True,
        )
    with tabs[1]:
        streamlit.dataframe(
            display_frame(_sector_focus_frame(payload)),
            width="stretch",
            hide_index=True,
        )
    with tabs[2]:
        streamlit.dataframe(
            display_frame(pd.DataFrame(payload.get("sectors", []))),
            width="stretch",
            hide_index=True,
        )
    with tabs[3]:
        option_rows = [
            *list(options.get("directional_ideas", [])),
            *list(options.get("rectangle_ideas", [])),
            *list(options.get("saved_ideas", [])),
        ]
        streamlit.dataframe(
            display_frame(pd.DataFrame(option_rows).drop(columns=["payload"], errors="ignore")),
            width="stretch",
            hide_index=True,
        )
    with tabs[4]:
        for item in payload.get("action_plan", []):
            streamlit.write(f"- {item}")
    with tabs[5]:
        streamlit.json(payload)


run_standalone_page(
    "Command Snapshots",
    "Review saved Command Center snapshots and latest-vs-previous deltas.",
    render_snapshot_history_page,
)
