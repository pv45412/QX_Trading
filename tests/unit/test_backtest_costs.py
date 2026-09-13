import pytest
from qx.models.backtest import BacktestParameters
from qx.backtesting.engine import net_trade_return


def test_costs_apply_to_both_sides():
    params = BacktestParameters(fee_bps_per_side=10, slippage_bps_per_side=20)
    assert net_trade_return(100, 110, params) == pytest.approx(110*.998*.999/(100*1.002*1.001)-1)
    assert net_trade_return(100, 110, BacktestParameters()) == pytest.approx(.1)
    assert net_trade_return(100, 100.1, params) < 0


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), 1001])
def test_invalid_cost_assumptions_rejected(value):
    with pytest.raises(ValueError):
        BacktestParameters(slippage_bps_per_side=value)
