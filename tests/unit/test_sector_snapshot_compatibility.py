from dataclasses import replace

import pytest

from qx.storage.sector_rotation import SQLiteSectorRotationRepository, StoredSectorRotationSnapshot


def snapshot(identifier):
    return StoredSectorRotationSnapshot(
        id=identifier, created_at="2026-09-09T12:00:00+00:00", source="manual",
        period="2y", data_source="schwab", leaders="Technology",
        payload={"benchmark": "SPY", "sectors": [
            {"sector": "Technology", "rotation_status": "Leading", "leadership_score": 0.8},
        ]},
    )


@pytest.mark.parametrize("difference", ["period", "data_source", "benchmark", "missing_benchmark"])
def test_incompatible_snapshots_are_not_market_changes(tmp_path, monkeypatch, difference):
    current, previous = snapshot(2), snapshot(1)
    if difference == "period":
        previous = replace(previous, period="5y")
    elif difference == "data_source":
        previous = replace(previous, data_source="yfinance")
    elif difference == "benchmark":
        previous = replace(previous, payload={**previous.payload, "benchmark": "QQQ"})
    else:
        previous = replace(previous, payload={"sectors": previous.payload["sectors"]})
    repo = SQLiteSectorRotationRepository(tmp_path / "unused.db")
    monkeypatch.setattr(repo, "list_snapshots", lambda limit: [current, previous])
    assert repo.compare_latest() == []


def test_matching_snapshots_keep_comparison_across_run_origins(tmp_path, monkeypatch):
    current, previous = snapshot(2), replace(snapshot(1), source="pipeline")
    repo = SQLiteSectorRotationRepository(tmp_path / "unused.db")
    monkeypatch.setattr(repo, "list_snapshots", lambda limit: [current, previous])
    changes = repo.compare_latest()
    assert len(changes) == 1
    assert changes[0].rank_change == 0
    assert changes[0].previous_score == 0.8


@pytest.mark.parametrize("change", ["removed", "added", "duplicate", "unnamed"])
def test_coverage_changes_do_not_manufacture_rank_moves(tmp_path, monkeypatch, change):
    current, previous = snapshot(2), snapshot(1)
    extra = {"sector": "Utilities", "rotation_status": "Lagging", "leadership_score": 0.2}
    if change == "removed":
        previous.payload["sectors"].append(extra)
    elif change == "added":
        current.payload["sectors"].append(extra)
    elif change == "duplicate":
        current.payload["sectors"].append(dict(current.payload["sectors"][0]))
    else:
        current.payload["sectors"][0].pop("sector")
    repo = SQLiteSectorRotationRepository(tmp_path / "unused.db")
    monkeypatch.setattr(repo, "list_snapshots", lambda limit: [current, previous])
    assert repo.compare_latest() == []
