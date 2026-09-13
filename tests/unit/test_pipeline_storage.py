from pathlib import Path

from qx.processing.overnight_workflow import run_overnight_workflow
from qx.storage.pipeline import PipelineRunMetadata, SQLitePipelineRepository, StoredPipelineRun, pipeline_runs_frame
from tests.unit.test_overnight_workflow import StaticProvider, _frames


def test_pipeline_repository_saves_operational_run(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    result = run_overnight_workflow(
        provider=StaticProvider(_frames()),
        universe="sp500",
        period="2y",
        profile="Classic rectangle",
        database=database,
    )
    metadata = PipelineRunMetadata(
        universe="sp500",
        period="2y",
        profile="Classic rectangle",
        data_source="yfinance",
        lookback=40,
        max_range_pct=0.25,
        refresh=False,
    )

    run_id = SQLitePipelineRepository(database).save(result, metadata)
    runs = SQLitePipelineRepository(database).list_runs()

    assert run_id == 1
    assert runs[0].universe == "sp500"
    assert runs[0].data_source == "yfinance"
    assert runs[0].scan_run_id == result.scan_run_id
    assert runs[0].workflow_run_id == result.workflow_run_id
    assert runs[0].payload["metadata"]["profile"] == "Classic rectangle"

    frame = pipeline_runs_frame(runs)
    assert list(frame.columns) == [
        "id",
        "created_at",
        "universe",
        "period",
        "profile",
        "data_source",
        "cached_symbols",
        "cache_failures",
        "scanned_symbols",
        "candidates",
        "scan_failures",
        "regime",
        "risk",
        "auth_warning",
        "health",
    ]
    assert frame.loc[0, "health"] in {"Ready", "Data Issues", "No Candidates", "Auth Warning"}


def test_pipeline_runs_frame_marks_clean_run_ready() -> None:
    run = StoredPipelineRun(
        id=1,
        created_at="2026-06-02T12:00:00+00:00",
        universe="sp500",
        period="2y",
        profile="Classic rectangle",
        data_source="yfinance",
        scan_run_id=10,
        workflow_run_id=20,
        cached_symbols=503,
        cache_failures=0,
        scanned_symbols=503,
        candidates=25,
        scan_failures=0,
        regime_label="Risk On",
        risk_level="Low",
        auth_warning="",
        payload={},
    )

    frame = pipeline_runs_frame([run])

    assert frame.loc[0, "health"] == "Ready"
    assert frame.loc[0, "auth_warning"] == "None"
