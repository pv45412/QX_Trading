from pathlib import Path

from qx.models.scan import ScanRunResult
from qx.patterns.rectangle import analyze_rectangle
from qx.reports.morning import build_morning_report, morning_report_frame, sector_summary_frame
from qx.storage.sqlite import SQLiteScanRepository
from tests.unit.test_rectangle import _clean_rectangle_bars


def test_morning_report_buckets_latest_scan(tmp_path: Path) -> None:
    repository = SQLiteScanRepository(tmp_path / "qx.db")
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    prior = candidate.model_copy(update={"setup_score": 0.60})
    current = candidate.model_copy(update={"setup_score": 0.75})

    repository.save_scan_run(ScanRunResult(candidates=[prior], total_symbols=1, passed_symbols=0))
    repository.save_scan_run(ScanRunResult(candidates=[current], total_symbols=1, passed_symbols=0))

    report = build_morning_report(repository, min_rank_score=0.0, limit=10)
    frame = morning_report_frame(report.top_candidates)

    assert report.run is not None
    assert report.previous_run is not None
    assert report.top_candidates[0].symbol == "TEST"
    assert report.improving_candidates[0].symbol == "TEST"
    assert "weekly_status" in frame.columns


def test_sector_summary_groups_report_rows(tmp_path: Path) -> None:
    repository = SQLiteScanRepository(tmp_path / "qx.db")
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    repository.save_scan_run(ScanRunResult(candidates=[candidate], total_symbols=1, passed_symbols=0))

    report = build_morning_report(repository, min_rank_score=0.0, limit=10)
    summary = sector_summary_frame(report.top_candidates)

    assert "sector" in summary.columns
    assert int(summary.iloc[0]["candidates"]) == 1
