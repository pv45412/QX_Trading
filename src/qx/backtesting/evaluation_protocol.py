"""Cost-aware, read-only evaluation of a single frozen daily-bar snapshot."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from qx.backtesting.engine import backtest_rectangle_breakouts
from qx.data.cache import _cache_symbol
from qx.data.membership import membership_symbols
from qx.data.provenance import valid_provenance
from qx.data.providers import REQUIRED_COLUMNS, MarketDataProvider
from qx.data.universe import UNIVERSE_OPTIONS
from qx.models.backtest import BacktestParameters, BacktestResult, BacktestRunResult
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.models.scan import RectangleScanParameters

DEFAULT_FEE_BPS_PER_SIDE = 0.0
DEFAULT_SLIPPAGE_BPS_PER_SIDE = 5.0
MIN_SAMPLE_TRADES = 20


class EvaluationProtocol(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    version: Literal["calendar-holdout-v1"] = "calendar-holdout-v1"
    holdout_fraction: float = Field(default=0.25, gt=0, lt=1, allow_inf_nan=False)


def evaluation_parameters(**overrides: Any) -> BacktestParameters:
    return BacktestParameters(**{
        "fee_bps_per_side": DEFAULT_FEE_BPS_PER_SIDE,
        "slippage_bps_per_side": DEFAULT_SLIPPAGE_BPS_PER_SIDE,
        **overrides,
    })


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})


def cached_evaluation_symbols(
    universe: str, text: str, cache_dir: Path = Path("data/cache")
) -> list[str]:
    if universe == "Custom":
        return normalize_symbols(text.replace(",", "\n").splitlines())
    # UniverseLoader may refresh membership on read; evaluations never do that.
    key = UNIVERSE_OPTIONS[universe]
    return normalize_symbols(membership_symbols((cache_dir / f"{key}_symbols.csv").read_bytes()))


class ReadOnlyEvaluationProvider:
    def __init__(self, cache_dir: Path = Path("data/cache/bars")) -> None:
        self.cache_dir = cache_dir

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        if request.period not in {"1y", "2y", "3y", "5y"}:
            raise ValueError("Unsupported cached history period")
        path = self.cache_dir / f"{_cache_symbol(request.symbol)}_{request.period}.csv"
        content = path.read_bytes()
        bars = pd.read_csv(BytesIO(content))
        label = str(bars.columns[0]).lower()
        if label not in {"date", "datetime"} and not label.startswith("unnamed"):
            raise ValueError("Cached history must have explicit session dates")
        bars.index = pd.DatetimeIndex(pd.to_datetime(bars.pop(bars.columns[0]), errors="raise"))
        bars.columns = [str(column).strip().lower() for column in bars.columns]
        # Do not drop invalid holdout rows: their values must not move the training cutoff.
        bars.attrs["provenance"] = {"actual_source": "unknown", "retrieved_at": None}
        try:
            metadata = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
            if (isinstance(metadata, dict) and metadata.get("sha256") == sha256(content).hexdigest()
                    and valid_provenance(metadata.get("provenance"))):
                bars.attrs["provenance"] = metadata["provenance"]
        except (OSError, ValueError):
            pass
        return bars

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        raise NotImplementedError("Evaluations use daily bars only")


@dataclass(frozen=True)
class EvaluationSnapshot:
    symbols: list[str]
    bars_by_symbol: dict[str, pd.DataFrame]
    failures: dict[str, str]
    date_checks: dict[str, dict[str, Any]] = field(default_factory=dict)


@lru_cache(maxsize=16)
def _nyse_session_dates(start: str, end: str) -> frozenset[str]:
    schedule = mcal.get_calendar("NYSE").schedule(start_date=start, end_date=end)
    return frozenset(pd.Timestamp(label).date().isoformat() for label in schedule.index)


def _audit_session_dates(index: pd.DatetimeIndex, observed_at: datetime) -> dict[str, Any]:
    today = observed_at.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    labels = [label.date().isoformat() for label in index]
    historical = [label for label in labels if label <= today]
    check: dict[str, Any] = {
        "observed_date_et": today, "reference_calendar": "NYSE",
        "future_dates": [label for label in labels if label > today],
        "non_session_dates": [], "calendar_status": "checked",
    }
    if historical:
        try:
            if (pd.Timestamp(historical[-1]) - pd.Timestamp(historical[0])).days > 11_000:
                raise ValueError("Session reference window exceeds 30 years")
            sessions = _nyse_session_dates(historical[0], historical[-1])
            check["non_session_dates"] = [label for label in historical if label not in sessions]
        except Exception:
            check["calendar_status"] = "unverified"
    return check


def capture_evaluation_snapshot(
    symbols: Iterable[str], provider: MarketDataProvider, period: str, *,
    observed_at: datetime | None = None,
) -> EvaluationSnapshot:
    observed_at = observed_at or datetime.now(timezone.utc)
    if observed_at.utcoffset() is None:
        raise ValueError("Capture time must include a timezone")
    requested = normalize_symbols(symbols)
    frames: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    date_checks: dict[str, dict[str, Any]] = {}
    for symbol in requested:
        try:
            bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
            if bars.empty:
                raise ValueError("Empty history")
            if (not isinstance(bars.index, pd.DatetimeIndex) or bars.index.hasnans
                    or not bars.index.is_unique or not bars.index.is_monotonic_increasing):
                raise ValueError("Ordered, unique, dated history required")
            frame = bars[REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce").astype(float)
            frame.attrs = bars.attrs.copy()
            # Daily labels keep their session date, independent of provider timezone.
            frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
            if not frame.index.is_unique:
                raise ValueError("Multiple bars for one daily session")
            date_checks[symbol] = _audit_session_dates(pd.DatetimeIndex(frame.index), observed_at)
            frames[symbol] = frame
        except Exception:
            failures[symbol] = "unavailable_or_invalid_dated_history"
    return EvaluationSnapshot(requested, frames, failures, date_checks)


def holdout_start(snapshot: EvaluationSnapshot, protocol: EvaluationProtocol) -> pd.Timestamp | None:
    # The recorded capture date survives replay; neither today's clock nor OHLCV
    # validity may admit future labels or move the training boundary.
    eligible_dates: set[pd.Timestamp] = set()
    for symbol, bars in snapshot.bars_by_symbol.items():
        observed_date = snapshot.date_checks.get(symbol, {}).get("observed_date_et")
        if not isinstance(observed_date, str):
            return None
        try:
            captured_day = date.fromisoformat(observed_date)
        except ValueError:
            return None
        if captured_day.isoformat() != observed_date:
            return None
        eligible_dates.update(pd.Timestamp(label) for label in bars.index
                              if pd.Timestamp(label).date() <= captured_day)
    dates = sorted(eligible_dates)
    if len(dates) < 2:
        return None
    index = max(1, int(len(dates) * (1 - protocol.holdout_fraction)))
    return pd.Timestamp(dates[index])


@dataclass(frozen=True)
class EvaluationPhase:
    result: BacktestRunResult
    coverage: list[dict[str, Any]]
    warnings: list[str]


def _validate_values(bars: pd.DataFrame) -> bool:
    if not np.isfinite(bars.to_numpy(dtype=float)).all():
        return False
    if (bars[["open", "high", "low", "close"]] <= 0).any().any() or (bars.volume < 0).any():
        return False
    return not (
        (bars.high < bars[["open", "close", "low"]].max(axis=1))
        | (bars.low > bars[["open", "close", "high"]].min(axis=1))
    ).any()


def evaluate_phase(
    snapshot: EvaluationSnapshot,
    scan_parameters: RectangleScanParameters,
    parameters: BacktestParameters,
    *,
    phase: Literal["training", "holdout"],
    split: pd.Timestamp | None,
) -> EvaluationPhase:
    if phase not in {"training", "holdout"}:
        raise ValueError("Unsupported evaluation phase")
    results: list[BacktestResult] = []
    coverage: list[dict[str, Any]] = []
    for symbol in snapshot.symbols:
        row: dict[str, Any] = {"symbol": symbol, "phase": phase, "candidate_signal_bars": 0}
        bars = snapshot.bars_by_symbol.get(symbol)
        if bars is None:
            row["status"] = snapshot.failures.get(symbol, "unavailable")
        else:
            split_index = int(bars.index.searchsorted(split)) if split is not None else None
            # Removing the entire holdout also purges training entries AND exits at the boundary.
            window = (bars.iloc[:split_index].copy()
                      if phase == "training" and split_index is not None else bars.copy())
            start = max(200, scan_parameters.lookback + 1,
                        split_index if phase == "holdout" and split_index is not None else 0)
            stop = len(window) - parameters.entry_window_bars - parameters.max_holding_bars
            check = snapshot.date_checks.get(symbol, {})
            labels = {pd.Timestamp(label).date().isoformat() for label in window.index}
            future_dates = sorted(labels.intersection(check.get("future_dates", [])))
            non_session_dates = sorted(labels.intersection(check.get("non_session_dates", [])))
            row.update(history_bars=len(window), split_index=split_index,
                       history_start=str(window.index[0]) if len(window) else None,
                       history_end=str(window.index[-1]) if len(window) else None,
                       future_dates=future_dates, non_session_dates=non_session_dates,
                       calendar_status=check.get("calendar_status", "unverified"))
            if future_dates:
                row["status"] = "future_dated_history"
            elif split is None:
                row["status"] = "insufficient_dated_history"
            elif start >= stop:
                row["status"] = "insufficient_history_for_signals_and_outcomes"
            elif not _validate_values(window):
                row["status"] = "invalid_ohlcv"
            else:
                # The midpoint prevents float rounding from moving the engine's floor one bar early.
                fraction = (len(window) - start - 0.5) / len(window) if phase == "holdout" else 1.0
                params = parameters.model_copy(update={"evaluation_fraction": fraction})
                result = backtest_rectangle_breakouts(symbol, window, scan_parameters, params)
                results.append(result)
                row.update(status="evaluated", candidate_signal_bars=stop - start,
                           first_signal=str(window.index[start]),
                           last_signal=str(window.index[stop - 1]),
                           evaluation_fraction=fraction, trades=result.total_trades)
        coverage.append(row)
    trades = [trade for result in results for trade in result.trades]
    failed = [row["symbol"] for row in coverage if row["status"] != "evaluated"]
    warnings = []
    if any(row.get("future_dates") for row in coverage):
        warnings.append(f"Future-dated bars in {phase} history: affected symbols were not evaluated.")
    if any(row.get("non_session_dates") for row in coverage):
        warnings.append(f"Non-NYSE session dates in {phase} history. The US-equity reference calendar may not match this instrument; results are not validated session evidence.")
    if any(row.get("calendar_status") == "unverified" for row in coverage):
        warnings.append(f"Session calendar could not be verified for some {phase} history.")
    if failed:
        warnings.append(f"Incomplete {phase} coverage: {len(results)}/{len(snapshot.symbols)} symbols evaluated.")
    if len(trades) < MIN_SAMPLE_TRADES:
        warnings.append(f"Small {phase} sample: {len(trades)} trades; fewer than {MIN_SAMPLE_TRADES} is not reliable evidence.")
    return EvaluationPhase(
        BacktestRunResult(
            results=results, total_symbols=len(snapshot.symbols), total_trades=len(trades),
            win_rate=sum(trade.outcome == "win" for trade in trades) / len(trades) if trades else 0,
            average_return_pct=sum(trade.return_pct for trade in trades) / len(trades) if trades else 0,
            failed_symbols=failed,
        ), coverage, warnings,
    )
