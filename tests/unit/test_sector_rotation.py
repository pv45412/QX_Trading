import pandas as pd

from qx.market.sector_rotation import analyze_sector_rotation, sector_rotation_frame
from qx.models.market import BarDataRequest
from qx.storage.sector_rotation import SQLiteSectorRotationRepository
from qx.ui.pages.sector_rotation import (
    _probable_rotation_flows,
    _rotation_lens_summary,
    _sector_action_board,
    _sector_decision_board,
    sector_decision_columns,
)


class StaticProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.frames[request.symbol].copy()


def test_sector_rotation_ranks_relative_leaders() -> None:
    frames = {"SPY": _bars(100.0, 0.10)}
    sector_steps = {
        "XLC": 0.30,
        "XLY": 0.05,
        "XLP": -0.02,
        "XLE": 0.04,
        "XLF": 0.03,
        "XLV": 0.02,
        "XLI": 0.06,
        "XLK": 0.40,
        "XLB": 0.01,
        "XLRE": -0.03,
        "XLU": -0.01,
    }
    frames.update({symbol: _bars(100.0, step) for symbol, step in sector_steps.items()})
    provider = StaticProvider(frames)

    result = analyze_sector_rotation(provider)
    frame = sector_rotation_frame(result)

    assert result.rows[0].etf == "XLK"
    assert result.rows[0].relative_20d > 0
    assert result.rows[0].relative_5d > 0
    assert result.rows[0].relative_60d > 0
    assert result.rows[0].group == "Growth"
    assert result.rows[0].rotation_status in {"Leading", "Improving"}
    assert len(frame) == 11
    assert "leadership_score" in frame.columns
    assert "acceleration" in frame.columns
    assert "rotation_status" in frame.columns
    assert "extension_risk_score" in frame.columns
    assert "distance_from_sma20" in frame.columns
    assert "rsi_14" in frame.columns


def test_sector_rotation_flow_map_pairs_weak_sources_with_strong_destinations() -> None:
    frame = pd.DataFrame(
        [
            {
                "sector": "Technology",
                "etf": "XLK",
                "group": "Growth",
                "relative_5d": 0.04,
                "relative_20d": 0.08,
                "relative_60d": 0.12,
                "acceleration": 0.03,
                "leadership_score": 0.92,
                "rotation_status": "Leading",
            },
            {
                "sector": "Utilities",
                "etf": "XLU",
                "group": "Defensive",
                "relative_5d": -0.03,
                "relative_20d": -0.07,
                "relative_60d": -0.02,
                "acceleration": -0.04,
                "leadership_score": 0.18,
                "rotation_status": "Lagging",
            },
        ]
    )

    flows = _probable_rotation_flows(frame)
    actions = _sector_action_board(frame)

    assert flows.loc[0, "from_sector"] == "Utilities"
    assert flows.loc[0, "to_sector"] == "Technology"
    assert flows.loc[0, "confidence"] > 0
    assert actions.set_index("sector").loc["Technology", "sector_action"] == "Favor pullbacks"
    assert actions.set_index("sector").loc["Utilities", "sector_action"] == "Avoid for longs"


def test_sector_rotation_lens_summarizes_key_timeframes_and_crowding() -> None:
    frame = pd.DataFrame(
        [
            {
                "sector": "Technology",
                "etf": "XLK",
                "relative_5d": 0.03,
                "relative_20d": 0.08,
                "relative_60d": 0.10,
                "acceleration": 0.02,
                "leadership_score": 0.90,
                "extension_risk_score": 0.20,
                "distance_from_sma20": 0.03,
                "rotation_status": "Leading",
            },
            {
                "sector": "Energy",
                "etf": "XLE",
                "relative_5d": 0.05,
                "relative_20d": 0.01,
                "relative_60d": 0.02,
                "acceleration": 0.04,
                "leadership_score": 0.50,
                "extension_risk_score": 0.80,
                "distance_from_sma20": 0.11,
                "rotation_status": "Improving",
            },
        ]
    )

    lens = _rotation_lens_summary(frame)

    assert [row["lens"] for row in lens] == ["1W Flow", "1M Flow", "1Q Flow", "Institutional Focus", "Crowding Risk"]
    assert lens[0]["sector"] == "Energy"
    assert lens[1]["sector"] == "Technology"
    assert lens[4]["sector"] == "Energy"


def test_sector_rotation_decision_board_has_one_actionable_row_per_sector() -> None:
    frame = pd.DataFrame(
        [
            {
                "sector": "Technology",
                "etf": "XLK",
                "group": "Growth",
                "relative_5d": 0.03,
                "relative_20d": 0.08,
                "relative_60d": 0.10,
                "acceleration": 0.02,
                "leadership_score": 0.90,
                "extension_risk_score": 0.20,
                "distance_from_sma20": 0.03,
                "rsi_14": 58.0,
                "rotation_status": "Leading",
            },
            {
                "sector": "Utilities",
                "etf": "XLU",
                "group": "Defensive",
                "relative_5d": -0.01,
                "relative_20d": -0.02,
                "relative_60d": 0.01,
                "acceleration": 0.01,
                "leadership_score": 0.25,
                "extension_risk_score": 0.15,
                "distance_from_sma20": 0.01,
                "rsi_14": 45.0,
                "rotation_status": "Lagging",
            },
        ]
    )

    decision = _sector_decision_board(frame)

    assert list(decision.columns) == sector_decision_columns()
    assert decision["sector"].is_unique
    assert decision.loc[decision["sector"] == "Technology", "sector_action"].iloc[0] == "Favor pullbacks"
    assert decision.loc[decision["sector"] == "Utilities", "sector_action"].iloc[0] == "Avoid for longs"


def test_sector_rotation_repository_saves_and_compares_rank_changes(tmp_path) -> None:
    first_provider = StaticProvider(_sector_frames({"XLK": 0.40, "XLU": -0.10}))
    second_provider = StaticProvider(_sector_frames({"XLK": -0.10, "XLU": 0.40}))
    repository = SQLiteSectorRotationRepository(tmp_path / "qx.db")

    repository.save(
        analyze_sector_rotation(first_provider),
        source="test",
        period="1y",
        data_source="static",
    )
    repository.save(
        analyze_sector_rotation(second_provider),
        source="test",
        period="1y",
        data_source="static",
    )

    latest = repository.latest()
    changes = repository.compare_latest()

    assert latest is not None
    assert latest.payload["sectors"]
    assert any(change.sector == "Utilities" and change.rank_change is not None for change in changes)


def _sector_frames(overrides: dict[str, float]) -> dict[str, pd.DataFrame]:
    symbols = ["SPY", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLK", "XLB", "XLRE", "XLU"]
    return {symbol: _bars(100.0, overrides.get(symbol, 0.10)) for symbol in symbols}


def _bars(start: float, step: float, rows: int = 260) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=rows)
    close = pd.Series([start + index_num * step for index_num in range(rows)], index=index)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=index,
    )
