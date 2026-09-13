from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from qx.data.cache import _cache_symbol, _read_cached_bars
from qx.data.provenance import valid_provenance
from qx.market.sessions import _schedule, completed_mover_bars


@dataclass(frozen=True)
class CacheFileStatus:
    symbol: str
    period: str
    path: Path
    rows: int
    size_bytes: int
    modified_at: str


@dataclass(frozen=True)
class CacheSummary:
    cache_dir: Path
    total_files: int
    total_symbols: int
    total_size_mb: float
    periods: dict[str, int]


@dataclass(frozen=True)
class CacheCoverage:
    period: str
    total: int
    cached: int
    missing: int
    coverage: float
    missing_symbols: list[str]


@dataclass(frozen=True)
class CacheHealth:
    label: str
    ready: bool
    coverage: float
    latest_modified_at: str
    stale: bool
    message: str
    expected_session: str = ""
    valid_symbols: int = 0
    fresh_symbols: int = 0
    source_verified_symbols: int = 0
    symbol_evidence: tuple["CacheSymbolEvidence", ...] = ()


@dataclass(frozen=True)
class CacheSymbolEvidence:
    symbol: str
    available: bool
    status: str
    latest_eligible_session: str = ""
    actual_source: str = "unknown"
    retrieved_at: str = ""
    source_verified: bool = False
    detail: str = ""


def cache_operational_actions(*, health: CacheHealth, coverage: CacheCoverage) -> list[str]:
    """Return the next practical cache actions for UI and CLI surfaces."""
    if not health.latest_modified_at:
        return ["Warm the cache before running large scans; no local bar cache exists for this period."]

    if health.stale:
        return ["Run a targeted forced cache refresh for missing, stale, or invalid completed-session bars. "
                + health.message]

    if coverage.coverage < 0.95:
        return [
            f"Warm missing symbols for {coverage.period}; coverage is {coverage.coverage:.1%} "
            f"with {coverage.missing} missing names."
        ]

    if not health.ready:
        return [health.message]
    return ["Cache is ready under the completed-session and source checks. "
            "This does not establish last job success or strategy-specific history sufficiency."]


def summarize_bar_cache(cache_dir: Path = Path("data/cache/bars")) -> CacheSummary:
    files = list_bar_cache(cache_dir)
    periods: dict[str, int] = {}
    for item in files:
        periods[item.period] = periods.get(item.period, 0) + 1

    return CacheSummary(
        cache_dir=cache_dir,
        total_files=len(files),
        total_symbols=len({item.symbol for item in files}),
        total_size_mb=round(sum(item.size_bytes for item in files) / 1_000_000, 2),
        periods=dict(sorted(periods.items())),
    )


def list_bar_cache(cache_dir: Path = Path("data/cache/bars")) -> list[CacheFileStatus]:
    if not cache_dir.exists():
        return []

    statuses: list[CacheFileStatus] = []
    for path in sorted(cache_dir.glob("*.csv")):
        parsed = _parse_cache_file_name(path)
        if parsed is None:
            continue
        symbol, period = parsed
        try:
            stat = path.stat()
        except OSError:
            continue
        statuses.append(
            CacheFileStatus(
                symbol=symbol,
                period=period,
                path=path,
                rows=_count_csv_data_rows(path, _stat_key(path)),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            )
        )
    return statuses


def universe_cache_coverage(
    universe_symbols: list[str],
    *,
    period: str = "2y",
    cache_dir: Path = Path("data/cache/bars"),
) -> CacheCoverage:
    # Availability is an inventory check only: do not open every CSV to count rows.
    available = {
        parsed[0] for path in cache_dir.glob("*.csv")
        if (parsed := _parse_cache_file_name(path)) is not None and parsed[1] == period
    }
    universe = {symbol.strip().upper() for symbol in universe_symbols if symbol.strip()}
    cached = sorted(symbol for symbol in universe if _cache_symbol(symbol) in available)
    missing = sorted(universe - set(cached))
    coverage = len(cached) / len(universe) if universe else 0.0
    return CacheCoverage(
        period=period,
        total=len(universe),
        cached=len(cached),
        missing=len(missing),
        coverage=coverage,
        missing_symbols=missing,
    )


def assess_cache_health(
    universe_symbols: list[str],
    *,
    period: str = "2y",
    cache_dir: Path = Path("data/cache/bars"),
    max_age_hours: int = 36,
    as_of: datetime | None = None,
) -> CacheHealth:
    """Assess requested US-equity daily bars, independently of file modification age.

    ``max_age_hours`` remains accepted for existing clients; completed exchange
    sessions (including the shared 30-minute buffer) now define freshness.
    """
    now = as_of if as_of is not None else datetime.now(UTC)
    if now.utcoffset() is None:
        raise ValueError("Cache assessment time must be timezone-aware")
    expected = latest_completed_session(now)
    coverage = universe_cache_coverage(universe_symbols, period=period, cache_dir=cache_dir)
    universe = sorted({symbol.strip().upper() for symbol in universe_symbols if symbol.strip()})
    evidence = []
    modified = []
    for symbol in universe:
        path = (cache_dir / f"{_cache_symbol(symbol)}_{period}.csv").resolve()
        signature = _stat_key(path)
        if signature is not None:
            modified.append(datetime.fromtimestamp(signature[0] / 1_000_000_000, UTC))
        evidence.append(_symbol_evidence(symbol, path, signature, _stat_key(path.with_suffix(".meta.json")), now))
    fresh = sum(item.status == "Current" for item in evidence)
    valid = sum(item.status in {"Current", "Stale"} for item in evidence)
    verified = sum(item.source_verified for item in evidence)
    stale = any(item.status != "Current" for item in evidence) or not evidence
    ready = bool(evidence) and fresh == len(evidence) and verified == len(evidence)
    if not coverage.cached:
        label = "Missing"
    elif coverage.missing:
        label = "Incomplete"
    elif any(item.status == "Invalid" for item in evidence):
        label = "Invalid"
    elif stale:
        label = "Stale"
    elif not ready:
        label = "Unverified"
    else:
        label = "Ready"
    message = (
        f"File availability {coverage.cached}/{coverage.total}; valid dated bars {valid}/{coverage.total}; "
        f"completed-session coverage through {expected}: {fresh}/{coverage.total}; "
        f"verified actual source {verified}/{coverage.total}. "
        "File modification time is not bar freshness. Last job success is not assessed."
    )
    return CacheHealth(
        label=label,
        ready=ready,
        coverage=coverage.coverage,
        latest_modified_at=max(modified).isoformat() if modified else "",
        stale=stale,
        message=message,
        expected_session=expected,
        valid_symbols=valid,
        fresh_symbols=fresh,
        source_verified_symbols=verified,
        symbol_evidence=tuple(evidence),
    )


@lru_cache(maxsize=64)
def latest_completed_session(as_of: datetime) -> str:
    """Use the existing NYSE calendar and completed-bar availability policy."""
    if as_of.utcoffset() is None:
        raise ValueError("Assessment time must be timezone-aware")
    schedule = _schedule(as_of.astimezone(ZoneInfo("America/New_York")).date())
    eligible = schedule.loc[schedule["market_close"] + pd.Timedelta(minutes=30) <= pd.Timestamp(as_of)]
    return str(eligible.index[-1].date())


def _stat_key(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns
    except OSError:
        return None


@lru_cache(maxsize=512)
def _cached_bar_evidence(
    path: Path,
    signature: tuple[int, int, int] | None,
    metadata_signature: tuple[int, int, int] | None,
) -> pd.DataFrame:
    # Both signatures invalidate cached reads, including metadata-only repairs.
    bars = _read_cached_bars(path)
    if _stat_key(path) != signature or _stat_key(path.with_suffix(".meta.json")) != metadata_signature:
        raise ValueError("Cache changed during evidence read; retry assessment")
    return bars


def _symbol_evidence(
    symbol: str,
    path: Path,
    signature: tuple[int, int, int] | None,
    metadata_signature: tuple[int, int, int] | None,
    as_of: datetime,
) -> CacheSymbolEvidence:
    if signature is None:
        return CacheSymbolEvidence(symbol, False, "Missing", detail="No local file")
    latest = ""
    source = "unknown"
    retrieved = ""
    verified = False
    try:
        bars = _cached_bar_evidence(path, signature, metadata_signature)
        provenance = bars.attrs.get("provenance", {})
        if valid_provenance(provenance):
            source = provenance["actual_source"].strip()
            retrieved = _parse_timestamp(provenance["retrieved_at"]).astimezone(UTC).isoformat()
            verified = source.lower() not in {"unknown", "n/a"}
        if (bars.empty or not isinstance(bars.index, pd.DatetimeIndex)
                or bars.index.hasnans or bars.index.duplicated().any()):
            raise ValueError("Missing, invalid, or duplicate daily session labels")
        if len(bars) != _count_csv_data_rows(path, signature):
            raise ValueError("Cache contains rows discarded during OHLCV normalization")
        values = bars[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
        prices = values[["open", "high", "low", "close"]]
        if (not np.isfinite(values.to_numpy()).all() or not prices.gt(0).all().all()
                or values["volume"].lt(0).any()
                or values["high"].lt(prices.max(axis=1)).any()
                or values["low"].gt(prices.min(axis=1)).any()):
            raise ValueError("Invalid OHLCV values")
        labels = bars.index.date
        expected = latest_completed_session(as_of)
        today = as_of.astimezone(ZoneInfo("America/New_York")).date()
        if any(label > today for label in labels):
            raise ValueError("Future-dated daily bars")
        # Daily indices are session labels. A weekend/holiday label is never eligible.
        sessions = set(pd.DatetimeIndex(_schedule(labels[-1]).index).date)
        for label in reversed(labels):
            if label.isoformat() <= expected and label in sessions:
                latest = label.isoformat()
                break
        if any(label not in sessions for label in labels[-21:]):
            raise ValueError("Non-session daily bars")
        try:
            completed_mover_bars(bars, as_of)
        except ValueError as exc:
            return CacheSymbolEvidence(symbol, True, "Stale", latest, source, retrieved, verified, str(exc))
        return CacheSymbolEvidence(symbol, True, "Current", latest, source, retrieved, verified,
                                   "Latest 21 eligible NYSE sessions present with valid OHLCV")
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        return CacheSymbolEvidence(symbol, True, "Invalid", latest, source, retrieved, verified, str(exc))


def _parse_cache_file_name(path: Path) -> tuple[str, str] | None:
    stem = path.stem
    if "_" not in stem:
        return None
    symbol, period = stem.rsplit("_", 1)
    if not symbol or not period:
        return None
    return symbol.upper(), period


@lru_cache(maxsize=4096)
def _count_csv_data_rows(path: Path, signature: tuple[int, int, int] | None = None) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return max(sum(1 for _line in handle) - 1, 0)
    except (OSError, UnicodeError):
        return 0


def _parse_timestamp(value: str) -> datetime:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize(UTC)
    return parsed.to_pydatetime(warn=False)
