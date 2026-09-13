from qx.backtesting.strategy_lab import compare_rectangle_strategies, strategy_lab_frame
from qx.models.scan import RectangleScanParameters
from tests.unit.test_backtest import _StaticProvider


def test_strategy_lab_scores_parameter_grid() -> None:
    result = compare_rectangle_strategies(
        ["TEST"],
        _StaticProvider(),
        period="2y",
        scan_parameters=RectangleScanParameters(),
    )
    frame = strategy_lab_frame(result)

    assert result.recommendation
    assert not frame.empty
    assert "strategy_score" in frame.columns

