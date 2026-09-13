from pathlib import Path

from qx.models.scan import ScanRunResult
from qx.patterns.rectangle import analyze_rectangle
from qx.storage.sqlite import SQLiteScanRepository
from tests.unit.test_rectangle import _clean_rectangle_bars


def test_sqlite_repository_saves_scan_run(tmp_path: Path) -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    repository = SQLiteScanRepository(tmp_path / "qx.db")

    run_id = repository.save_scan_run(
        ScanRunResult(candidates=[candidate], total_symbols=1, passed_symbols=1)
    )

    assert run_id == 1
    assert (tmp_path / "qx.db").exists()


def test_sqlite_repository_loads_and_compares_runs(tmp_path: Path) -> None:
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    baseline = candidate.model_copy(update={"setup_score": 0.70})
    improved = candidate.model_copy(update={"setup_score": 0.80})
    repository = SQLiteScanRepository(tmp_path / "qx.db")

    repository.save_scan_run(ScanRunResult(candidates=[baseline], total_symbols=1, passed_symbols=1))
    repository.save_scan_run(ScanRunResult(candidates=[improved], total_symbols=1, passed_symbols=1))

    runs = repository.list_scan_runs()
    latest = repository.latest_candidates()
    changes = repository.compare_latest_runs()

    assert len(runs) == 2
    assert latest[0].symbol == "TEST"
    assert changes[0].symbol == "TEST"
    assert changes[0].score_change is not None
    assert changes[0].score_change > 0
