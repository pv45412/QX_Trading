from dataclasses import dataclass
from typing import Any

import pandas as pd

from qx.backtesting.evaluation_protocol import (
    MIN_SAMPLE_TRADES,
    EvaluationProtocol,
    EvaluationSnapshot,
    capture_evaluation_snapshot,
    evaluate_phase,
    evaluation_parameters,
    holdout_start,
)
from qx.backtesting.evaluation_report import build_evaluation_report, evaluation_spec
from qx.data.providers import MarketDataProvider
from qx.models.backtest import BacktestParameters
from qx.models.scan import RectangleScanParameters

STRATEGY_GRID: dict[str, list[float] | list[int]] = {
    "setup_scores": [0.55, 0.65, 0.75, 0.85], "entry_windows": [3, 5, 10],
}


@dataclass(frozen=True)
class StrategyLabResult:
    rows: list[dict[str, Any]]
    recommendation: str
    report: dict[str, Any]


def compare_rectangle_strategies(
    symbols: list[str],
    provider: MarketDataProvider,
    *,
    period: str,
    scan_parameters: RectangleScanParameters,
    backtest_parameters: BacktestParameters | None = None,
    protocol: EvaluationProtocol | None = None,
    universe: str = "Custom",
    profile: str = "Custom parameters",
) -> StrategyLabResult:
    spec = evaluation_spec(
        symbols, universe=universe, period=period, profile=profile,
        scan_parameters=scan_parameters,
        parameters=backtest_parameters or evaluation_parameters(),
        protocol=protocol or EvaluationProtocol(), kind="training_selection", grid=STRATEGY_GRID,
    )
    snapshot = capture_evaluation_snapshot(symbols, provider, period)
    return evaluate_strategy_snapshot(spec, snapshot)


def strategy_lab_frame(result: StrategyLabResult) -> pd.DataFrame:
    return pd.DataFrame(result.rows)


def evaluate_strategy_snapshot(
    spec: dict[str, Any], snapshot: EvaluationSnapshot
) -> StrategyLabResult:
    scan = RectangleScanParameters.model_validate(spec["scan_parameters"])
    base = BacktestParameters.model_validate(spec["backtest_parameters"])
    split = holdout_start(snapshot, EvaluationProtocol.model_validate(spec["protocol"]))
    grid = spec["grid"]
    trials = []
    for score in grid["setup_scores"]:
        for window in grid["entry_windows"]:
            params = BacktestParameters(**{
                **base.model_dump(), "min_setup_score": score,
                "entry_window_bars": window, "evaluation_fraction": 1.0,
            })
            training = evaluate_phase(snapshot, scan, params, phase="training", split=split)
            run = training.result
            row = {
                "min_setup_score": score, "entry_window_bars": window,
                "symbols": run.total_symbols, "evaluated_symbols": len(run.results),
                "failed_symbols": run.failed_symbols,
                "candidate_signal_bars": sum(item["candidate_signal_bars"] for item in training.coverage),
                "coverage": training.coverage, "warnings": training.warnings,
                "trades": run.total_trades,
                "win_rate": run.win_rate if run.total_trades else None,
                "average_return_pct": run.average_return_pct if run.total_trades else None,
                "strategy_score": run.average_return_pct if run.total_trades else None,
                "label": "Small training sample" if run.total_trades < MIN_SAMPLE_TRADES else "Training only",
                "fee_bps_per_side": params.fee_bps_per_side,
                "slippage_bps_per_side": params.slippage_bps_per_side,
            }
            trials.append((row, params, training))
    trials.sort(key=lambda trial: (
        trial[0]["trades"] > 0, trial[0]["average_return_pct"] or 0,
        trial[0]["trades"], trial[0]["min_setup_score"], -trial[0]["entry_window_bars"],
    ), reverse=True)
    rows = [trial[0] for trial in trials]
    selected = trials[0] if trials and trials[0][0]["trades"] else None
    # Holdout outcomes are computed only AFTER the training ranking is finalized.
    heldout = evaluate_phase(snapshot, scan, selected[1], phase="holdout", split=split) if selected else None
    report = build_evaluation_report(
        spec, snapshot, training=selected[2] if selected else None,
        heldout=heldout, selected_parameters=selected[1] if selected else None, training_rows=rows,
    )
    recommendation = "No candidate selected: no usable training trades. Holdout was not evaluated."
    if selected:
        recommendation = (
            f"Exploratory training selection: setup score >= {selected[1].min_setup_score}, "
            f"{selected[1].entry_window_bars} breakout bars. "
            "Frozen before holdout evaluation; not a production recommendation."
        )
    return StrategyLabResult(rows=rows, recommendation=recommendation, report=report)
