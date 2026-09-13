from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from qx.backtesting import evaluation_protocol as protocol
from qx.backtesting import evaluation_report
from qx.backtesting.evaluation_report import (
    content_hash,
    evaluate_fixed_snapshot,
    latest_compatible_report,
    replay_evaluation_report,
    report_json,
    save_evaluation_report,
    validate_report,
)
from tests.unit.test_strategy_evaluation_protocol_20260911 import (
    EvaluationProvider,
    evaluation_bars,
    fixed_spec,
    predictable_setups,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("predictable_setups")


def fixed_report():
    bars = evaluation_bars()
    bars.attrs["provenance"] = {"actual_source": "test_fixture", "retrieved_at": "2021-11-02T21:00:00+00:00"}
    snapshot = protocol.capture_evaluation_snapshot(["TEST"], EvaluationProvider({"TEST": bars}), "2y")
    return evaluate_fixed_snapshot(fixed_spec(["TEST"]), snapshot)


def test_report_contains_reproducible_inputs_and_is_stable_across_creation_times():
    report = fixed_report()
    loaded = json.loads(report_json(report))
    validate_report(loaded)
    assert report == loaded
    record = report["data"]["symbols"][0]
    assert record["actual_source"] == "test_fixture"
    assert record["bar_count"] == 480
    assert record["input_sha256"] == content_hash(record["inputs"])
    assert report["spec"]["universe"]["exact_symbols"] == ["TEST"]
    assert report["spec"]["profile"] == "Test"
    assert report["spec"]["scan_parameters"]["lookback"] == 40
    assert "backtesting/engine.py" in report["spec"]["implementation"]["sources"]
    assert any("No performance guarantees" in value for value in report["warnings"])
    loaded["generated_at"] = "2030-01-01T00:00:00+00:00"
    validate_report(loaded)
    replayed = replay_evaluation_report(loaded)
    assert replayed["report_id"] == report["report_id"]
    assert replayed["results"] == report["results"]


def test_input_change_and_assumption_change_have_distinct_identities():
    first = fixed_report()
    bars = evaluation_bars()
    bars.iloc[-1, bars.columns.get_loc("close")] = 102.0
    snapshot = protocol.capture_evaluation_snapshot(["TEST"], EvaluationProvider({"TEST": bars}), "2y")
    second = evaluate_fixed_snapshot(first["spec"], snapshot)
    assert first["data"]["sha256"] != second["data"]["sha256"]
    assert first["report_id"] != second["report_id"]
    spec = deepcopy(first["spec"])
    spec["backtest_parameters"]["fee_bps_per_side"] = 10
    spec["costs"]["fee_bps_per_side"] = 10
    third = evaluate_fixed_snapshot(spec, snapshot)
    assert third["spec_sha256"] != second["spec_sha256"]
    assert third["results"] != second["results"]


@pytest.mark.parametrize("section", ["spec", "data", "results"])
def test_modified_report_is_rejected(section):
    report = fixed_report()
    report[section]["tampered"] = True
    with pytest.raises(ValueError):
        validate_report(report)


def test_explicit_save_and_exact_compatibility_only(tmp_path):
    directory = tmp_path / "reports"
    report = fixed_report()
    assert latest_compatible_report(report["spec"], directory) is None
    assert not directory.exists()
    path = save_evaluation_report(report, directory)
    before = path.read_bytes()
    assert latest_compatible_report(report["spec"], directory) == report
    assert path.read_bytes() == before
    assert save_evaluation_report(report, directory) == path
    assert len(list(directory.iterdir())) == 1
    for field in ("period", "profile", "universe", "costs", "protocol", "implementation"):
        changed = deepcopy(report["spec"])
        changed[field] = "incompatible"
        assert latest_compatible_report(changed, directory) is None


def test_bad_saved_report_is_skipped_and_different_engine_cannot_replay(tmp_path):
    report = fixed_report()
    path = save_evaluation_report(report, tmp_path)
    path.write_text("not json", encoding="utf-8")
    assert latest_compatible_report(report["spec"], tmp_path) is None
    changed = deepcopy(report)
    changed["spec"]["implementation"]["python"] = "different"
    changed["spec_sha256"] = content_hash(changed["spec"])
    changed["report_id"] = content_hash({k: v for k, v in changed.items() if k not in {"report_id", "generated_at"}})
    with pytest.raises(ValueError, match="implementation"):
        replay_evaluation_report(changed)


def test_read_only_cache_missing_data_does_not_create_directories(tmp_path):
    provider = protocol.ReadOnlyEvaluationProvider(tmp_path / "bars")
    snapshot = protocol.capture_evaluation_snapshot(["MISSING"], provider, "2y")
    assert snapshot.failures == {"MISSING": "unavailable_or_invalid_dated_history"}
    assert not (tmp_path / "bars").exists()
    with pytest.raises(OSError):
        protocol.cached_evaluation_symbols("S&P 500", "", tmp_path / "membership")
    assert not (tmp_path / "membership").exists()


def test_cache_reader_preserves_invalid_heldout_rows_and_does_not_rewrite(tmp_path):
    bars = evaluation_bars().astype(object)
    bars.iloc[400, bars.columns.get_loc("close")] = "invalid"
    path = tmp_path / "TEST_2y.csv"
    bars.to_csv(path)
    original = path.read_bytes()
    snapshot = protocol.capture_evaluation_snapshot(["TEST"], protocol.ReadOnlyEvaluationProvider(tmp_path), "2y")
    assert len(snapshot.bars_by_symbol["TEST"]) == 480
    assert protocol.holdout_start(snapshot, protocol.EvaluationProtocol()) == bars.index[360]
    assert snapshot.bars_by_symbol["TEST"].attrs["provenance"]["actual_source"] == "unknown"
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_interrupted_explicit_save_leaves_no_partial_report(tmp_path, monkeypatch):
    report = fixed_report()
    def interrupted(*args):
        raise OSError("Simulated failed rename")
    monkeypatch.setattr(evaluation_report.os, "replace", interrupted)
    with pytest.raises(OSError):
        save_evaluation_report(report, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("invalid", ["[]", "null", '{"schema_version":1}'])
def test_malformed_saved_reports_do_not_break_initial_lookup(tmp_path, invalid):
    (tmp_path / "bad.json").write_text(invalid, encoding="utf-8")
    assert latest_compatible_report(fixed_spec(["TEST"]), tmp_path) is None


def test_oversized_report_rejected_before_creating_saved_directory(tmp_path, monkeypatch):
    report = fixed_report()
    monkeypatch.setattr(evaluation_report, "MAX_SAVED_REPORT_BYTES", 1)
    with pytest.raises(ValueError, match="limit"):
        save_evaluation_report(report, tmp_path / "reports")
    assert not (tmp_path / "reports").exists()


def test_compatible_report_is_found_beyond_fifty_newer_files_without_evaluation(tmp_path, monkeypatch):
    report = fixed_report()
    saved = save_evaluation_report(report, tmp_path)
    os.utime(saved, (1, 1))
    for index in range(55):
        (tmp_path / f"newer-{index}.json").write_text('{"spec_sha256":"incompatible"}', encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("Reopening a saved report must not run evaluation")

    monkeypatch.setattr(evaluation_report, "evaluate_phase", forbidden)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert latest_compatible_report(report["spec"], tmp_path) == report
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_unreadable_report_metadata_does_not_hide_other_saved_reports(tmp_path, monkeypatch):
    report = fixed_report()
    save_evaluation_report(report, tmp_path)
    unavailable = tmp_path / "unavailable.json"
    unavailable.write_text("{}", encoding="utf-8")
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path == unavailable:
            raise OSError("Report disappeared during directory lookup")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    assert latest_compatible_report(report["spec"], tmp_path) == report
