from datetime import UTC, datetime, timedelta
from pathlib import Path

from qx.core.engine import ScannerEngine
from qx.options.ideas import generate_option_ideas
from qx.reports.command_center import build_command_center
from qx.storage.command_center import (
    CommandCenterSnapshotMetadata,
    SQLiteCommandCenterSnapshotRepository,
    snapshot_freshness_label,
    snapshot_is_stale,
)
from qx.storage.options import SQLiteOptionIdeaRepository
from qx.storage.sqlite import SQLiteScanRepository
from tests.unit.test_overnight_workflow import StaticProvider, _frames


def test_command_center_snapshot_round_trips_full_payload(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    provider = StaticProvider(_frames())
    scan_result = ScannerEngine(provider).scan_symbols(["TEST"], period="2y")
    scan_repository = SQLiteScanRepository(database)
    scan_repository.save_scan_run(scan_result)
    option_repository = SQLiteOptionIdeaRepository(database)
    option_repository.save_ideas(generate_option_ideas(scan_result.candidates))

    center = build_command_center(
        provider=provider,
        repository=scan_repository,
        period="2y",
        limit=5,
        watchlist_symbols=["SPY"],
        option_repository=option_repository,
    )
    repository = SQLiteCommandCenterSnapshotRepository(database)
    snapshot_id = repository.save(
        center,
        CommandCenterSnapshotMetadata(
            source="test",
            period="2y",
            data_source="static",
            universe="unit",
        ),
    )

    snapshot = repository.latest()

    assert snapshot is not None
    assert snapshot.id == snapshot_id
    assert snapshot.regime_label == center.workflow.regime.label
    assert snapshot.watchlist_count == len(center.watchlist)
    assert snapshot.payload["market_state"]["spx"]["trend_bias"] == center.spx.trend_bias
    assert snapshot.payload["sectors"]
    assert snapshot.payload["sector_focus"] == center.sector_focus
    assert snapshot.payload["watchlist"]
    assert snapshot.payload["options"]["saved_ideas"]
    assert snapshot.payload["action_plan"]


def test_snapshot_freshness_helpers_flag_old_snapshots(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    provider = StaticProvider(_frames())
    scan_result = ScannerEngine(provider).scan_symbols(["TEST"], period="2y")
    scan_repository = SQLiteScanRepository(database)
    scan_repository.save_scan_run(scan_result)
    center = build_command_center(
        provider=provider,
        repository=scan_repository,
        period="2y",
        limit=5,
        watchlist_symbols=["SPY"],
    )
    repository = SQLiteCommandCenterSnapshotRepository(database)
    repository.save(
        center,
        CommandCenterSnapshotMetadata(
            source="test",
            period="2y",
            data_source="static",
            universe="unit",
        ),
    )
    snapshot = repository.latest()
    assert snapshot is not None

    stale_snapshot = snapshot.__class__(
        **{
            **snapshot.__dict__,
            "created_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        }
    )

    assert snapshot_freshness_label(snapshot)
    assert snapshot_is_stale(stale_snapshot)


def test_command_center_snapshot_comparison_tracks_deltas(tmp_path: Path) -> None:
    database = tmp_path / "qx.db"
    provider = StaticProvider(_frames())
    scan_result = ScannerEngine(provider).scan_symbols(["TEST"], period="2y")
    scan_repository = SQLiteScanRepository(database)
    scan_repository.save_scan_run(scan_result)
    center = build_command_center(
        provider=provider,
        repository=scan_repository,
        period="2y",
        limit=5,
        watchlist_symbols=["SPY"],
    )
    repository = SQLiteCommandCenterSnapshotRepository(database)
    metadata = CommandCenterSnapshotMetadata(
        source="test",
        period="2y",
        data_source="static",
        universe="unit",
    )
    repository.save(center, metadata)
    repository.save(center, metadata)

    comparison = repository.compare_latest()

    assert comparison.current is not None
    assert comparison.previous is not None
    assert not comparison.regime_changed
    assert comparison.new_watchlist_symbols == []
