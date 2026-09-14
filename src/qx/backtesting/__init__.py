"""QX Advanced Backtesting & Walk-Forward Optimization Engine Package."""

from qx.backtesting.engine import backtest_rectangle_breakouts
from qx.backtesting.evaluation_protocol import (
    EvaluationPhase,
    EvaluationProtocol,
    EvaluationSnapshot,
    capture_evaluation_snapshot,
    evaluate_phase,
    holdout_start,
)
from qx.backtesting.evaluation_report import (
    build_evaluation_report,
    evaluate_fixed_snapshot,
    save_evaluation_report,
    validate_report,
)
from qx.backtesting.walk_forward import (
    WalkForwardConfig,
    WalkForwardFold,
    build_walk_forward_folds,
)

__all__ = [
    "backtest_rectangle_breakouts",
    "build_evaluation_report",
    "build_walk_forward_folds",
    "capture_evaluation_snapshot",
    "evaluate_fixed_snapshot",
    "evaluate_phase",
    "holdout_start",
    "save_evaluation_report",
    "validate_report",
    "EvaluationPhase",
    "EvaluationProtocol",
    "EvaluationSnapshot",
    "WalkForwardConfig",
    "WalkForwardFold",
]


