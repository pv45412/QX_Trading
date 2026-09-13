import pandas as pd
import pytest

from qx.backtesting.engine import backtest_rectangle_universe
from tests.unit.test_market_regime import _bars


@pytest.mark.parametrize("symbols, evaluated, failed", [
    ([" good ", "GOOD", "bad", "BAD", ""], ["GOOD"], ["BAD"]),
    (["bad"], [], ["BAD"]),
    (["empty"], [], ["EMPTY"]),
    ([], [], []),
])
def test_backtest_reports_unavailable_symbols(symbols, evaluated, failed):
    class Provider:
        def get_daily_bars(self, request):
            if request.symbol == "BAD":
                raise ValueError("private provider details")
            return pd.DataFrame() if request.symbol == "EMPTY" else _bars(100.0, 0.4)

    result = backtest_rectangle_universe(symbols, Provider())
    assert [item.symbol for item in result.results] == evaluated
    assert result.failed_symbols == failed
    assert result.total_symbols == len(evaluated) + len(failed)
    assert "private provider" not in result.model_dump_json()


def test_empty_coverage_is_not_presented_as_strategy_result():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
from qx.models.backtest import BacktestRunResult
from qx.ui.pages.backtest import _render_backtest_result
import streamlit as st
result = BacktestRunResult(results=[], total_symbols=1, total_trades=0,
    win_rate=0, average_return_pct=0, failed_symbols=["BAD"])
_render_backtest_result(st, result)
''').run()
    assert not app.exception
    assert "Evaluated 0 of 1" in app.caption[0].value
    assert "BAD" in app.warning[0].value
    assert "No symbols were evaluated" in app.error[0].value
