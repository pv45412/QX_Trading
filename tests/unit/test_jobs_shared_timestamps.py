from unittest.mock import MagicMock

import pytest

from qx.storage.pipeline import StoredPipelineRun
from qx.ui.pages.pipeline import _render_recent_pipeline_runs
from qx.ui.status import friendly_iso_time


@pytest.mark.parametrize(("value", "expected"), [
    ("2026-09-11T00:30:00+00:00", "Sep 10, 2026 08:30 PM EDT"),
    ("2026-01-11T12:30:00", "Jan 11, 2026 07:30 AM EST"),
    ("2026-09-11", "Sep 11, 2026"),
    ("", "n/a"),
])
def test_operational_status_uses_shared_eastern_timestamp_contract(value, expected):
    assert friendly_iso_time(value) == expected


def test_pipeline_summary_and_history_display_same_timestamp_without_writes():
    created = "2026-09-11T00:30:00+00:00"
    run = StoredPipelineRun(
        id=1, created_at=created, universe="sp500", period="2y", profile="Classic rectangle",
        data_source="test_fixture", scan_run_id=10, workflow_run_id=20, cached_symbols=3,
        cache_failures=0, scanned_symbols=3, candidates=2, scan_failures=0,
        regime_label="Risk On", risk_level="Low", auth_warning="", payload={},
    )
    repository, ui = MagicMock(), MagicMock()
    repository.list_runs.return_value = [run]
    columns = [MagicMock() for _ in range(7)]
    ui.columns.return_value = columns
    _render_recent_pipeline_runs(ui, repository)
    expected = "Sep 10, 2026 08:30 PM EDT"
    columns[0].metric.assert_called_once_with("Last Run", expected)
    assert ui.dataframe.call_args.args[0].loc[0, "Created"] == expected
    repository.save.assert_not_called()
    assert run.created_at == created
