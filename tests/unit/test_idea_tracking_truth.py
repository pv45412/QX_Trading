from contextlib import closing
from pathlib import Path
import sqlite3

import pandas as pd

from qx.storage.options import (
    SQLiteOptionIdeaRepository, option_idea_performance_frame, stored_option_ideas_frame,
)
from qx.ui.pages import performance


class UnderlyingProvider:
    def get_daily_bars(self, request):
        return pd.DataFrame({"close": [105.0]})


def populated_repository(tmp_path: Path) -> SQLiteOptionIdeaRepository:
    repository = SQLiteOptionIdeaRepository(tmp_path / "ideas.db")
    repository.initialize()
    with closing(sqlite3.connect(repository.database_path)) as connection:
        connection.executemany(
            """INSERT INTO option_ideas
               (created_at, symbol, action, direction, strategy, idea_score, status,
                entry_underlying_price, payload_json)
               VALUES ('2026-01-01T12:00:00+00:00', 'TEST', 'Watch', 'Bullish', 'Call', 75, ?, 100, '{}')
            """,
            [("Watch" if index < 3 else "Untracked",) for index in range(61)],
        )
        connection.commit()
    return repository


def test_repeated_snapshots_count_distinct_ids_across_all_pages(tmp_path: Path) -> None:
    repository = populated_repository(tmp_path)
    assert repository.tracking_counts() == {
        "saved_ideas": 61, "performance_snapshots": 0, "tracked_ideas": 0,
    }
    repository.update_performance(UnderlyingProvider(), max_workers=1)
    repository.update_performance(UnderlyingProvider(), max_workers=1)
    with closing(sqlite3.connect(repository.database_path)) as connection:
        connection.executemany(
            """INSERT INTO option_idea_performance
               (option_idea_id, created_at, underlying_price, return_pct)
               VALUES (1, '2026-01-03T12:00:00+00:00', 105, 0.05)""",
            [()] * 130,
        )
        connection.commit()
    assert repository.tracking_counts() == {
        "saved_ideas": 61, "performance_snapshots": 136, "tracked_ideas": 3,
    }
    # Both legacy query limits would omit tracked IDs, but the full count stays correct.
    assert all(row.id > 3 for row in repository.list_ideas(limit=25))
    assert {row.option_idea_id for row in repository.list_performance(limit=100)} == {1}
    pages = [repository.list_ideas(limit=25, offset=offset) for offset in (0, 25, 50)]
    ids = [row.id for page in pages for row in page]
    assert ids == list(range(61, 0, -1))
    assert len(ids) == len(set(ids)) == 61
    assert performance._options_performance_summary(
        saved_count=61, history_count=136, tracked_count=3,
    )["tracked_ideas"] == 3


def test_orphan_snapshots_do_not_count_as_saved_tracked_ids(tmp_path: Path) -> None:
    repository = populated_repository(tmp_path)
    with closing(sqlite3.connect(repository.database_path)) as connection:
        connection.execute(
            """INSERT INTO option_idea_performance
               (option_idea_id, created_at, underlying_price, return_pct)
               VALUES (999, '2026-01-03', 105, 0.05)""",
        )
        connection.commit()
    assert repository.tracking_counts()["tracked_ideas"] == 0


def test_idea_labels_are_underlying_returns_and_preserve_stable_ids(tmp_path: Path) -> None:
    repository = populated_repository(tmp_path)
    repository.update_performance(UnderlyingProvider(), max_workers=1)
    frame = performance._idea_tracking_frame(stored_option_ideas_frame(
        repository.list_ideas(status="Watch"),
    ).drop(columns="payload"))
    assert frame["Record ID"].tolist() == ["3", "2", "1"]
    assert frame["Underlying Return"].tolist() == ["5.0%"] * 3
    assert "Underlying Price at Save" in frame.columns
    assert "Latest Underlying Price" in frame.columns
    assert "Latest Return" not in frame.columns
    history = performance._idea_tracking_frame(option_idea_performance_frame(
        repository.list_performance(limit=2, offset=1),
    ))
    assert "Idea ID" in history.columns
    assert "Underlying Return" in history.columns
    assert "Return" not in history.columns


class TrackingUI:
    def __init__(self, page=1):
        self.page = page
        self.metrics = {}
        self.frames = []
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def subheader(self, message):
        self.messages.append(message)

    caption = warning = info = error = subheader

    def columns(self, count):
        return [self] * count

    def metric(self, label, value):
        self.metrics[label] = value

    def number_input(self, *args, **kwargs):
        return self.page

    def dataframe(self, frame, **kwargs):
        self.frames.append(frame)

    def expander(self, *args):
        return self


def test_page_counts_do_not_change_when_idea_page_changes(tmp_path: Path, monkeypatch) -> None:
    repository = populated_repository(tmp_path)
    repository.update_performance(UnderlyingProvider(), max_workers=1)
    monkeypatch.setattr(performance, "SCAN_HISTORY_DB", repository.database_path)
    first, last = TrackingUI(page=1), TrackingUI(page=3)
    performance._render_options_performance(first)
    performance._render_options_performance(last)
    assert first.metrics == last.metrics == {
        "Saved Ideas": 61, "Underlying Snapshots": 3, "Tracked Ideas": 3,
    }
    assert len(first.frames[0]) == 25
    assert len(last.frames[0]) == 11
    assert "Idea Tracking" in first.messages
    assert any("not actual option P&L" in message for message in first.messages)
