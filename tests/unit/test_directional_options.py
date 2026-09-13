import pandas as pd

from qx.options.directional import analyze_directional_setup


def test_directional_setup_scores_bullish_breakout() -> None:
    bars = _directional_bars(direction="up")

    setup = analyze_directional_setup("BULL", bars)

    assert setup.bias == "Bullish"
    assert setup.call_score > setup.put_score
    assert setup.normalized_score > 0.50
    assert setup.relative_volume >= 1.2
    assert setup.iv_available is False


def test_directional_setup_scores_bearish_breakdown() -> None:
    bars = _directional_bars(direction="down")

    setup = analyze_directional_setup("BEAR", bars)

    assert setup.bias == "Bearish"
    assert setup.put_score > setup.call_score
    assert setup.normalized_score > 0.50


def _directional_bars(direction: str, rows: int = 260) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=rows)
    values: list[float] = []
    for index_num in range(rows):
        if direction == "up":
            base = 50 + index_num * 0.20
            values.append(base + (8 if index_num == rows - 1 else 0))
        else:
            base = 120 - index_num * 0.18
            values.append(base - (8 if index_num == rows - 1 else 0))

    close = pd.Series(values, index=index)
    volume_values = [1_000_000 + index_num * 500 for index_num in range(rows)]
    volume_values[-1] = 2_000_000
    volume = pd.Series(volume_values, index=index)
    return pd.DataFrame(
        {
            "open": close - 0.5 if direction == "up" else close + 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": volume,
        },
        index=index,
    )
