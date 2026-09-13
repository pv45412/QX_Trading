from typing import Any

from qx.data.cache_status import CacheHealth
from qx.ui.formatting import format_timestamp


def render_cache_readiness_panel(streamlit: Any, *, health: CacheHealth, overnight_log: Any) -> None:
    """Render a consistent cache freshness panel for operational pages."""
    cols = streamlit.columns(4)
    cols[0].metric("Cache", health.label)
    cols[1].metric("Coverage", f"{health.coverage:.1%}")
    cols[2].metric("Latest Cache", friendly_iso_time(health.latest_modified_at))
    cols[3].metric("Overnight Log", log_size_label(overnight_log))

    message = cache_readiness_message(health)
    if health.ready:
        streamlit.success(message)
    elif health.stale:
        streamlit.warning(message)
    else:
        streamlit.info(message)


def cache_readiness_message(health: CacheHealth) -> str:
    detail = health.message
    if not health.latest_modified_at:
        return detail
    return f"{detail} Latest cache update: {friendly_iso_time(health.latest_modified_at)}."


def friendly_iso_time(value: str) -> str:
    return format_timestamp(value) if value else "n/a"


def log_size_label(status: Any) -> str:
    if not status.exists:
        return "Missing"
    if status.empty:
        return "Empty"
    return f"{status.size_bytes:,} bytes"
