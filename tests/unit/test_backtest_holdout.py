import pandas as pd
from qx.backtesting import engine
from qx.models.backtest import BacktestParameters


def test_holdout_only_evaluates_final_quarter_signals(monkeypatch):
    histories = []
    def analyze(symbol, history, params):
        histories.append(len(history))
        raise ValueError("No setup")
    monkeypatch.setattr(engine, "analyze_rectangle", analyze)
    bars = pd.DataFrame({"close": [100.] * 400})
    engine.backtest_rectangle_breakouts("TEST", bars, backtest_parameters=BacktestParameters(evaluation_fraction=.25))
    assert histories
    assert min(histories) == 301
    assert max(histories) <= 400 - 25
    assert bars.shape[0] == 400
