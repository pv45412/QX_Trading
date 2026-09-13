from pathlib import Path
import pytest

from qx.models.scan import RectangleScanParameters
from qx.patterns.rectangle import analyze_rectangle
from qx.storage.feature_cache import SQLiteFeatureCache, build_feature_cache_key
from tests.unit.test_rectangle import _clean_rectangle_bars


def test_feature_cache_round_trips_candidate(tmp_path: Path) -> None:
    bars = _clean_rectangle_bars()
    parameters = RectangleScanParameters()
    key = build_feature_cache_key("test", bars, parameters, period="2y")
    candidate = analyze_rectangle("TEST", bars, parameters)
    cache = SQLiteFeatureCache(tmp_path / "features.db")

    cache.set(key, candidate)
    loaded = cache.get(key)

    assert cache.count() == 1
    assert loaded is not None
    assert loaded.symbol == "TEST"
    assert loaded.setup_score == candidate.setup_score


def test_feature_cache_key_tracks_parameter_changes() -> None:
    bars = _clean_rectangle_bars()

    strict_key = build_feature_cache_key(
        "TEST",
        bars,
        RectangleScanParameters(max_range_pct=0.10),
        period="2y",
    )
    loose_key = build_feature_cache_key(
        "TEST",
        bars,
        RectangleScanParameters(max_range_pct=0.25),
        period="2y",
    )

    assert strict_key.parameter_hash != loose_key.parameter_hash


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("row", [0, -1])
def test_cache_key_changes_when_history_is_corrected(column, row):
    bars = _clean_rectangle_bars()
    params = RectangleScanParameters()
    original = build_feature_cache_key("TEST", bars, params, period="2y")
    corrected = bars.copy()
    corrected.iloc[row, corrected.columns.get_loc(column)] *= 2
    changed = build_feature_cache_key("TEST", corrected, params, period="2y")
    assert original.last_bar_date == changed.last_bar_date
    assert original != changed


def test_identical_history_reuses_key():
    bars = _clean_rectangle_bars()
    params = RectangleScanParameters()
    assert build_feature_cache_key("TEST", bars, params, period="2y") == build_feature_cache_key(
        "TEST", bars.copy(), params, period="2y")


def test_corrected_history_does_not_return_old_candidate(tmp_path):
    bars = _clean_rectangle_bars()
    params = RectangleScanParameters()
    cache = SQLiteFeatureCache(tmp_path / "features.db")
    cache.set(build_feature_cache_key("TEST", bars, params, period="2y"), analyze_rectangle("TEST", bars, params))
    bars.iloc[-1, bars.columns.get_loc("volume")] *= 2
    assert cache.get(build_feature_cache_key("TEST", bars, params, period="2y")) is None
