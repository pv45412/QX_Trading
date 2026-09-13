"""Evidence for the exact daily series used by the ES/NQ context workspace.

Bar labels and retrieval times do not establish completed futures sessions.
This contract intentionally never certifies intraday or execution readiness.
"""

from datetime import datetime
from hashlib import sha256
import json
from typing import Any

import numpy as np
import pandas as pd

from qx.data.provenance import valid_provenance


def daily_series_evidence(
    symbol: str, bars: pd.DataFrame | None, *, checked_at: datetime,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    if checked_at.utcoffset() is None:
        raise ValueError("Daily evidence requires an aware clock")
    cutoff = as_of or checked_at
    if cutoff.utcoffset() is None:
        raise ValueError("Daily evidence requires an aware cutoff")
    result: dict[str, Any] = {
        "symbol": symbol,
        "interval": "1d",
        "date_cutoff": cutoff.isoformat(),
        "status": "unavailable",
        "bar_count": 0 if bars is None else len(bars),
        "latest_bar_label": None,
        "prior_bar_label": None,
        "actual_source": "unknown",
        "retrieved_at": None,
        "fallback_used": None,
        "provenance_status": "unavailable",
        "bars_sha256": None,
        "daily_facts": None,
        "chart_bars": [],
        "session_completion": "unverified",
        "freshness": "unverified",
        "contract_continuity": "unverified",
        "cash_close_synchronized": False,
        "intraday_confirmation": "unavailable",
        "live_signal_eligible": False,
    }
    if bars is None or bars.empty:
        return result
    index = bars.index
    if (not isinstance(index, pd.DatetimeIndex) or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing):
        return {**result, "status": "invalid_dates"}
    # Daily labels are not quote timestamps. Compare dates without assigning a
    # timezone to naive labels or claiming that today's session has completed.
    check_date = cutoff.astimezone(index.tz).date() if index.tz else cutoff.date()
    if index[-1].date() > check_date:
        return {**result, "status": "future_dated"}
    try:
        values = bars[["open", "high", "low", "close", "volume"]]
        if any(not pd.api.types.is_numeric_dtype(dtype)
               or pd.api.types.is_bool_dtype(dtype) for dtype in values.dtypes):
            return {**result, "status": "invalid_ohlcv"}
        if (not np.isfinite(values.to_numpy(dtype=float)).all()
                or (values[["open", "high", "low", "close"]] <= 0).any().any()
                or (values["volume"] < 0).any()
                or (values["high"] < values[["open", "close", "low"]].max(axis=1)).any()
                or (values["low"] > values[["open", "close", "high"]].min(axis=1)).any()):
            return {**result, "status": "invalid_ohlcv"}
    except (KeyError, TypeError, ValueError):
        return {**result, "status": "invalid_ohlcv"}
    result.update(
        status="daily_reference" if len(bars) >= 20 else "insufficient_history",
        latest_bar_label=index[-1].isoformat(),
        prior_bar_label=index[-2].isoformat() if len(bars) > 1 else None,
        bars_sha256=sha256(values.to_csv().encode("utf-8")).hexdigest(),
    )
    if result["status"] == "daily_reference":
        result["chart_bars"] = [
            {"bar_label": label.isoformat(), **{column: float(value) for column, value in row.items()}}
            for label, row in zip(index[-60:], values.tail(60).to_dict("records"))
        ]
        latest, prior = values.iloc[-1], values.iloc[-2]
        result["daily_facts"] = {
            "close": round(float(latest["close"]), 2),
            "prior_close": round(float(prior["close"]), 2),
            "prior_high": round(float(prior["high"]), 2),
            "prior_low": round(float(prior["low"]), 2),
            "return_1d": round(float(latest["close"] / prior["close"] - 1), 4),
        }
    provenance = bars.attrs.get("provenance")
    if isinstance(provenance, dict) and valid_provenance(provenance):
        # Metadata must describe this series, not another cached response.
        if (provenance["last_bar_label"] == result["latest_bar_label"]
                and datetime.fromisoformat(provenance["retrieved_at"]) <= checked_at):
            result.update(
                actual_source=provenance["actual_source"],
                retrieved_at=provenance["retrieved_at"],
                fallback_used=provenance["fallback_used"],
                provenance_status="recorded",
            )
        else:
            result["provenance_status"] = "metadata_mismatch"
    return result


def daily_context_evidence(
    rows: list[dict[str, Any]], *, checked_at: datetime
) -> dict[str, Any]:
    labels = [(row["latest_bar_label"], row["prior_bar_label"]) for row in rows]
    aligned = (len(rows) == 2 and all(row["status"] == "daily_reference" for row in rows)
               and labels[0] == labels[1])
    return {
        "schema_version": "qx.futures-daily-context.v1",
        "snapshot_id": sha256(json.dumps(rows, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "checked_at": checked_at.isoformat(),
        "rows": rows,
        "daily_labels_aligned": aligned,
        "live_signal_eligible": False,
        "limitations": [
            "Daily bar labels are not verified session closes or quote times.",
            "Retrieval time does not establish market freshness.",
            "Continuous-series roll handling and explicit contract continuity are unverified.",
            "No synchronized cash-close reference, intraday confirmation or trading is enabled.",
        ],
    }
