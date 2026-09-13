"""Add local, date-aligned price evidence without mutating cached fund data."""

from pathlib import Path
import re
from typing import Any

import pandas as pd

from qx.data.cache import _cache_symbol, _read_cached_bars
from qx.market.dashboard_metrics import metrics


def enrich_holdings(payload: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    def read(symbol: str) -> pd.DataFrame | None:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", symbol):
            return None
        try:
            return _read_cached_bars(cache_dir / f"{_cache_symbol(symbol)}_1y.csv")
        except (OSError, ValueError, KeyError, TypeError):
            return None

    spy = read("SPY")
    rows = []
    for holding in payload["rows"]:
        row = {**holding, "analytics": None}
        bars = read(str(holding["symbol"]))
        if spy is not None and bars is not None:
            try:
                calculated = metrics(bars, spy)
                row["analytics"] = {key: calculated[key] for key in
                                    ("rs_change", "rs_days", "up_down", "up_days", "down_days", "as_of")}
                row["analytics"]["source"] = bars.attrs.get("provenance", {}).get("actual_source", "unknown")
                row["analytics"]["status"] = "CACHED_UNVERIFIED"
            except (ValueError, KeyError, TypeError):
                pass
        rows.append(row)
    return {**payload, "rows": rows,
            "analytics_coverage": sum(row["analytics"] is not None for row in rows)}
