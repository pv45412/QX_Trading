from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from datetime import datetime, timedelta, timezone
import math
import logging
from hashlib import sha256

import pandas as pd

from qx.data.providers import MarketDataProvider
from qx.data.cache import _atomic_write
from qx.market.sessions import completed_mover_bars
from qx.models.market import BarDataRequest
from qx.models.scan import RectangleScanParameters, ScanCandidate, ScanError, ScanRunResult
from qx.patterns.ranking import sort_candidates
from qx.patterns.rectangle import analyze_rectangle, minimum_required_bars
from qx.storage.feature_cache import SQLiteFeatureCache, build_feature_cache_key

SCANNER_FAILURE_CACHE = Path("data/cache/scanner_failures.csv")
FAILURE_CACHE_TTL = timedelta(hours=1)


class ScannerEngine:
    """Coordinates data loading and deterministic pattern detection."""

    def __init__(
        self,
        provider: MarketDataProvider,
        parameters: RectangleScanParameters | None = None,
        feature_cache: SQLiteFeatureCache | None = None,
        *,
        as_of: datetime | None = None,
        failure_cache_scope: str | None = None,
    ) -> None:
        self.provider = provider
        self.parameters = parameters or RectangleScanParameters()
        self.feature_cache = feature_cache
        if as_of is not None and as_of.utcoffset() is None:
            raise ValueError("Scan time must be timezone-aware")
        self.as_of = as_of
        scope = failure_cache_scope or f"{type(provider).__module__}.{type(provider).__qualname__}"
        scope_hash = sha256(scope.encode()).hexdigest()[:16]
        self.failure_cache_path = SCANNER_FAILURE_CACHE.with_name(
            f"{SCANNER_FAILURE_CACHE.stem}_{scope_hash}{SCANNER_FAILURE_CACHE.suffix}")
        self._feature_cache_lock = Lock()

    def scan_symbols(
        self,
        symbols: Iterable[str],
        period: str = "1y",
        *,
        max_workers: int = 12,
        retry_failed: bool = False,
    ) -> ScanRunResult:
        candidates: list[ScanCandidate] = []
        normalized_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        effective_period = self._effective_period(period)

        cached_failures = {} if retry_failed else _read_failure_cache(effective_period, self.failure_cache_path)
        new_failures: dict[str, str] = {}
        errors: list[ScanError] = [
            ScanError(symbol=symbol, message=cached_failures[symbol])
            for symbol in normalized_symbols
            if symbol in cached_failures
        ]
        symbols_to_scan = [symbol for symbol in normalized_symbols if symbol not in cached_failures]
        benchmark_return_20d = self._benchmark_return_20d(effective_period) if symbols_to_scan else None

        workers = max(1, min(max_workers, len(symbols_to_scan) or 1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._scan_symbol, symbol, effective_period, benchmark_return_20d): symbol
                for symbol in symbols_to_scan
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    candidates.append(future.result())
                except Exception as exc:
                    message = str(exc)
                    errors.append(ScanError(symbol=symbol, message=message))
                    if _cacheable_error(message):
                        new_failures[symbol] = message

        try:
            if retry_failed:
                _remove_failure_entries(effective_period, normalized_symbols, self.failure_cache_path)
            _write_failure_cache(effective_period, new_failures, self.failure_cache_path)
        except OSError:
            logging.getLogger(__name__).warning("Failure cooldown cache unavailable; scan results retained")
        candidates = sort_candidates(candidates)
        return ScanRunResult(
            candidates=candidates,
            total_symbols=len(normalized_symbols),
            passed_symbols=sum(candidate.passed for candidate in candidates),
            failed_symbols=len(errors),
            errors=errors,
        )

    def _scan_symbol(
        self,
        symbol: str,
        effective_period: str,
        benchmark_return_20d: tuple[pd.Index, float] | None,
    ) -> ScanCandidate:
        bars = self.provider.get_daily_bars(BarDataRequest(symbol=symbol, period=effective_period))
        return self._analyze(symbol, bars, effective_period, benchmark_return_20d)

    def scan_symbols_sequential(self, symbols: Iterable[str], period: str = "1y") -> ScanRunResult:
        candidates: list[ScanCandidate] = []
        errors: list[ScanError] = []
        normalized_symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        effective_period = self._effective_period(period)
        benchmark_return_20d = self._benchmark_return_20d(effective_period) if normalized_symbols else None
        for symbol in normalized_symbols:
            try:
                bars = self.provider.get_daily_bars(BarDataRequest(symbol=symbol, period=effective_period))
                candidates.append(self._analyze(symbol, bars, effective_period, benchmark_return_20d))
            except Exception as exc:
                errors.append(ScanError(symbol=symbol, message=str(exc)))

        candidates = sort_candidates(candidates)
        return ScanRunResult(
            candidates=candidates,
            total_symbols=len(normalized_symbols),
            passed_symbols=sum(candidate.passed for candidate in candidates),
            failed_symbols=len(errors),
            errors=errors,
        )

    def _effective_period(self, requested_period: str) -> str:
        if minimum_required_bars(self.parameters) >= 200 and requested_period in {"6mo", "1y"}:
            return "2y"
        return requested_period

    def _analyze(
        self,
        symbol: str,
        bars: pd.DataFrame,
        period: str,
        benchmark_return_20d: tuple[pd.Index, float] | None,
    ) -> ScanCandidate:
        bars = self._completed_history(bars)
        if self.feature_cache is None:
            candidate = analyze_rectangle(symbol, bars, self.parameters)
            return _with_relative_strength(candidate, bars, benchmark_return_20d)

        key = build_feature_cache_key(symbol, bars, self.parameters, period=period)
        with self._feature_cache_lock:
            cached = self.feature_cache.get(key)
        if cached is not None:
            return _with_relative_strength(cached, bars, benchmark_return_20d)

        candidate = analyze_rectangle(symbol, bars, self.parameters)
        with self._feature_cache_lock:
            self.feature_cache.set(key, candidate)
        return _with_relative_strength(candidate, bars, benchmark_return_20d)

    def _benchmark_return_20d(self, period: str) -> tuple[pd.Index, float] | None:
        try:
            benchmark_bars = self.provider.get_daily_bars(BarDataRequest(symbol="SPY", period=period))
            benchmark_bars = self._completed_history(benchmark_bars)
        except Exception:
            return None
        return _return_window(benchmark_bars)

    def _completed_history(self, bars: pd.DataFrame) -> pd.DataFrame:
        if self.as_of is None:
            return bars
        if not isinstance(bars.index, pd.DatetimeIndex):
            raise ValueError("Live scan requires dated daily bars")
        return completed_mover_bars(bars, self.as_of)


def _with_relative_strength(
    candidate: ScanCandidate,
    bars: pd.DataFrame,
    benchmark_return_20d: tuple[pd.Index, float] | None,
) -> ScanCandidate:
    window = _return_window(bars)
    if benchmark_return_20d is None or window is None:
        candidate.metrics.rs_status = "Not checked"
        return candidate

    if not window[0].equals(benchmark_return_20d[0]):
        candidate.metrics.rs_status = "Not checked"
        return candidate
    relative_20d = window[1] - benchmark_return_20d[1]
    candidate.metrics.rs_status = _relative_strength_status(relative_20d)
    return candidate


def _return_window(bars: pd.DataFrame) -> tuple[pd.Index, float] | None:
    try:
        window = bars.tail(21)
        if len(window) != 21 or not window.index.is_unique or not window.index.is_monotonic_increasing:
            return None
        prices = window["close"].astype(float)
        if not all(math.isfinite(value) and value > 0 for value in prices):
            return None
        result = float(prices.iloc[-1] / prices.iloc[0] - 1)
        return (window.index.copy(), result) if math.isfinite(result) else None
    except (ValueError, TypeError, KeyError):
        return None


def _return_over_bars(bars: pd.DataFrame, bars_back: int) -> float:
    if len(bars) <= bars_back:
        return 0.0
    current = float(bars["close"].iloc[-1])
    prior = float(bars["close"].iloc[-bars_back - 1])
    return (current / prior) - 1.0 if prior > 0 else 0.0


def _relative_strength_status(relative_20d: float) -> str:
    if relative_20d >= 0.03:
        return "Leading"
    if relative_20d > 0.0:
        return "Improving"
    if relative_20d >= -0.03:
        return "Neutral"
    return "Lagging"


def _read_failure_cache(period: str, path: Path | None = None) -> dict[str, str]:
    resolved_path = path or SCANNER_FAILURE_CACHE
    if not resolved_path.exists():
        return {}
    try:
        frame = pd.read_csv(resolved_path)
    except Exception:
        return {}
    required = {"symbol", "period", "message", "failed_at"}
    if not required.issubset(set(frame.columns)):
        return {}
    filtered = frame[frame["period"].astype(str) == str(period)]
    return {
        str(row.symbol).strip().upper(): str(row.message)
        for row in filtered.itertuples(index=False)
        if str(row.symbol).strip() and _recent_failure(str(row.failed_at))
    }


def _write_failure_cache(
    period: str,
    failures: dict[str, str],
    path: Path | None = None,
) -> None:
    if not failures:
        return
    resolved_path = path or SCANNER_FAILURE_CACHE
    existing = _read_all_failure_cache(resolved_path)
    for symbol, message in failures.items():
        existing[(symbol.upper(), str(period))] = (message, datetime.now(timezone.utc).isoformat())
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {"symbol": symbol, "period": cached_period, "message": message, "failed_at": failed_at}
            for (symbol, cached_period), (message, failed_at) in sorted(existing.items())
        ]
    )
    _atomic_write(resolved_path, frame.to_csv(index=False).encode())


def _read_all_failure_cache(path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    if not path.exists():
        return {}
    try:
        frame = pd.read_csv(path)
    except Exception:
        return {}
    required = {"symbol", "period", "message", "failed_at"}
    if not required.issubset(set(frame.columns)):
        return {}
    return {
        (str(row.symbol).strip().upper(), str(row.period)): (str(row.message), str(row.failed_at))
        for row in frame.itertuples(index=False)
        if str(row.symbol).strip() and _recent_failure(str(row.failed_at))
    }


def _recent_failure(value: str) -> bool:
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.utcoffset() is None:
            return False
        return timedelta(0) <= datetime.now(timezone.utc) - timestamp < FAILURE_CACHE_TTL
    except ValueError:
        return False


def _remove_failure_entries(period: str, symbols: list[str], path: Path) -> None:
    if not path.exists():
        return
    entries = _read_all_failure_cache(path)
    for symbol in symbols:
        entries.pop((symbol, period), None)
    frame = pd.DataFrame([
        {"symbol": symbol, "period": cached_period, "message": message, "failed_at": failed_at}
        for (symbol, cached_period), (message, failed_at) in entries.items()
    ], columns=["symbol", "period", "message", "failed_at"])
    _atomic_write(path, frame.to_csv(index=False).encode())


def _cacheable_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "no price data" in lowered
        or "no schwab price history" in lowered
        or "possibly delisted" in lowered
    )
