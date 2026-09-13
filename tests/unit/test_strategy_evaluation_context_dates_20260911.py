from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from qx.backtesting import evaluation_protocol as protocol
from qx.backtesting.evaluation_report import replay_evaluation_report, snapshot_payload
from qx.backtesting.strategy_lab import STRATEGY_GRID, evaluate_strategy_snapshot
from qx.ui.pages import backtest, strategy_lab
from tests.unit.test_strategy_evaluation_protocol_20260911 import (
    EvaluationProvider,
    evaluation_bars,
    fixed_spec,
    predictable_setups,  # noqa: F401
)
from tests.unit.test_strategy_evaluation_ui_20260911 import app_for

pytestmark = pytest.mark.usefixtures("predictable_setups")


@pytest.mark.parametrize("page", ["backtest", "strategy_lab"])
def test_evaluation_context_seeds_and_tracks_scope_without_running(monkeypatch, page):
    module = backtest if page == "backtest" else strategy_lab
    observed_scopes = []
    def symbols(universe, text):
        observed_scopes.append((universe, text))
        return ["TSLA"]
    def forbidden(*args, **kwargs):
        raise AssertionError("Navigation must not evaluate data")
    monkeypatch.setattr(module, "cached_evaluation_symbols", symbols)
    monkeypatch.setattr(module, "capture_evaluation_snapshot", forbidden)
    monkeypatch.setattr(backtest, "latest_compatible_report", lambda spec: None)
    app = app_for(page)
    app.query_params.update(universe="custom", symbol="TSLA", period="5y", sector="Technology")
    app.run()
    assert not app.exception
    assert app.selectbox[0].value == "Custom"
    assert app.text_area[0].value == "TSLA"
    history = next(widget for widget in app.selectbox if "history" in widget.label.lower())
    assert history.value == "5y"
    history.set_value("3y").run()
    app.text_area[0].set_value("AMD").run()
    assert not app.exception
    assert app.query_params["symbol"] == ["AMD"]
    assert app.query_params["period"] == ["3y"]
    assert app.query_params["sector"] == ["Technology"]
    app.selectbox[0].set_value("S&P 500").run()
    assert not app.exception
    assert app.query_params["universe"] == ["sp500"]
    assert observed_scopes[-1][0] == "S&P 500"


@pytest.mark.parametrize("page", ["backtest", "strategy_lab"])
def test_named_universe_and_one_year_history_seed_from_context(monkeypatch, page):
    module = backtest if page == "backtest" else strategy_lab
    monkeypatch.setattr(module, "cached_evaluation_symbols", lambda universe, text: ["TEST"])
    monkeypatch.setattr(backtest, "latest_compatible_report", lambda spec: None)
    app = app_for(page)
    app.query_params.update(universe="nasdaq_100", period="1y")
    app.run()
    assert not app.exception
    assert app.selectbox[0].value == "NASDAQ 100"
    assert next(widget for widget in app.selectbox if "history" in widget.label.lower()).value == "1y"


@pytest.mark.parametrize("page", ["backtest", "strategy_lab"])
@pytest.mark.parametrize("selection", [
    {"as_of": "2021-01-04", "snapshot": "7"}, {"snapshot": "7"}, {"as_of": "invalid"},
])
def test_historical_navigation_blocks_current_data_and_saved_report_lookup(monkeypatch, page, selection):
    module = backtest if page == "backtest" else strategy_lab
    def forbidden(*args, **kwargs):
        raise AssertionError("Historical navigation must not load current evidence")
    monkeypatch.setattr(module, "cached_evaluation_symbols", forbidden)
    monkeypatch.setattr(module, "capture_evaluation_snapshot", forbidden)
    monkeypatch.setattr(backtest, "latest_compatible_report", forbidden)
    app = app_for(page)
    app.query_params.update(universe="custom", symbol="TSLA", period="5y", sector="Technology", **selection)
    app.run()
    assert not app.exception
    assert next(button for button in app.button if button.label.startswith("Run ")).disabled
    assert any("current cached data was not evaluated" in warning.value for warning in app.warning)
    link = app.get("link_button")[0]
    assert link.label == "Use current evidence"
    query = parse_qs(urlparse(link.proto.url).query)
    assert query == {"page": [page], "universe": ["custom"], "symbol": ["TSLA"],
                     "period": ["5y"], "sector": ["Technology"]}
    app.text_area[0].set_value("AMD").run()
    query = parse_qs(urlparse(app.get("link_button")[0].proto.url).query)
    assert query["symbol"] == ["AMD"]
    assert not app.exception
    assert "as_of" not in query and "snapshot" not in query


def test_future_sessions_block_holdout_but_do_not_change_training_selection():
    bars = evaluation_bars()
    observed = pd.Timestamp(bars.index[400]).to_pydatetime().replace(hour=22, tzinfo=timezone.utc)
    snapshots = [protocol.capture_evaluation_snapshot(
        ["TEST"], EvaluationProvider({"TEST": frame}), "2y", observed_at=observed)
        for frame in (bars.iloc[:401], bars)]
    spec = {**fixed_spec(["TEST"]), "kind": "training_selection", "grid": STRATEGY_GRID}
    baseline, extended = [evaluate_strategy_snapshot(spec, snapshot) for snapshot in snapshots]
    assert baseline.rows == extended.rows
    assert baseline.report["selected_parameters"] == extended.report["selected_parameters"]
    assert baseline.report["results"]["training"] == extended.report["results"]["training"]
    assert baseline.report["split"]["holdout_start"] == str(bars.index[300])
    assert extended.report["split"] == baseline.report["split"]
    heldout = extended.report["results"]["holdout"]
    assert heldout["result"]["total_trades"] == 0
    assert heldout["coverage"][0]["status"] == "future_dated_history"
    assert any("Future-dated" in warning for warning in heldout["warnings"])
    assert baseline.report["results"]["holdout"]["result"]["total_trades"] > 0
    assert extended.report["data"]["symbols"][0]["date_validation"]["future_dates"]
    pd.testing.assert_frame_equal(snapshots[1].bars_by_symbol["TEST"], bars)
    replayed = replay_evaluation_report(extended.report)
    assert replayed["report_id"] == extended.report["report_id"]
    assert replayed["data"] == extended.report["data"]
    assert replayed["results"] == extended.report["results"]


def test_weekends_and_holidays_flagged_without_removing_or_reordering_bars():
    bars = evaluation_bars(10)
    bars.index = pd.date_range("2021-07-01", periods=10, freq="D")
    snapshot = protocol.capture_evaluation_snapshot(
        ["TEST"], EvaluationProvider({"TEST": bars}), "2y",
        observed_at=datetime(2021, 7, 12, 22, tzinfo=timezone.utc))
    check = snapshot_payload(snapshot)["symbols"][0]["date_validation"]
    assert check["reference_calendar"] == "NYSE"
    assert check["observed_date_et"] == "2021-07-12"
    assert {"2021-07-03", "2021-07-04", "2021-07-05"}.issubset(check["non_session_dates"])
    assert not check["future_dates"]
    pd.testing.assert_frame_equal(snapshot.bars_by_symbol["TEST"], bars)
