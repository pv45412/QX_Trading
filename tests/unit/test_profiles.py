from qx.patterns.profiles import (
    CLASSIC_RECTANGLE,
    STRICT_INSTITUTIONAL,
    build_rectangle_parameters,
    default_max_range_pct,
)


def test_profile_defaults_are_centralized() -> None:
    assert default_max_range_pct(STRICT_INSTITUTIONAL) == 0.10
    assert default_max_range_pct(CLASSIC_RECTANGLE) == 0.25


def test_strict_profile_keeps_institutional_filters_enabled() -> None:
    params = build_rectangle_parameters(STRICT_INSTITUTIONAL, lookback=35)

    assert params.lookback == 35
    assert params.require_volume_staircase
    assert params.require_bullish_absorption
    assert params.require_atr_compression
    assert not params.use_pivot_boundaries


def test_classic_profile_uses_pivot_rectangle_rules() -> None:
    params = build_rectangle_parameters(CLASSIC_RECTANGLE, lookback=60)

    assert params.lookback == 60
    assert params.use_pivot_boundaries
    assert params.require_pivot_touches
    assert params.touch_tolerance_pct == 0.03
    assert params.pivot_order == 3
    assert params.require_flat_boundaries
    assert params.max_boundary_slope_pct == 0.03
    assert params.min_inside_close_pct == 0.80
    assert params.min_range_pct == 0.05
    assert params.max_range_pct == 0.25
