import pytest

from qx.patterns.rectangle import analyze_rectangle
from tests.unit.test_rectangle import _clean_rectangle_bars


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_invalid_prices_are_rejected(value: float) -> None:
    bars = _clean_rectangle_bars().copy()
    bars.iloc[-1, bars.columns.get_loc("close")] = value
    with pytest.raises(ValueError, match="History"):
        analyze_rectangle("TEST", bars)


def test_missing_columns_are_rejected() -> None:
    with pytest.raises(ValueError, match="requires"):
        analyze_rectangle("TEST", _clean_rectangle_bars().drop(columns="volume"))


def test_reversed_history_is_rejected() -> None:
    with pytest.raises(ValueError, match="ascending"):
        analyze_rectangle("TEST", _clean_rectangle_bars().iloc[::-1])


def test_duplicate_indices_are_rejected() -> None:
    bars = _clean_rectangle_bars().copy()
    bars.index = [0] * len(bars)
    with pytest.raises(ValueError, match="unique"):
        analyze_rectangle("TEST", bars)
