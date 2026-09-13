from datetime import datetime, timezone

import pandas as pd


def valid_provenance(value: object) -> bool:
    """Validate the v1 metadata shape; this does not establish market freshness."""
    if not isinstance(value, dict):
        return False
    version = value.get("schema_version")
    if type(version) is not int or version != 1:
        return False
    source = value.get("actual_source")
    if not isinstance(source, str) or not source.strip():
        return False
    if type(value.get("fallback_used")) is not bool:
        return False
    retrieved = value.get("retrieved_at")
    if not isinstance(retrieved, str):
        return False
    try:
        timestamp = datetime.fromisoformat(retrieved)
        if timestamp.utcoffset() is None:
            return False
        if "last_bar_label" not in value:
            return False
        label = value["last_bar_label"]
        if label is not None:
            if not isinstance(label, str):
                return False
            datetime.fromisoformat(label)
    except ValueError:
        return False
    return True


def tag_bars(
    bars: pd.DataFrame, provider: object, *, fallback_used: bool = False
) -> pd.DataFrame:
    """Attach per-response evidence without mutable provider-wide state."""
    result = bars.copy()
    source = getattr(provider, "provider_name", "unknown")
    result.attrs["provenance"] = {
        "schema_version": 1,
        "actual_source": source,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        # A daily date is a bar label, not a claim of session completeness.
        "last_bar_label": (
            bars.index.max().isoformat()
            if isinstance(bars.index, pd.DatetimeIndex) and any(bars.index.notna())
            else None
        ),
        "fallback_used": fallback_used,
    }
    return result
