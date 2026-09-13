from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from qx.data.universe import UNIVERSE_OPTIONS
from qx.storage.command_center import SQLiteCommandCenterSnapshotRepository, StoredCommandCenterSnapshot, snapshot_is_stale
from qx.ui.formatting import format_timestamp
from qx.ui.workspace_context import read_context


def today_snapshots(
    repository: SQLiteCommandCenterSnapshotRepository, context: dict[str, str], *,
    data_source: str | None = None, previous_to: StoredCommandCenterSnapshot | None = None,
) -> list[StoredCommandCenterSnapshot]:
    universe = context.get("universe", "sp500")
    label = next((name for name, code in UNIVERSE_OPTIONS.items() if code == universe), universe)
    if universe == "scanner_review":
        label = "Saved scanner names"
    deadline = None
    if context.get("as_of"):
        next_day = date.fromisoformat(context["as_of"]) + timedelta(days=1)
        deadline = datetime.combine(next_day, time(), tzinfo=ZoneInfo("America/New_York")).astimezone(UTC).isoformat()
    selected_id = int(context["snapshot"]) if context.get("snapshot") and previous_to is None else None
    return repository.list_snapshots(
        limit=1, universes=(universe, label), period=context.get("period", "2y"),
        data_source=previous_to.data_source if previous_to else data_source,
        snapshot_id=selected_id, created_before=deadline,
        before_id=previous_to.id if previous_to else None,
    )


def render_today_identity(streamlit: Any, snapshot: StoredCommandCenterSnapshot) -> None:
    streamlit.caption(f"Report #{snapshot.id} | {snapshot.universe} | {snapshot.period} | Created {format_timestamp(snapshot.created_at)}")
    streamlit.caption(f"Requested source: {snapshot.data_source}. Report creation time is not a verified market-bar timestamp.")
    if snapshot_is_stale(snapshot):
        streamlit.warning("Historical report. Refresh is explicit; this view does not verify current market conditions.")


def selected_today_context(streamlit: Any) -> dict[str, str]:
    return read_context(getattr(streamlit, "query_params", {}))
