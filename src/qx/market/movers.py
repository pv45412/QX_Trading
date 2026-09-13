from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, fields
from datetime import datetime
import math

import pandas as pd

from qx.data.fundamentals import FundamentalProvider
from qx.data.metadata import SymbolMetadataStore
from qx.data.providers import MarketDataProvider
from qx.models.market import BarDataRequest
from qx.models.scan import ScanCandidate
from qx.market.sessions import completed_mover_bars


@dataclass(frozen=True)
class MarketMoverCandidate:
    symbol: str
    name: str
    sector: str
    industry: str
    price: float
    market_cap: float
    return_1d: float
    return_5d: float
    return_20d: float
    latest_volume: float
    avg_volume_20d: float
    dollar_volume: float
    relative_volume_20d: float
    close_location: float
    accumulation_ratio: float
    accumulation_score: float
    mover_score: float
    tape_status: str
    rectangle_signal: str
    rectangle_score: float
    options_quality: str
    mover_action: str
    notes: str
    bar_date: str = ""
    actual_source: str = "unknown"
    freshness: str = "Unchecked"


@dataclass(frozen=True)
class MarketMoverResult:
    candidates: list[MarketMoverCandidate]
    total_symbols: int
    failed_symbols: int
    failures: dict[str, str]


def scan_market_movers(
    symbols: Iterable[str],
    provider: MarketDataProvider,
    *,
    period: str = "2y",
    limit: int = 50,
    metadata_store: SymbolMetadataStore | None = None,
    fundamental_provider: FundamentalProvider | None = None,
    rectangle_candidates: Iterable[ScanCandidate] = (),
    max_workers: int = 12,
    enrich_metadata_limit: int = 50,
    as_of: datetime | None = None,
) -> MarketMoverResult:
    normalized_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    if limit < 1:
        raise ValueError("Result limit must be positive")
    if as_of is not None and as_of.utcoffset() is None:
        raise ValueError("Scan time must be timezone-aware")
    metadata = metadata_store or SymbolMetadataStore()
    rectangle_by_symbol = {candidate.symbol: candidate for candidate in rectangle_candidates}

    candidates: list[MarketMoverCandidate] = []
    failures: dict[str, str] = {}
    workers = max(1, min(max_workers, len(normalized_symbols) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _candidate_for_symbol,
                symbol,
                provider,
                period,
                metadata,
                rectangle_by_symbol.get(symbol),
                as_of,
            ): symbol
            for symbol in normalized_symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                candidates.append(future.result())
            except Exception as exc:
                failures[symbol] = str(exc)

    candidates.sort(key=lambda candidate: (-candidate.mover_score, candidate.symbol))
    top_candidates = candidates[:limit]
    _enrich_metadata(metadata, top_candidates, enrich_metadata_limit)
    top_candidates = [
        _candidate_with_metadata_and_fundamentals(candidate, metadata, fundamental_provider)
        for candidate in top_candidates
    ]
    return MarketMoverResult(
        candidates=top_candidates,
        total_symbols=len(normalized_symbols),
        failed_symbols=len(failures),
        failures=failures,
    )


def market_movers_frame(candidates: list[MarketMoverCandidate]) -> pd.DataFrame:
    return pd.DataFrame([candidate.__dict__ for candidate in candidates],
                        columns=[field.name for field in fields(MarketMoverCandidate)])


def market_movers_columns() -> list[str]:
    return [
        "symbol",
        "price",
        "name",
        "sector",
        "market_cap",
        "return_1d",
        "return_5d",
        "return_20d",
        "relative_volume_20d",
        "dollar_volume",
        "close_location",
        "accumulation_ratio",
        "accumulation_score",
        "tape_status",
        "rectangle_signal",
        "rectangle_score",
        "options_quality",
        "mover_action",
        "notes",
    ]


def _candidate_for_symbol(
    symbol: str,
    provider: MarketDataProvider,
    period: str,
    metadata: SymbolMetadataStore,
    rectangle: ScanCandidate | None,
    as_of: datetime | None = None,
) -> MarketMoverCandidate:
    bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
    _validate_bars(bars)
    if as_of is not None:
        bars = completed_mover_bars(bars, as_of)
    candidate = _candidate_from_bars(symbol, bars, metadata, rectangle)
    return MarketMoverCandidate(**{**candidate.__dict__, "freshness": "Session-aligned" if as_of else "Unchecked"})


def _validate_bars(bars: pd.DataFrame) -> None:
    if (not isinstance(bars.index, pd.DatetimeIndex) or bars.index.hasnans
            or not bars.index.is_unique or not bars.index.is_monotonic_increasing):
        raise ValueError("Daily dates must be valid, unique, and increasing")
    if len(bars) < 21:
        raise ValueError("At least 21 daily bars are required")
    values = bars[["open", "high", "low", "close", "volume"]].astype(float)
    if not all(math.isfinite(value) for value in values.to_numpy().flat):
        raise ValueError("OHLCV values must be finite")
    if (values[["open", "high", "low", "close"]] <= 0).any().any() or (values["volume"] < 0).any():
        raise ValueError("Prices must be positive and volume nonnegative")
    if ((values["high"] < values[["open", "close", "low"]].max(axis=1)).any()
            or (values["low"] > values[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("Invalid OHLC candle geometry")


def _candidate_from_bars(
    symbol: str,
    bars: pd.DataFrame,
    metadata: SymbolMetadataStore,
    rectangle: ScanCandidate | None,
) -> MarketMoverCandidate:
    _validate_bars(bars)

    meta = metadata.get(symbol)
    close = float(bars["close"].iloc[-1])
    latest_volume = float(bars["volume"].iloc[-1])
    avg_volume_20d = float(bars["volume"].iloc[-21:-1].mean())
    if avg_volume_20d <= 0:
        raise ValueError("Prior 20-session volume baseline is zero")
    prior = bars.iloc[-21:-1]
    dollar_volume = float((prior["close"] * prior["volume"]).mean())
    relative_volume = latest_volume / avg_volume_20d if avg_volume_20d > 0 else 0.0
    close_location = _close_location(bars)
    accumulation_ratio = _accumulation_ratio(bars)
    accumulation_score = _accumulation_score(
        return_1d=_return_over_bars(bars, 1),
        relative_volume=relative_volume,
        close_location=close_location,
        accumulation_ratio=accumulation_ratio,
    )
    mover_score = _mover_score(
        return_1d=_return_over_bars(bars, 1),
        return_5d=_return_over_bars(bars, 5),
        relative_volume=relative_volume,
        accumulation_score=accumulation_score,
        dollar_volume=dollar_volume,
    )
    rectangle_score = rectangle.setup_score if rectangle else 0.0
    return MarketMoverCandidate(
        symbol=symbol,
        name=meta.name,
        sector=meta.sector,
        industry=meta.industry,
        price=round(close, 2),
        market_cap=0.0,
        return_1d=round(_return_over_bars(bars, 1), 4),
        return_5d=round(_return_over_bars(bars, 5), 4),
        return_20d=round(_return_over_bars(bars, 20), 4),
        latest_volume=round(latest_volume, 0),
        avg_volume_20d=round(avg_volume_20d, 0),
        dollar_volume=round(dollar_volume, 0),
        relative_volume_20d=round(relative_volume, 3),
        close_location=round(close_location, 3),
        accumulation_ratio=round(accumulation_ratio, 3),
        accumulation_score=round(accumulation_score, 3),
        mover_score=round(mover_score, 3),
        tape_status=_tape_status(accumulation_score, relative_volume, close_location, _return_over_bars(bars, 1)),
        rectangle_signal=rectangle.setup_status if rectangle else "No rectangle signal",
        rectangle_score=round(rectangle_score, 3),
        options_quality=_options_quality(avg_volume_20d, dollar_volume, 0.0),
        mover_action=_mover_action(accumulation_score, relative_volume, close_location, avg_volume_20d, _return_over_bars(bars, 1), dollar_volume),
        notes=_notes(_return_over_bars(bars, 1), relative_volume, close_location, accumulation_ratio, rectangle),
        bar_date=bars.index[-1].date().isoformat(),
        actual_source=str(bars.attrs.get("provenance", {}).get("actual_source", "unknown")),
    )


def _enrich_metadata(
    metadata: SymbolMetadataStore,
    candidates: list[MarketMoverCandidate],
    limit: int,
) -> None:
    unknown = [
        candidate.symbol
        for candidate in candidates
        if candidate.name == "Unknown" or candidate.sector == "Unknown" or candidate.industry == "Unknown"
    ]
    if unknown and limit > 0:
        metadata.enrich_yfinance(unknown, max_symbols=limit)


def _candidate_with_metadata_and_fundamentals(
    candidate: MarketMoverCandidate,
    metadata: SymbolMetadataStore,
    fundamental_provider: FundamentalProvider | None,
) -> MarketMoverCandidate:
    meta = metadata.get(candidate.symbol)
    market_cap = _market_cap(candidate.symbol, fundamental_provider)
    return MarketMoverCandidate(
        **{
            **candidate.__dict__,
            "name": meta.name,
            "sector": meta.sector,
            "industry": meta.industry,
            "market_cap": round(market_cap, 0),
            "options_quality": _options_quality(candidate.avg_volume_20d, candidate.dollar_volume, market_cap),
        }
    )


def _market_cap(symbol: str, fundamental_provider: FundamentalProvider | None) -> float:
    if fundamental_provider is None:
        return 0.0
    try:
        snapshot = fundamental_provider.get_fundamentals(symbol)
    except Exception:
        return 0.0
    return float(snapshot.market_cap or 0.0)


def _return_over_bars(bars: pd.DataFrame, bars_back: int) -> float:
    if len(bars) <= bars_back:
        return 0.0
    current = float(bars["close"].iloc[-1])
    prior = float(bars["close"].iloc[-bars_back - 1])
    return (current / prior) - 1.0 if prior > 0 else 0.0


def _close_location(bars: pd.DataFrame) -> float:
    high = float(bars["high"].iloc[-1])
    low = float(bars["low"].iloc[-1])
    close = float(bars["close"].iloc[-1])
    if high <= low:
        return 0.5
    return _clamp((close - low) / (high - low))


def _accumulation_ratio(bars: pd.DataFrame) -> float:
    window = bars.tail(10)
    up_volume = float(window.loc[window["close"] > window["open"], "volume"].sum())
    down_volume = float(window.loc[window["close"] < window["open"], "volume"].sum())
    if down_volume <= 0:
        return 2.0 if up_volume > 0 else 1.0
    return up_volume / down_volume


def _accumulation_score(
    *,
    return_1d: float,
    relative_volume: float,
    close_location: float,
    accumulation_ratio: float,
) -> float:
    return _clamp(
        close_location * 0.35
        + min(relative_volume / 2.0, 1.0) * 0.25
        + _clamp((accumulation_ratio - 0.75) / 1.25) * 0.25
        + (0.15 if return_1d > 0 else 0.03)
    )


def _mover_score(
    *,
    return_1d: float,
    return_5d: float,
    relative_volume: float,
    accumulation_score: float,
    dollar_volume: float,
) -> float:
    daily_strength = _clamp(return_1d / 0.08)
    swing_strength = _clamp(return_5d / 0.15)
    liquidity = _clamp(dollar_volume / 100_000_000)
    volume_confirmation = _clamp(relative_volume / 2.0)
    return _clamp(
        daily_strength * 0.38
        + volume_confirmation * 0.24
        + accumulation_score * 0.22
        + swing_strength * 0.10
        + liquidity * 0.06
    )


def _tape_status(accumulation_score: float, relative_volume: float, close_location: float, return_1d: float) -> str:
    if close_location < 0.35 and relative_volume >= 1.2:
        return "Distribution Risk"
    if return_1d <= 0:
        return "Neutral"
    if accumulation_score >= 0.78 and relative_volume >= 1.5 and close_location >= 0.65:
        return "Accumulation Surge"
    if accumulation_score >= 0.65 and relative_volume >= 1.2:
        return "Constructive Accumulation"
    return "Neutral"


def _options_quality(avg_volume: float, dollar_volume: float, market_cap: float) -> str:
    liquid = avg_volume >= 1_000_000 and dollar_volume >= 100_000_000
    quality_cap = math.isfinite(market_cap) and market_cap >= 5_000_000_000
    if liquid and quality_cap:
        return "Underlying Liquid"
    if dollar_volume >= 50_000_000:
        return "Underlying Review"
    return "Low Underlying Liquidity"


def _mover_action(
    accumulation_score: float,
    relative_volume: float,
    close_location: float,
    avg_volume: float,
    return_1d: float,
    dollar_volume: float,
) -> str:
    if close_location < 0.35 and relative_volume >= 1.2:
        return "Distribution Risk"
    if return_1d <= 0:
        return "Monitor"
    if avg_volume < 500_000 or dollar_volume < 10_000_000:
        return "Liquidity Review"
    if accumulation_score >= 0.78 and relative_volume >= 1.5 and close_location >= 0.65:
        return "Review Now"
    if relative_volume >= 1.2 and avg_volume >= 500_000:
        return "Watch Tape"
    return "Monitor"


def _notes(
    return_1d: float,
    relative_volume: float,
    close_location: float,
    accumulation_ratio: float,
    rectangle: ScanCandidate | None,
) -> str:
    notes: list[str] = []
    if return_1d > 0:
        notes.append("positive daily mover")
    if relative_volume >= 1.5:
        notes.append("high RVOL")
    if close_location >= 0.65:
        notes.append("closed near high")
    if accumulation_ratio >= 1.2:
        notes.append("up-volume leading")
    if rectangle:
        notes.append(f"rectangle {rectangle.setup_status}")
    return ", ".join(notes) if notes else "watch for confirmation"


def _clamp(value: float) -> float:
    return max(0.0, min(value, 1.0))
