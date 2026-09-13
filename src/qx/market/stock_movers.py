"""Read-only stock movers from cached membership and aligned daily closes."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from qx.data.cache import _cache_symbol, _read_cached_bars
from qx.data.metadata import SymbolMetadataStore
from qx.data.membership import membership_provenance, membership_symbols
from qx.market.dashboard_metrics import metrics, closes
from qx.market.sessions import _schedule

UNIVERSES = {"sp500": "S&P 500", "sp100": "S&P 100", "nasdaq_100": "Nasdaq 100", "dow_jones": "Dow Jones"}


def stock_movers(cache: Path, universe: str, *, price_cache: Path | None = None) -> dict[str, Any]:
    if universe not in UNIVERSES:
        raise ValueError("Unsupported universe")
    membership = (price_cache / "symbols.csv") if price_cache is not None else cache.parent / f"{universe}_symbols.csv"
    symbols = membership_symbols(membership.read_bytes())
    now = datetime.now(timezone.utc)
    schedule = _schedule(now.astimezone(ZoneInfo("America/New_York")).date())
    eligible = schedule.loc[schedule["market_close"] + pd.Timedelta(minutes=30) <= pd.Timestamp(now)].index

    def read(symbol: str) -> pd.DataFrame:
        for period in ("2y", "1y"):
            path = (price_cache or cache) / f"{_cache_symbol(symbol)}_{period}.csv"
            if path.exists():
                bars = _read_cached_bars(path)
                # Daily timestamps label sessions; preserve the provider's date.
                bars.index = pd.DatetimeIndex(pd.DatetimeIndex(bars.index).date)
                return bars.loc[bars.index.isin(eligible)].tail(22)
        raise ValueError("Missing price cache")

    spy = read("SPY")
    summary = metrics(spy, spy)
    metadata = SymbolMetadataStore(cache.parent / "symbol_metadata.csv")
    rows = []
    for symbol in symbols:
        info = metadata.get(symbol)
        row: dict[str, Any] = {"etf": symbol, "sector": info.sector, "name": info.name}
        try:
            bars = read(symbol)
            prices = closes(bars)
            if not prices.index.equals(spy.index):
                raise ValueError("Unmatched session dates")
            daily = float(prices.iloc[-1] / prices.iloc[-2] - 1)
            row.update(as_of=summary["as_of"], return_1d=daily,
                       excess_1d=daily - summary["return_1d"])
            row["source"] = bars.attrs.get("provenance", {}).get("actual_source", "unknown")
        except (OSError, ValueError, TypeError, KeyError):
            pass
        rows.append(row)
    provenance = membership_provenance(membership)
    return {"rows": rows, "universe": len(symbols), "benchmark_metrics": summary,
            "membership_provenance": provenance,
            "membership_updated": datetime.fromtimestamp(membership.stat().st_mtime, timezone.utc).isoformat(),
            "membership_status": provenance["status"]}
