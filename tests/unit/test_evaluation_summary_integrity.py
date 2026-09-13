from copy import deepcopy

import pytest

from qx.backtesting import evaluation_report as reports
from tests.unit.test_strategy_evaluation_protocol_20260911 import (
    EvaluationProvider, evaluation_bars, fixed_spec, predictable_setups,  # noqa: F401
)
from tests.unit.test_strategy_evaluation_reports_20260911 import fixed_report


pytestmark = pytest.mark.usefixtures("predictable_setups")


def rehash(report):
    report["data"]["sha256"] = reports.content_hash(report["data"]["symbols"])
    report["spec_sha256"] = reports.content_hash(report["spec"])
    report["report_id"] = reports.content_hash({
        key: value for key, value in report.items() if key not in {"report_id", "generated_at"}
    })
    return report


@pytest.mark.parametrize("path,value", [
    (("result", "total_trades"), 999),
    (("result", "total_symbols"), True),
    (("result", "win_rate"), 0.123456),
    (("result", "average_return_pct"), 0.987654),
    (("result", "results", 0, "total_trades"), 999),
    (("result", "results", 0, "win_rate"), 0.123456),
    (("result", "results", 0, "average_return_pct"), 0.987654),
    (("result", "results", 0, "symbol"), "OTHER"),
    (("result", "results", 0, "trades", 0, "symbol"), "OTHER"),
    (("result", "results", 0, "trades", 0, "outcome"), "profit"),
    (("result", "failed_symbols"), ["TEST"]),
    (("coverage", 0, "trades"), 999),
    (("coverage", 0, "phase"), "training"),
    (("coverage", 0, "status"), "unavailable"),
    (("coverage",), {}),
    (("mean_net_trade_return",), 0.987654),
    (("target_hit_rate",), 0.123456),
    (("positive_net_trades",), 999),
    (("positive_net_trades",), True),
])
def test_rehashed_inconsistent_summary_is_rejected(path, value):
    report = fixed_report()
    payload = report["results"]["holdout"]
    assert payload["result"]["total_trades"] > 0
    for key in path[:-1]:
        payload = payload[key]
    payload[path[-1]] = value
    with pytest.raises(ValueError):
        reports.validate_report(rehash(report))


@pytest.mark.parametrize("field", ["fee_bps_per_side", "slippage_bps_per_side"])
def test_selected_candidate_cannot_change_reported_costs(field):
    report = fixed_report()
    report["selected_parameters"][field] += 1
    with pytest.raises(ValueError, match="cost"):
        reports.validate_report(rehash(report))


def test_duplicate_input_membership_cannot_inflate_distinct_coverage():
    report = fixed_report()
    report["data"]["symbols"].append(deepcopy(report["data"]["symbols"][0]))
    report["spec"]["universe"]["exact_symbols"].append("TEST")
    payload = report["results"]["holdout"]
    payload["coverage"].append(deepcopy(payload["coverage"][0]))
    payload["result"]["total_symbols"] = 2
    with pytest.raises(ValueError, match="symbols"):
        reports.validate_report(rehash(report))


def test_inconsistent_saved_report_is_skipped_without_running_evaluation(tmp_path, monkeypatch):
    report = fixed_report()
    report["results"]["holdout"]["result"]["total_trades"] += 1
    rehash(report)
    saved = tmp_path / f"{report['report_id']}.json"
    saved.write_text(reports.report_json(report), encoding="utf-8")
    before = saved.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved lookup must not evaluate strategies")

    monkeypatch.setattr(reports, "evaluate_phase", forbidden)
    assert reports.latest_compatible_report(report["spec"], tmp_path) is None
    assert saved.read_bytes() == before


def test_empty_and_failed_coverage_keep_null_display_metrics():
    from qx.backtesting.evaluation_protocol import capture_evaluation_snapshot

    snapshot = capture_evaluation_snapshot(["MISSING"], EvaluationProvider({}), "2y")
    report = reports.evaluate_fixed_snapshot(fixed_spec(["MISSING"]), snapshot)
    reports.validate_report(report)
    phase = report["results"]["holdout"]
    assert phase["mean_net_trade_return"] is None
    assert phase["target_hit_rate"] is None
    assert phase["positive_net_trades"] == 0


def test_zero_trade_evaluated_symbol_is_not_failed_coverage(monkeypatch):
    from qx.backtesting import engine
    from qx.backtesting.evaluation_protocol import capture_evaluation_snapshot

    def no_setup(*args, **kwargs):
        raise ValueError("No qualifying setup")

    monkeypatch.setattr(engine, "analyze_rectangle", no_setup)
    spec = fixed_spec(["TEST"])
    snapshot = capture_evaluation_snapshot(["TEST"], EvaluationProvider({"TEST": evaluation_bars()}), "2y")
    report = reports.evaluate_fixed_snapshot(spec, snapshot)
    reports.validate_report(report)
    phase = report["results"]["holdout"]
    assert phase["result"]["total_trades"] == 0
    assert phase["result"]["failed_symbols"] == []
    assert phase["coverage"][0]["status"] == "evaluated"


def test_target_hits_can_have_negative_net_returns_after_costs():
    from qx.backtesting.evaluation_protocol import capture_evaluation_snapshot

    spec = fixed_spec(["TEST"])
    spec["backtest_parameters"]["fee_bps_per_side"] = 1000.0
    spec["costs"]["fee_bps_per_side"] = 1000.0
    snapshot = capture_evaluation_snapshot(["TEST"], EvaluationProvider({"TEST": evaluation_bars()}), "2y")
    report = reports.evaluate_fixed_snapshot(spec, snapshot)
    reports.validate_report(report)
    phase = report["results"]["holdout"]
    assert phase["target_hit_rate"] == 1.0
    assert phase["mean_net_trade_return"] < 0
    assert phase["positive_net_trades"] == 0


def test_backtest_page_skips_inconsistent_saved_totals_without_work(tmp_path, monkeypatch):
    from qx.backtesting.evaluation_protocol import capture_evaluation_snapshot
    from qx.ui.pages import backtest
    from tests.unit.test_strategy_evaluation_ui_20260911 import app_for

    captured_specs = []
    monkeypatch.setattr(backtest, "latest_compatible_report", lambda spec: captured_specs.append(spec))
    initial = app_for("backtest").run()
    assert not initial.exception
    spec = captured_specs[0]
    symbols = spec["universe"]["exact_symbols"]
    snapshot = capture_evaluation_snapshot(
        symbols, EvaluationProvider({symbol: evaluation_bars() for symbol in symbols}), "2y")
    report = reports.evaluate_fixed_snapshot(spec, snapshot)
    report["results"]["holdout"]["result"]["average_return_pct"] = 0.987654
    rehash(report)
    path = tmp_path / f"{report['report_id']}.json"
    path.write_text(reports.report_json(report), encoding="utf-8")
    original = path.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("Page entry cannot fetch, evaluate or save")

    monkeypatch.setattr(backtest, "latest_compatible_report", lambda spec: reports.latest_compatible_report(spec, tmp_path))
    monkeypatch.setattr(backtest, "capture_evaluation_snapshot", forbidden)
    monkeypatch.setattr(backtest, "save_evaluation_report", forbidden)
    monkeypatch.setattr(reports, "evaluate_phase", forbidden)
    app = app_for("backtest").run()
    assert not app.exception
    assert any("No saved evaluation" in item.value for item in app.info)
    assert not any(item.value == "Historical Evaluation" for item in app.subheader)
    assert path.read_bytes() == original
