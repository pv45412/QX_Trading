from typing import Any

import pandas as pd

from qx.patterns.profiles import CLASSIC_RECTANGLE, STRICT_INSTITUTIONAL, build_rectangle_parameters
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame


def render_strategy_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    streamlit.subheader("Rule Profiles")
    streamlit.markdown(
        """
        The app is structured around reusable rule profiles. A page, CLI command, or future agent can load the same profile builder instead of duplicating thresholds.

        - Strict institutional: narrow base, volume contraction, absorption, ATR compression, and trend filters.
        - Classic rectangle: 30-60 bar sideways base, 5%-25% range depth, pivot support/resistance touches, flat zones, near-resistance status, and controlled down-volume.
        """
    )

    streamlit.dataframe(
        display_frame(
            pd.DataFrame(
                [
                    _profile_row(STRICT_INSTITUTIONAL),
                    _profile_row(CLASSIC_RECTANGLE),
                ]
            )
        ),
        width="stretch",
        hide_index=True,
    )


def _profile_row(profile: str) -> dict[str, object]:
    params = build_rectangle_parameters(profile)
    return {
        "profile": profile,
        "lookback": params.lookback,
        "min_range_pct": params.min_range_pct,
        "max_range_pct": params.max_range_pct,
        "touch_tolerance_pct": params.touch_tolerance_pct,
        "pivot_order": params.pivot_order,
        "pivot_boundaries": params.use_pivot_boundaries,
        "pivot_touches_required": params.require_pivot_touches,
        "flat_boundaries_required": params.require_flat_boundaries,
        "max_boundary_slope_pct": params.max_boundary_slope_pct,
        "min_inside_close_pct": params.min_inside_close_pct,
        "breakout_buffer_pct": params.breakout_buffer_pct,
        "failure_atr_buffer": params.failure_atr_buffer_multiple,
        "volume_staircase_required": params.require_volume_staircase,
        "atr_compression_required": params.require_atr_compression,
        "prior_trend_required": params.require_prior_trend,
    }


run_standalone_page(
    "Strategy Rules",
    "Review the active rule profiles and the rectangle scoring model.",
    render_strategy_page,
)
