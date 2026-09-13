import pandas as pd

from qx.models.scan import RectangleScanParameters
from qx.patterns.rectangle import analyze_rectangle


def test_rectangle_detector_passes_clean_rectangle() -> None:
    result = analyze_rectangle("TEST", _clean_rectangle_bars())

    assert result.passed
    assert result.score == 1
    assert result.metrics.relative_volume_20d > 0
    assert result.metrics.support_touches >= 2
    assert result.metrics.resistance_touches >= 2
    assert result.metrics.support_slope_pct >= 0
    assert result.metrics.resistance_slope_pct >= 0
    assert result.metrics.position_in_range >= 0.85
    assert result.metrics.bars_above_mid_pct >= 0.55
    assert result.metrics.accumulation_ratio > 0
    assert result.metrics.box_quality_score > 0
    assert result.metrics.accumulation_score > 0
    assert result.metrics.breakout_score > 0
    assert result.metrics.box_status in {"Tight Box", "Box Building"}


def test_rectangle_detector_rejects_wide_range() -> None:
    result = analyze_rectangle(
        "WIDE",
        _clean_rectangle_bars(range_multiplier=2.0),
        RectangleScanParameters(max_range_pct=0.10),
    )

    failed_rule_names = {rule.name for rule in result.rules if not rule.passed}
    assert not result.passed
    assert "tight_rectangle" in failed_rule_names
    assert result.setup_score <= 0.49


def test_rectangle_detector_caps_severely_wide_range() -> None:
    result = analyze_rectangle(
        "VERY_WIDE",
        _clean_rectangle_bars(range_multiplier=5.0),
        RectangleScanParameters(max_range_pct=0.10),
    )

    assert result.metrics.range_pct >= 0.20
    assert result.setup_score <= 0.30


def test_rectangle_detector_rejects_sloped_classic_boundaries() -> None:
    result = analyze_rectangle(
        "SLOPED",
        _sloped_rectangle_bars(),
        RectangleScanParameters(
            min_range_pct=0.05,
            max_range_pct=0.25,
            require_flat_boundaries=True,
            max_boundary_slope_pct=0.01,
            max_resistance_distance_pct=0.05,
            require_volume_staircase=False,
            require_bullish_absorption=False,
            require_atr_compression=False,
            require_clean_recent_candles=False,
            require_prior_trend=False,
            require_base_above_50_sma=False,
        ),
    )

    failed_rule_names = {rule.name for rule in result.rules if not rule.passed}
    assert "flat_boundaries" in failed_rule_names
    assert result.setup_score <= 0.69


def test_rectangle_detector_uses_pivot_boundaries_for_classic_pattern() -> None:
    result = analyze_rectangle(
        "PIVOT",
        _pivot_rectangle_bars(),
        RectangleScanParameters(
            min_range_pct=0.05,
            max_range_pct=0.25,
            use_pivot_boundaries=True,
            require_pivot_touches=True,
            require_flat_boundaries=True,
            max_boundary_slope_pct=0.05,
            max_resistance_distance_pct=0.05,
            require_volume_staircase=False,
            require_bullish_absorption=False,
            require_atr_compression=False,
            require_clean_recent_candles=False,
            require_prior_trend=False,
            require_base_above_50_sma=False,
        ),
    )

    failed_rule_names = {rule.name for rule in result.rules if not rule.passed}
    assert result.metrics.pivot_support_touches >= 2
    assert result.metrics.pivot_resistance_touches >= 2
    assert "pivot_support_touches" not in failed_rule_names
    assert "pivot_resistance_touches" not in failed_rule_names


def _clean_rectangle_bars(range_multiplier: float = 1.0) -> pd.DataFrame:
    rows: list[dict[str, float]] = []

    for index in range(160):
        close = 20 + index * 0.07
        rows.append(_bar(close - 0.08, close + 0.20, close - 0.20, close, 900_000))

    center = 33.20
    amplitude = 1.00 * range_multiplier
    wave = [
        center - amplitude,
        center - 0.20,
        center + amplitude,
        center + 0.25,
        center - amplitude,
        center - 0.15,
        center + amplitude,
        center + 0.20,
    ] * 4 + [
        center - amplitude,
        center - 0.20,
        center + amplitude,
        center + 0.20,
        center + 0.72,
        center + 0.78,
        center + 0.75,
        center + 0.82,
    ]
    for index, close in enumerate(wave):
        recent = index >= 35
        spread = 0.04 if recent else 0.28
        open_price = close - 0.18 if index % 3 != 0 else close + 0.18
        rows.append(_bar(open_price, close + spread, close - spread, close, 750_000 - index * 9_000))

    rows.append(
        _bar(
            center + amplitude - 0.18,
            center + amplitude - 0.02,
            center + amplitude - 0.28,
            center + amplitude - 0.05,
            310_000,
        )
    )
    return pd.DataFrame(rows)


def _sloped_rectangle_bars() -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for index in range(160):
        close = 30 + index * 0.05
        rows.append(_bar(close - 0.05, close + 0.15, close - 0.15, close, 900_000))

    for index in range(40):
        support = 36.00 + index * 0.07
        resistance = 40.00 + index * 0.07
        close = support + 3.80 if index % 2 == 0 else support + 0.20
        rows.append(_bar(close - 0.05, resistance, support, close, 700_000))

    rows.append(_bar(42.40, 42.60, 42.10, 42.45, 650_000))
    return pd.DataFrame(rows)


def _pivot_rectangle_bars() -> pd.DataFrame:
    rows: list[dict[str, float]] = []

    for index in range(160):
        close = 40 + index * 0.08
        rows.append(_bar(close - 0.08, close + 0.25, close - 0.25, close, 900_000))

    closes = [
        54.0,
        56.0,
        59.8,
        56.8,
        52.2,
        55.5,
        60.1,
        57.1,
        52.0,
        55.8,
        59.9,
        56.5,
        52.1,
        55.9,
        60.2,
        57.0,
        52.0,
        56.0,
        59.7,
        57.4,
        52.3,
        55.9,
        60.0,
        57.2,
        52.2,
        55.8,
        59.8,
        57.4,
        52.1,
        56.1,
        60.0,
        57.2,
        52.2,
        55.9,
        59.7,
        58.6,
        59.0,
        59.3,
        59.5,
        59.6,
    ]
    for index, close in enumerate(closes):
        spread = 0.20 if close < 59.5 else 0.10
        open_price = close - 0.25 if index % 3 != 0 else close + 0.18
        rows.append(_bar(open_price, close + spread, close - spread, close, 700_000 - index * 5_000))

    rows.append(_bar(59.5, 59.75, 59.25, 59.65, 480_000))
    return pd.DataFrame(rows)


def _bar(open_price: float, high: float, low: float, close: float, volume: float) -> dict[str, float]:
    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
