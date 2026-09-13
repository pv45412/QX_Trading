from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from qx.data.metadata import SymbolMetadata, SymbolMetadataStore
from qx.data.providers import MarketDataProvider
from qx.market.regime import MarketRegimeResult, analyze_market_regime
from qx.market.sector_rotation import SectorRotationResult, analyze_sector_rotation
from qx.models.market import BarDataRequest
from qx.models.scan import ScanCandidate
from qx.options.directional import analyze_directional_setup
from qx.patterns.ranking import composite_rank_score
from qx.storage.sqlite import SQLiteScanRepository

WATCHLIST_FAILURE_CACHE = Path("data/cache/watchlist_failures.csv")


@dataclass(frozen=True)
class WatchlistCandidate:
    symbol: str
    name: str
    sector: str
    industry: str
    final_score: float
    readiness_score: float
    readiness_label: str
    setup_state: str
    breakout_setup_score: float
    risk_score: float
    trigger_level: float
    distance_to_trigger_pct: float
    close_location_20d: float
    momentum_score: float
    trend_score: float
    relative_strength_score: float
    sector_score: float
    liquidity_score: float
    volume_score: float
    directional_score: float
    rectangle_score: float
    regime_score: float
    options_bias: str
    options_setup: str
    directional_call_score: int
    directional_put_score: int
    close: float
    return_20d: float
    return_60d: float
    relative_20d: float
    avg_volume_20d: float
    relative_volume_20d: float
    rectangle_status: str
    source: str
    notes: str


@dataclass(frozen=True)
class WatchlistResult:
    candidates: list[WatchlistCandidate]
    total_symbols: int
    failed_symbols: int
    failures: dict[str, str]
    regime: MarketRegimeResult
    sector_rotation: SectorRotationResult


def build_broad_watchlist(
    symbols: Iterable[str],
    provider: MarketDataProvider,
    *,
    repository: SQLiteScanRepository | None = None,
    period: str = "2y",
    limit: int = 50,
    metadata_store: SymbolMetadataStore | None = None,
    max_workers: int = 12,
    enrich_metadata_limit: int = 15,
) -> WatchlistResult:
    normalized_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    metadata = metadata_store or SymbolMetadataStore()
    regime = analyze_market_regime(provider, period=period)
    sector_rotation = analyze_sector_rotation(provider, period=period)
    spy = provider.get_daily_bars(BarDataRequest(symbol="SPY", period=period))
    spy_return_20d = _return_over_bars(spy, 20)
    sector_scores = {row.sector: row.leadership_score for row in sector_rotation.rows}
    rectangle_by_symbol = _rectangle_candidates(repository)
    cached_failures = _read_failure_cache(period)

    candidates: list[WatchlistCandidate] = []
    failures: dict[str, str] = {symbol: cached_failures[symbol] for symbol in normalized_symbols if symbol in cached_failures}
    symbols_to_scan = [symbol for symbol in normalized_symbols if symbol not in cached_failures]
    workers = max(1, min(max_workers, len(symbols_to_scan) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _candidate_for_symbol,
                symbol,
                provider,
                period,
                metadata,
                regime,
                spy_return_20d,
                sector_scores,
                rectangle_by_symbol.get(symbol),
            ): symbol
            for symbol in symbols_to_scan
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                candidates.append(future.result())
            except Exception as exc:
                failures[symbol] = str(exc)

    _write_failure_cache(period, failures)
    candidates.sort(key=lambda candidate: candidate.readiness_score, reverse=True)
    top_candidates = _enrich_top_candidate_metadata(
        candidates[:limit],
        metadata,
        max_symbols=enrich_metadata_limit,
    )
    return WatchlistResult(
        candidates=top_candidates,
        total_symbols=len(normalized_symbols),
        failed_symbols=len(failures),
        failures=failures,
        regime=regime,
        sector_rotation=sector_rotation,
    )


def watchlist_frame(candidates: list[WatchlistCandidate]) -> pd.DataFrame:
    return pd.DataFrame([candidate.__dict__ for candidate in candidates])


def _read_failure_cache(period: str, path: Path | None = None) -> dict[str, str]:
    cache_path = path or WATCHLIST_FAILURE_CACHE
    if not cache_path.exists():
        return {}
    try:
        frame = pd.read_csv(cache_path)
    except Exception:
        return {}
    required = {"symbol", "period", "message"}
    if not required.issubset(set(frame.columns)):
        return {}
    filtered = frame[frame["period"].astype(str) == str(period)]
    return {
        str(row.symbol).strip().upper(): str(row.message)
        for row in filtered.itertuples(index=False)
        if str(row.symbol).strip()
    }


def _write_failure_cache(
    period: str,
    failures: dict[str, str],
    path: Path | None = None,
) -> None:
    if not failures:
        return
    cache_path = path or WATCHLIST_FAILURE_CACHE
    existing = _read_all_failure_cache(cache_path)
    for symbol, message in failures.items():
        existing[(symbol.upper(), str(period))] = message
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"symbol": symbol, "period": cached_period, "message": message}
            for (symbol, cached_period), message in sorted(existing.items())
        ]
    ).to_csv(cache_path, index=False)


def _read_all_failure_cache(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    try:
        frame = pd.read_csv(path)
    except Exception:
        return {}
    required = {"symbol", "period", "message"}
    if not required.issubset(set(frame.columns)):
        return {}
    return {
        (str(row.symbol).strip().upper(), str(row.period)): str(row.message)
        for row in frame.itertuples(index=False)
        if str(row.symbol).strip()
    }


def _candidate_for_symbol(
    symbol: str,
    provider: MarketDataProvider,
    period: str,
    metadata: SymbolMetadataStore,
    regime: MarketRegimeResult,
    spy_return_20d: float,
    sector_scores: dict[str, float],
    rectangle: ScanCandidate | None,
) -> WatchlistCandidate:
    bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
    return _candidate_from_bars(
        symbol,
        bars,
        metadata,
        regime,
        spy_return_20d,
        sector_scores,
        rectangle,
    )


def _enrich_top_candidate_metadata(
    candidates: list[WatchlistCandidate],
    metadata: SymbolMetadataStore,
    *,
    max_symbols: int,
) -> list[WatchlistCandidate]:
    unknown_symbols = [
        candidate.symbol
        for candidate in candidates
        if candidate.name == "Unknown" or candidate.sector == "Unknown" or candidate.industry == "Unknown"
    ]
    if unknown_symbols and max_symbols > 0:
        metadata.enrich_yfinance(unknown_symbols, max_symbols=max_symbols)
    return [_candidate_with_metadata(candidate, metadata.get(candidate.symbol)) for candidate in candidates]


def _candidate_with_metadata(
    candidate: WatchlistCandidate,
    metadata: SymbolMetadata,
) -> WatchlistCandidate:
    name = metadata.name
    sector = metadata.sector
    industry = metadata.industry
    if name == candidate.name and sector == candidate.sector and industry == candidate.industry:
        return candidate
    return WatchlistCandidate(
        **{
            **candidate.__dict__,
            "name": str(name),
            "sector": str(sector),
            "industry": str(industry),
        }
    )


def _candidate_from_bars(
    symbol: str,
    bars: pd.DataFrame,
    metadata_store: SymbolMetadataStore,
    regime: MarketRegimeResult,
    spy_return_20d: float,
    sector_scores: dict[str, float],
    rectangle: ScanCandidate | None,
) -> WatchlistCandidate:
    _validate_history(symbol, bars)
    meta = metadata_store.get(symbol)
    close = float(bars["close"].iloc[-1])
    sma20 = _last_rolling(bars["close"], 20)
    sma50 = _last_rolling(bars["close"], 50)
    sma200 = _last_rolling(bars["close"], 200)
    high_20d = float(bars["high"].tail(20).max())
    low_20d = float(bars["low"].tail(20).min())
    return_20d = _return_over_bars(bars, 20)
    return_60d = _return_over_bars(bars, 60)
    relative_20d = return_20d - spy_return_20d
    avg_volume_20d = float(bars["volume"].tail(20).mean())
    avg_volume_60d = float(bars["volume"].tail(60).mean())
    latest_volume = float(bars["volume"].iloc[-1])
    relative_volume = latest_volume / avg_volume_20d if avg_volume_20d > 0 else 0.0

    momentum_score = _momentum_score(return_20d, return_60d)
    trend_score = _trend_score(close, sma20, sma50, sma200)
    relative_strength_score = _relative_strength_score(relative_20d)
    sector_score = sector_scores.get(meta.sector, 0.0)
    liquidity_score = _liquidity_score(close, avg_volume_20d)
    volume_score = _volume_score(relative_volume, avg_volume_20d, avg_volume_60d)
    directional = analyze_directional_setup(symbol, bars)
    directional_score = directional.normalized_score
    rectangle_score = composite_rank_score(rectangle) if rectangle else 0.0
    regime_score = 1.0 if regime.is_constructive else 0.35
    close_location_20d = _close_location(close, high_20d, low_20d)
    distance_to_trigger_pct = _distance_to_trigger_pct(close, high_20d)
    breakout_setup_score = _breakout_setup_score(
        close=close,
        high_20d=high_20d,
        low_20d=low_20d,
        close_location=close_location_20d,
        relative_volume=relative_volume,
        rectangle_score=rectangle_score,
    )
    risk_score = _risk_score(
        close=close,
        sma20=sma20,
        sma50=sma50,
        return_5d=_return_over_bars(bars, 5),
        return_20d=return_20d,
        close_location=close_location_20d,
    )

    final_score = (
        momentum_score * 0.16
        + trend_score * 0.16
        + relative_strength_score * 0.13
        + sector_score * 0.13
        + liquidity_score * 0.10
        + volume_score * 0.10
        + directional_score * 0.12
        + rectangle_score * 0.05
        + regime_score * 0.05
    )
    readiness_score = _readiness_score(
        liquidity_score=liquidity_score,
        trend_score=trend_score,
        momentum_score=momentum_score,
        relative_strength_score=relative_strength_score,
        sector_score=sector_score,
        breakout_setup_score=breakout_setup_score,
        risk_score=risk_score,
        regime_score=regime_score,
    )
    readiness_label = _readiness_label(
        readiness_score=readiness_score,
        breakout_setup_score=breakout_setup_score,
        trend_score=trend_score,
        momentum_score=momentum_score,
        risk_score=risk_score,
        distance_to_trigger_pct=distance_to_trigger_pct,
    )
    setup_state = _setup_state(
        close=close,
        high_20d=high_20d,
        distance_to_trigger_pct=distance_to_trigger_pct,
        trend_score=trend_score,
        momentum_score=momentum_score,
        risk_score=risk_score,
        breakout_setup_score=breakout_setup_score,
    )
    return WatchlistCandidate(
        symbol=symbol,
        name=meta.name,
        sector=meta.sector,
        industry=meta.industry,
        final_score=round(final_score, 3),
        readiness_score=round(readiness_score, 3),
        readiness_label=readiness_label,
        setup_state=setup_state,
        breakout_setup_score=round(breakout_setup_score, 3),
        risk_score=round(risk_score, 3),
        trigger_level=round(high_20d, 2),
        distance_to_trigger_pct=round(distance_to_trigger_pct, 4),
        close_location_20d=round(close_location_20d, 3),
        momentum_score=round(momentum_score, 3),
        trend_score=round(trend_score, 3),
        relative_strength_score=round(relative_strength_score, 3),
        sector_score=round(sector_score, 3),
        liquidity_score=round(liquidity_score, 3),
        volume_score=round(volume_score, 3),
        directional_score=round(directional_score, 3),
        rectangle_score=round(rectangle_score, 3),
        regime_score=round(regime_score, 3),
        options_bias=directional.bias,
        options_setup=directional.setup_type,
        directional_call_score=directional.call_score,
        directional_put_score=directional.put_score,
        close=round(close, 2),
        return_20d=round(return_20d, 4),
        return_60d=round(return_60d, 4),
        relative_20d=round(relative_20d, 4),
        avg_volume_20d=round(avg_volume_20d, 0),
        relative_volume_20d=round(relative_volume, 3),
        rectangle_status=rectangle.setup_status if rectangle else "No rectangle signal",
        source="Broad + Rectangle" if rectangle else "Broad",
        notes=_notes(close, sma50, relative_20d, rectangle, directional.notes),
    )


def _rectangle_candidates(repository: SQLiteScanRepository | None) -> dict[str, ScanCandidate]:
    if repository is None:
        return {}
    return {candidate.symbol: candidate for candidate in repository.latest_candidates()}


def _validate_history(symbol: str, bars: pd.DataFrame) -> None:
    if len(bars) < 220:
        raise ValueError(f"{symbol} needs at least 220 daily bars, got {len(bars)}")


def _return_over_bars(bars: pd.DataFrame, bars_back: int) -> float:
    if len(bars) <= bars_back:
        return 0.0
    current = float(bars["close"].iloc[-1])
    prior = float(bars["close"].iloc[-bars_back - 1])
    return (current / prior) - 1.0 if prior > 0 else 0.0


def _last_rolling(series: pd.Series, window: int) -> float:
    values = series.rolling(window).mean().dropna()
    return float(values.iloc[-1]) if not values.empty else 0.0


def _momentum_score(return_20d: float, return_60d: float) -> float:
    score = 0.0
    score += max(0.0, min(return_20d / 0.12, 1.0)) * 0.55
    score += max(0.0, min(return_60d / 0.25, 1.0)) * 0.45
    return score


def _trend_score(close: float, sma20: float, sma50: float, sma200: float) -> float:
    score = 0.0
    score += 0.25 if close > sma20 else 0.0
    score += 0.30 if close > sma50 else 0.0
    score += 0.30 if close > sma200 else 0.0
    score += 0.15 if sma50 > sma200 else 0.0
    return score


def _relative_strength_score(relative_20d: float) -> float:
    return max(0.0, min((relative_20d + 0.05) / 0.15, 1.0))


def _liquidity_score(close: float, avg_volume_20d: float) -> float:
    dollar_volume = close * avg_volume_20d
    return max(0.0, min(dollar_volume / 100_000_000, 1.0))


def _volume_score(relative_volume: float, avg_volume_20d: float, avg_volume_60d: float) -> float:
    confirmation = max(0.0, min(relative_volume / 1.5, 1.0)) * 0.55
    sustained = min(avg_volume_20d / avg_volume_60d, 1.5) / 1.5 * 0.45 if avg_volume_60d > 0 else 0.0
    return confirmation + sustained


def _close_location(close: float, high: float, low: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min((close - low) / (high - low), 1.5))


def _distance_to_trigger_pct(close: float, trigger_level: float) -> float:
    if close <= 0:
        return 1.0
    return (trigger_level - close) / close


def _breakout_setup_score(
    *,
    close: float,
    high_20d: float,
    low_20d: float,
    close_location: float,
    relative_volume: float,
    rectangle_score: float,
) -> float:
    if close <= 0 or high_20d <= low_20d:
        return 0.0
    range_pct = (high_20d - low_20d) / close
    range_quality = 1.0 if 0.03 <= range_pct <= 0.18 else max(0.0, 1.0 - abs(range_pct - 0.105) / 0.20)
    location_quality = max(0.0, min((close_location - 0.45) / 0.45, 1.0))
    trigger_distance = abs(_distance_to_trigger_pct(close, high_20d))
    trigger_quality = max(0.0, min(1.0 - trigger_distance / 0.06, 1.0))
    volume_quality = max(0.0, min(relative_volume / 1.5, 1.0))
    structure_quality = max(rectangle_score, range_quality * 0.60 + location_quality * 0.40)
    return (
        structure_quality * 0.30
        + location_quality * 0.25
        + trigger_quality * 0.25
        + volume_quality * 0.20
    )


def _risk_score(
    *,
    close: float,
    sma20: float,
    sma50: float,
    return_5d: float,
    return_20d: float,
    close_location: float,
) -> float:
    if close <= 0:
        return 0.0
    distance_from_20 = (close / sma20 - 1.0) if sma20 > 0 else 0.0
    distance_from_50 = (close / sma50 - 1.0) if sma50 > 0 else 0.0
    extension_penalty = 0.0
    extension_penalty += max(0.0, min((distance_from_20 - 0.08) / 0.12, 1.0)) * 0.35
    extension_penalty += max(0.0, min((distance_from_50 - 0.18) / 0.22, 1.0)) * 0.30
    extension_penalty += max(0.0, min((return_5d - 0.12) / 0.18, 1.0)) * 0.20
    extension_penalty += max(0.0, min((return_20d - 0.30) / 0.30, 1.0)) * 0.15
    if close_location > 1.05:
        extension_penalty = max(extension_penalty, 0.70)
    return max(0.0, min(1.0 - extension_penalty, 1.0))


def _readiness_score(
    *,
    liquidity_score: float,
    trend_score: float,
    momentum_score: float,
    relative_strength_score: float,
    sector_score: float,
    breakout_setup_score: float,
    risk_score: float,
    regime_score: float,
) -> float:
    return max(
        0.0,
        min(
            liquidity_score * 0.15
            + trend_score * 0.22
            + momentum_score * 0.20
            + relative_strength_score * 0.12
            + sector_score * 0.07
            + breakout_setup_score * 0.18
            + risk_score * 0.04
            + regime_score * 0.02,
            1.0,
        ),
    )


def _readiness_label(
    *,
    readiness_score: float,
    breakout_setup_score: float,
    trend_score: float,
    momentum_score: float,
    risk_score: float,
    distance_to_trigger_pct: float,
) -> str:
    if risk_score < 0.35 and readiness_score >= 0.60:
        return "Extended Risk"
    if readiness_score >= 0.78 and breakout_setup_score >= 0.65 and distance_to_trigger_pct <= 0.02:
        return "Ready Now"
    if readiness_score >= 0.65 and trend_score >= 0.65 and momentum_score >= 0.45:
        return "Ready Watch"
    if readiness_score >= 0.52 and trend_score >= 0.45:
        return "Base Building"
    return "Avoid"


def _setup_state(
    *,
    close: float,
    high_20d: float,
    distance_to_trigger_pct: float,
    trend_score: float,
    momentum_score: float,
    risk_score: float,
    breakout_setup_score: float,
) -> str:
    if close > high_20d and breakout_setup_score >= 0.55:
        return "Breakout"
    if risk_score < 0.35:
        return "Extended"
    if distance_to_trigger_pct <= 0.02 and breakout_setup_score >= 0.55:
        return "Near Breakout"
    if trend_score >= 0.65 and momentum_score >= 0.45:
        return "Trending"
    if breakout_setup_score >= 0.45:
        return "Base Building"
    return "No Clean Setup"


def _notes(
    close: float,
    sma50: float,
    relative_20d: float,
    rectangle: ScanCandidate | None,
    directional_notes: str,
) -> str:
    notes: list[str] = []
    if close > sma50:
        notes.append("above 50D")
    if relative_20d > 0:
        notes.append("beating SPY 20D")
    if rectangle:
        notes.append(f"rectangle: {rectangle.setup_status}")
    notes.append(directional_notes)
    return ", ".join(notes) if notes else "needs confirmation"
