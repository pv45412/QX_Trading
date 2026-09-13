from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from qx.backtesting.evaluation_protocol import capture_evaluation_snapshot
from qx.backtesting.evaluation_report import evaluate_fixed_snapshot
from qx.models.backtest import BacktestRunResult
from qx.ui.pages import backtest, strategy_lab
from tests.unit.test_strategy_evaluation_protocol_20260911 import (
    EvaluationProvider,
    evaluation_bars,
    predictable_setups,  # noqa: F401
)
from tests.unit.test_strategy_evaluation_reports_20260911 import fixed_report

pytestmark = pytest.mark.usefixtures("predictable_setups")


def app_for(page):
    return AppTest.from_string(
        f"import streamlit as st\nfrom qx.ui.pages.{page} import render_{page}_page\n"
        f"render_{page}_page(st)"
    )


@pytest.mark.parametrize("page", ["backtest", "strategy_lab"])
def test_essential_controls_and_run_in_body_with_no_initial_evaluation(monkeypatch, page):
    module = backtest if page == "backtest" else strategy_lab
    monkeypatch.setattr(backtest, "latest_compatible_report", lambda spec: None)
    def forbidden(*args, **kwargs):
        raise AssertionError("No automatic evaluation, download or save")
    monkeypatch.setattr(module, "capture_evaluation_snapshot", forbidden)
    monkeypatch.setattr(backtest, "save_evaluation_report", forbidden)
    app = app_for(page).run()
    assert not app.exception
    assert len(app.sidebar.button) == 0
    assert len(app.sidebar.selectbox) == 0
    assert len(app.sidebar.number_input) == 0
    assert any(button.label.startswith("Run ") for button in app.main.button)
    assert [widget.value for widget in app.main.number_input] == [0.0, 5.0]
    assert any("No saved evaluation" in item.value for item in app.info)


@pytest.mark.parametrize("page", ["backtest", "strategy_lab"])
def test_results_survive_rerender_and_save_requires_explicit_action(monkeypatch, page):
    module = backtest if page == "backtest" else strategy_lab
    reads, saves = [], []
    monkeypatch.setattr(backtest, "latest_compatible_report", lambda spec: None)
    def snapshot(symbols, provider, period):
        reads.append(tuple(symbols))
        return capture_evaluation_snapshot(
            symbols, EvaluationProvider({symbol: evaluation_bars() for symbol in symbols}), period)
    def save(report):
        saves.append(report)
        return Path("test-only-report.json")
    monkeypatch.setattr(module, "capture_evaluation_snapshot", snapshot)
    monkeypatch.setattr(backtest, "save_evaluation_report", save)
    app = app_for(page).run()
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert len(reads) == 1
    assert not saves
    state_key = "backtest_report" if page == "backtest" else "strategy_lab_report"
    report_id = app.session_state[state_key]["report_id"]
    app.run()
    assert not app.exception
    assert app.session_state[state_key]["report_id"] == report_id
    assert len(reads) == 1
    assert not saves
    next(button for button in app.button if button.label == "Save evaluation report").click().run()
    assert not app.exception
    assert len(reads) == 1
    assert len(saves) == 1
    app.number_input[0].set_value(2.0).run()
    assert not app.exception
    assert not any(button.label == "Save evaluation report" for button in app.button)
    assert len(reads) == 1


def test_initial_saved_report_is_historical_and_does_not_read_bars(monkeypatch):
    saved = []
    def lookup(spec):
        snapshot = capture_evaluation_snapshot(
            spec["universe"]["exact_symbols"],
            EvaluationProvider({symbol: evaluation_bars() for symbol in spec["universe"]["exact_symbols"]}),
            "2y",
        )
        report = evaluate_fixed_snapshot(spec, snapshot)
        saved.append(report)
        return report
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved reports must not read current bars or rerun")
    monkeypatch.setattr(backtest, "latest_compatible_report", lookup)
    monkeypatch.setattr(backtest, "capture_evaluation_snapshot", forbidden)
    monkeypatch.setattr(backtest, "save_evaluation_report", forbidden)
    app = app_for("backtest").run()
    assert not app.exception
    assert len(saved) == 1
    assert any("Historical Evaluation" in item.value for item in app.subheader)
    assert any("current cache not revalidated" in item.value for item in app.caption)
    assert any("No performance guarantees" in item.value for item in app.warning)
    app.run()
    assert not app.exception
    assert len(saved) == 1


def test_all_positive_trades_do_not_show_finite_profit_factor_one():
    report = fixed_report()
    result = BacktestRunResult.model_validate(report["results"]["holdout"]["result"])
    analytics = backtest.backtest_analytics(result)
    assert result.total_trades > 0
    assert analytics["profit_factor"] == float("inf")
    assert backtest._profit_factor_text(analytics["profit_factor"]) == "No losses"
