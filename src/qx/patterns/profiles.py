from qx.models.scan import RectangleScanParameters

STRICT_INSTITUTIONAL = "Strict institutional"
CLASSIC_RECTANGLE = "Classic rectangle"
PROFILE_OPTIONS = [STRICT_INSTITUTIONAL, CLASSIC_RECTANGLE]


def default_max_range_pct(profile: str) -> float:
    if profile == CLASSIC_RECTANGLE:
        return 0.25
    return 0.10


def build_rectangle_parameters(
    profile: str,
    *,
    lookback: int = 40,
    max_range_pct: float | None = None,
) -> RectangleScanParameters:
    effective_max_range_pct = (
        default_max_range_pct(profile) if max_range_pct is None else max_range_pct
    )
    if profile == CLASSIC_RECTANGLE:
        return RectangleScanParameters(
            lookback=lookback,
            min_range_pct=0.05,
            max_range_pct=effective_max_range_pct,
            touch_tolerance_pct=0.03,
            use_pivot_boundaries=True,
            require_pivot_touches=True,
            pivot_order=3,
            require_flat_boundaries=True,
            max_boundary_slope_pct=0.03,
            min_inside_close_pct=0.80,
            max_resistance_distance_pct=0.05,
            require_volume_staircase=False,
            require_bullish_absorption=False,
            require_atr_compression=False,
            require_clean_recent_candles=False,
            require_prior_trend=False,
            require_base_above_50_sma=False,
        )
    return RectangleScanParameters(lookback=lookback, max_range_pct=effective_max_range_pct)
