from datetime import datetime, timezone

import pandas as pd
import pytest

from qx.data.provenance import tag_bars
from qx.market.mag11_snapshot import (
    build_mag11_trend_snapshot,
    load_mag11_trend_snapshot,
    save_mag11_trend_snapshot,
)
from qx.models.market import BarDataRequest


class StaticProvider:
    provider_name = "fixture"

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        if request.symbol == "MISS":
            raise RuntimeError("unavailable")
        index = pd.bdate_range("2026-09-01", periods=6, tz="UTC")
        bars = pd.DataFrame(
            {"open": [10, 11, 12, 13, 14, 15], "high": [11, 12, 13, 14, 15, 16],
             "low": [9, 10, 11, 12, 13, 14], "close": [10, 11, 12, 13, 14, 15],
             "volume": [100] * 6}, index=index,
        )
        return tag_bars(bars, self)


def test_mag11_trend_snapshot_preserves_row_provenance_and_round_trips(tmp_path) -> None:
    basket = tuple(f"S{index}" for index in range(10)) + ("MISS",)
    snapshot = build_mag11_trend_snapshot(
        StaticProvider(), basket=basket, period="6mo", requested_source="schwab",
        now=datetime(2026, 9, 12, 15, tzinfo=timezone.utc),
    )
    assert snapshot.rows[0].state == "available"
    assert snapshot.rows[0].actual_source == "fixture"
    assert snapshot.rows[0].return_1d == pytest.approx(15 / 14 - 1, abs=1e-6)
    assert snapshot.rows[0].return_5d == pytest.approx(0.5)
    assert snapshot.rows[-1].state == "unavailable"
    path = tmp_path / "mag11.json"
    save_mag11_trend_snapshot(snapshot, path)
    assert load_mag11_trend_snapshot(path) == snapshot


def test_mag11_trend_snapshot_requires_exact_distinct_basket() -> None:
    with pytest.raises(ValueError, match="exactly 11"):
        build_mag11_trend_snapshot(StaticProvider(), basket=("AAPL",), period="6mo", requested_source="schwab")
    with pytest.raises(ValueError, match="distinct"):
        build_mag11_trend_snapshot(StaticProvider(), basket=("AAPL",) * 11, period="6mo", requested_source="schwab")
