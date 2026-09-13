from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys

from qx.models.backtest import BacktestResult
from tests.unit.test_market_regime import _bars


def test_cached_holdout_records_inputs_costs_and_coverage(tmp_path, monkeypatch, capsys):
    symbols = tmp_path / "symbols.csv"
    symbols.write_text("symbol\nGOOD\nMISSING\nBAD\nSHORT\n", encoding="utf-8")
    good = _bars(100.0, 0.35)
    good.to_csv(tmp_path / "GOOD_2y.csv")
    bad = good.copy()
    bad.loc[bad.index[-1], "high"] = 1
    bad.to_csv(tmp_path / "BAD_2y.csv")
    good.head(200).to_csv(tmp_path / "SHORT_2y.csv")
    output = tmp_path / "report.json"
    calls = []

    def evaluate(symbol, bars, scan, params):
        calls.append((symbol, params))
        return BacktestResult(symbol=symbol, trades=[], total_trades=0, win_rate=0, average_return_pct=0)

    monkeypatch.setattr("qx.backtesting.engine.backtest_rectangle_breakouts", evaluate)
    monkeypatch.setattr(sys, "argv", ["evaluate", "--symbols", str(symbols), "--bars", str(tmp_path), "--output", str(output)])
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/evaluate_cached_holdout.py"), run_name="__main__")
    report = json.loads(capsys.readouterr().out)
    assert report == json.loads(output.read_text(encoding="utf-8"))
    assert report["requested"] == 4
    assert report["evaluated"] == 1
    assert report["trades"] == 0
    row = report["symbols"][0]
    assert row["mean_net_return"] is None
    assert row["input_sha256"] == sha256((tmp_path / "GOOD_2y.csv").read_bytes()).hexdigest()
    assert row["first_signal"] == str(good.index[200])
    assert row["last_signal"] == str(good.index[234])
    assert len(calls) == 1
    params = calls[0][1]
    assert (params.evaluation_fraction, params.fee_bps_per_side, params.slippage_bps_per_side) == (.25, 1, 5)
