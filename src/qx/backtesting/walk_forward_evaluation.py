"""Read-only chronological evaluation for fixed rectangle parameters.

This evaluator does not tune a rule.  It applies caller-supplied parameters to
successive, non-overlapping holdout windows so any reported result keeps its
training/holdout boundary, costs, coverage, and input dates explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

import pandas as pd

from qx.backtesting.engine import backtest_rectangle_breakouts
from qx.backtesting.walk_forward import WalkForwardConfig, WalkForwardFold, build_walk_forward_folds
from qx.models.backtest import BacktestParameters, BacktestResult, BacktestRunResult
from qx.models.scan import RectangleScanParameters


@dataclass(frozen=True)
class WalkForwardFoldResult:
    """One train/holdout result for a frozen parameter set."""

    fold: WalkForwardFold
    training: BacktestRunResult
    holdout: BacktestRunResult
    coverage: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class WalkForwardEvaluationResult:
    """Versioned output suitable for later report persistence and replay."""

    version: str
    costs: dict[str, float]
    shared_session_count: int
    folds: tuple[WalkForwardFoldResult, ...]
    warnings: tuple[str, ...]


def evaluate_rectangle_walk_forward(
    bars_by_symbol: Mapping[str, pd.DataFrame],
    *,
    as_of_date: date | str,
    fold_config: WalkForwardConfig,
    scan_parameters: RectangleScanParameters,
    backtest_parameters: BacktestParameters,
) -> WalkForwardEvaluationResult:
    """Evaluate fixed rectangle parameters over shared completed sessions.

    Each holdout only uses bars available through its own final session.  A
    symbol missing any shared label is excluded from this evaluation rather
    than receiving a shifted date boundary.
    """
    normalized = {symbol.strip().upper(): frame.copy() for symbol, frame in bars_by_symbol.items() if symbol.strip()}
    if not normalized:
        raise ValueError("At least one symbol history is required")
    frames = {symbol: _normalize_frame(frame) for symbol, frame in normalized.items()}
    shared_dates = _shared_dates(frames)
    folds = build_walk_forward_folds(shared_dates, fold_config, as_of_date=as_of_date)
    if not folds:
        return WalkForwardEvaluationResult(
            version="rectangle-walk-forward-v1",
            costs=_costs(backtest_parameters),
            shared_session_count=len(shared_dates),
            folds=(),
            warnings=("No complete walk-forward fold is available for the supplied history.",),
        )

    results = tuple(
        _evaluate_fold(frames, fold, scan_parameters, backtest_parameters)
        for fold in folds
    )
    warnings = [
        "Parameters are caller-supplied and are not selected or optimized by this evaluator.",
        "Results use current supplied histories; historical membership and survivorship bias remain separate evidence requirements.",
    ]
    if any(result.holdout.total_trades == 0 for result in results):
        warnings.append("One or more holdout folds produced no trades; no performance inference should be drawn from them.")
    return WalkForwardEvaluationResult(
        version="rectangle-walk-forward-v1",
        costs=_costs(backtest_parameters),
        shared_session_count=len(shared_dates),
        folds=results,
        warnings=tuple(warnings),
    )


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Walk-forward histories require a DatetimeIndex")
    normalized = frame.copy()
    normalized.index = pd.DatetimeIndex(normalized.index).tz_localize(None).normalize()
    if normalized.index.has_duplicates or not normalized.index.is_monotonic_increasing:
        raise ValueError("Walk-forward histories require ascending unique session dates")
    return normalized


def _shared_dates(frames: Mapping[str, pd.DataFrame]) -> tuple[date, ...]:
    date_sets = [{timestamp.date() for timestamp in frame.index} for frame in frames.values()]
    shared = set.intersection(*date_sets)
    if not shared:
        raise ValueError("No shared completed sessions across supplied histories")
    return tuple(sorted(shared))


def _evaluate_fold(
    frames: Mapping[str, pd.DataFrame],
    fold: WalkForwardFold,
    scan_parameters: RectangleScanParameters,
    parameters: BacktestParameters,
) -> WalkForwardFoldResult:
    training_results: list[BacktestResult] = []
    holdout_results: list[BacktestResult] = []
    coverage: list[dict[str, object]] = []
    train_end = pd.Timestamp(fold.train_dates[-1])
    holdout_start = pd.Timestamp(fold.holdout_dates[0])
    holdout_end = pd.Timestamp(fold.holdout_dates[-1])
    for symbol, frame in frames.items():
        training_frame = frame.loc[:train_end]
        holdout_frame = frame.loc[:holdout_end]
        holdout_start_index = int(holdout_frame.index.searchsorted(holdout_start))
        row: dict[str, object] = {
            "symbol": symbol,
            "training_bars": len(training_frame),
            "holdout_bars": len(holdout_frame) - holdout_start_index,
        }
        try:
            training = backtest_rectangle_breakouts(symbol, training_frame, scan_parameters, parameters)
            holdout_parameters = parameters.model_copy(update={
                "evaluation_fraction": (len(holdout_frame) - holdout_start_index - 0.5) / len(holdout_frame),
            })
            holdout = backtest_rectangle_breakouts(symbol, holdout_frame, scan_parameters, holdout_parameters)
        except (KeyError, ValueError, ZeroDivisionError):
            row["status"] = "invalid_or_insufficient_history"
        else:
            row.update(status="evaluated", training_trades=training.total_trades, holdout_trades=holdout.total_trades)
            training_results.append(training)
            holdout_results.append(holdout)
        coverage.append(row)
    return WalkForwardFoldResult(
        fold=fold,
        training=_aggregate(training_results, len(frames), coverage),
        holdout=_aggregate(holdout_results, len(frames), coverage),
        coverage=tuple(coverage),
    )


def _aggregate(results: list[BacktestResult], total_symbols: int, coverage: list[dict[str, object]]) -> BacktestRunResult:
    trades = [trade for result in results for trade in result.trades]
    return BacktestRunResult(
        results=results,
        total_symbols=total_symbols,
        total_trades=len(trades),
        win_rate=sum(trade.outcome == "win" for trade in trades) / len(trades) if trades else 0.0,
        average_return_pct=sum(trade.return_pct for trade in trades) / len(trades) if trades else 0.0,
        failed_symbols=sorted(str(row["symbol"]) for row in coverage if row.get("status") != "evaluated"),
    )


def _costs(parameters: BacktestParameters) -> dict[str, float]:
    return {
        "fee_bps_per_side": parameters.fee_bps_per_side,
        "slippage_bps_per_side": parameters.slippage_bps_per_side,
    }
