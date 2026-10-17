"""Ranked Schwab mover subsets, never index membership or breadth."""
from datetime import datetime, timezone
import math
from typing import Any

from qx.brokers.schwab.client import SchwabApiClient
from qx.data.metadata import SymbolMetadata, SymbolMetadataStore
from qx.data.quotes import QuoteProvider


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Invalid numeric value")
    return float(value)


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    return _number(value)


def _text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def normalize_screeners(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("screeners")
    if not isinstance(items, list) or len(items) > 10:
        raise ValueError("Unexpected movers response")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid screener")
        symbol = item.get("symbol")
        last, change = _number(item.get("lastPrice")), _number(item.get("netChange"))
        normalized_symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
        if not normalized_symbol or normalized_symbol in seen:
            raise ValueError("Invalid mover identity or price")
        reference = last - change
        if last <= 0 or not math.isfinite(reference) or reference <= 0:
            raise ValueError("Invalid reference price")
        provider_percent = _optional_number(item.get("netPercentChange"))
        daily = change / reference
        if not math.isfinite(daily):
            raise ValueError("Invalid return")
        seen.add(normalized_symbol)
        result.append(
            {
                "symbol": normalized_symbol,
                "description": _text(item.get("description")),
                "last": last,
                "change": change,
                "return": daily,
                "provider_net_percent_change": provider_percent,
                "volume": _optional_number(item.get("volume")),
                "total_volume": _optional_number(item.get("totalVolume")),
                "trades": _optional_number(item.get("trades")),
                "market_share": _optional_number(item.get("marketShare")),
            }
        )
    return result


def fetch_top_movers(
    client: SchwabApiClient,
    *,
    metadata_store: SymbolMetadataStore | None = None,
    benchmark_quote_provider: QuoteProvider | None = None,
) -> dict[str, Any]:
    retrieved_at = datetime.now(timezone.utc)
    groups = {}
    for key, sort in (("highest", "PERCENT_CHANGE_UP"), ("lowest", "PERCENT_CHANGE_DOWN")):
        payload = client.get("/marketdata/v1/movers/$SPX", params={"sort": sort, "frequency": 0})
        rows = normalize_screeners(payload)
        groups[key] = sorted(rows, key=lambda row: row["return"], reverse=key == "highest")

    benchmark_return = None
    benchmark_as_of = None
    if benchmark_quote_provider is not None:
        try:
            benchmark = benchmark_quote_provider.get_quote("SPY")
            if benchmark.symbol.strip().upper() == "SPY":
                benchmark_return = benchmark.change_pct
                benchmark_as_of = benchmark.timestamp
        except Exception:
            benchmark_return = None
            benchmark_as_of = None
    if benchmark_return is not None and not math.isfinite(benchmark_return):
        benchmark_return = None

    metadata_as_of = None
    if metadata_store is not None and metadata_store.cache_path.exists():
        metadata_as_of = datetime.fromtimestamp(
            metadata_store.cache_path.stat().st_mtime,
            timezone.utc,
        )

    enriched_groups: dict[str, list[dict[str, Any]]] = {}
    for key, rows in groups.items():
        enriched_groups[key] = [
            _enrich_mover(
                row,
                metadata_store=metadata_store,
                benchmark_return=benchmark_return,
                retrieved_at=retrieved_at,
            )
            for row in rows
        ]

    unique_rows: dict[str, dict[str, Any]] = {}
    for row in [*enriched_groups["highest"], *enriched_groups["lowest"]]:
        unique_rows.setdefault(row["symbol"], row)
    return {
        "rows": list(unique_rows.values()),
        "groups": enriched_groups,
        "source": "schwab",
        "index": "$SPX",
        "retrieved_at": retrieved_at.isoformat(),
        "market_as_of": benchmark_as_of.isoformat() if benchmark_as_of else None,
        "metadata_as_of": metadata_as_of.isoformat() if metadata_as_of else None,
        "benchmark": {
            "symbol": "SPY",
            "return_1d": benchmark_return,
            "source": (
                getattr(benchmark_quote_provider, "provider_name", "schwab")
                if benchmark_return is not None
                else "UNAVAILABLE"
            ),
            "as_of": benchmark_as_of.isoformat() if benchmark_as_of else None,
        },
        "scope": "Ranked subsets only; not full-index breadth or membership",
    }


def _enrich_mover(
    row: dict[str, Any],
    *,
    metadata_store: SymbolMetadataStore | None,
    benchmark_return: float | None,
    retrieved_at: datetime,
) -> dict[str, Any]:
    metadata = SymbolMetadata(symbol=row["symbol"])
    if metadata_store is not None:
        try:
            metadata = metadata_store.get(row["symbol"])
        except (OSError, ValueError, TypeError, KeyError):
            metadata = SymbolMetadata(symbol=row["symbol"])
    schwab_name = _text(row.get("description"))
    metadata_name = _known_metadata_value(metadata.name)
    sector = _known_metadata_value(metadata.sector)
    industry = _known_metadata_value(metadata.industry)
    return_1d = row["return"]
    return {
        **row,
        "name": schwab_name or metadata_name,
        "name_source": "schwab:movers.description" if schwab_name else (
            "local_symbol_metadata_cache" if metadata_name else "UNAVAILABLE"
        ),
        "sector": sector,
        "industry": industry,
        "sector_source": "local_symbol_metadata_cache" if sector else "UNAVAILABLE",
        "return_1d": return_1d,
        "excess_1d": (
            return_1d - benchmark_return if benchmark_return is not None else None
        ),
        "benchmark_symbol": "SPY",
        "benchmark_return_1d": benchmark_return,
        "benchmark_source": "schwab:quote:SPY" if benchmark_return is not None else "UNAVAILABLE",
        "as_of": retrieved_at.isoformat(),
        "freshness": "CURRENT_REQUEST",
        "source": "schwab",
    }


def _known_metadata_value(value: str) -> str | None:
    normalized = value.strip()
    return normalized if normalized.lower() not in {"", "unknown", "nan"} else None
