from __future__ import annotations

import pandas as pd

from qx.ui.tradingview import build_lightweight_chart_html


def test_lightweight_chart_html_contains_candles_and_levels() -> None:
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1_000_000, 1_200_000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    html = build_lightweight_chart_html(
        bars,
        title="SPY liquidity map",
        levels=[{"price": 103.0, "label": "Call Wall", "side": "resistance", "source": "option_wall"}],
    )

    assert "LightweightCharts" in html
    assert "addCandlestickSeries" in html
    assert '"time": "2026-01-02"' in html
    assert "Call Wall 103.00" in html


def test_lightweight_chart_html_can_resample_weekly() -> None:
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1_000_000, 1_200_000, 1_400_000],
        },
        index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
    )

    html = build_lightweight_chart_html(bars, title="SPY weekly", interval="Weekly")

    assert '"time": "2026-01-09"' in html
    assert '"open": 100.0' in html
    assert '"high": 104.0' in html
    assert '"low": 99.0' in html
    assert '"close": 103.0' in html
    assert '"value": 3600000.0' in html
