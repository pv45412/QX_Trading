from pathlib import Path

import pandas as pd

from qx.models.market import BarDataRequest
from qx.options.ideas import generate_option_ideas
from qx.patterns.rectangle import analyze_rectangle
from qx.storage.options import (
    SQLiteOptionIdeaRepository,
    option_idea_performance_frame,
    stored_option_ideas_frame,
)
from tests.unit.test_options_ideas import StaticChainProvider
from tests.unit.test_rectangle import _clean_rectangle_bars


class PriceProvider:
    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": [105.0],
                "high": [106.0],
                "low": [104.0],
                "close": [105.0],
                "volume": [1_000_000],
            },
            index=pd.bdate_range("2026-01-01", periods=1),
        )


def test_option_idea_repository_saves_and_updates_performance(tmp_path: Path) -> None:
    repository = SQLiteOptionIdeaRepository(tmp_path / "qx.db")
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    ideas = generate_option_ideas([candidate], chain_provider=StaticChainProvider())

    saved = repository.save_ideas(ideas)
    updated = repository.update_performance(PriceProvider())
    stored = repository.list_ideas()
    frame = stored_option_ideas_frame(stored)

    assert saved == 1
    assert updated == 1
    assert stored[0].symbol == "TEST"
    assert stored[0].latest_underlying_price == 105.0
    assert "latest_return_pct" in frame.columns


def test_option_idea_repository_lists_performance_history(tmp_path: Path) -> None:
    repository = SQLiteOptionIdeaRepository(tmp_path / "qx.db")
    candidate = analyze_rectangle("TEST", _clean_rectangle_bars())
    ideas = generate_option_ideas([candidate], chain_provider=StaticChainProvider())

    repository.save_ideas(ideas)
    repository.update_performance(PriceProvider())
    stored = repository.list_ideas()
    history = repository.list_performance(option_idea_id=stored[0].id)
    frame = option_idea_performance_frame(history)

    assert len(history) == 1
    assert history[0].option_idea_id == stored[0].id
    assert history[0].underlying_price == 105.0
    assert "return_pct" in frame.columns
