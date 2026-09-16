"""Phase 8: Time-of-Day Normalized RVOL.

Computes Relative Volume (RVOL) normalized against historical same-slot baselines.

Key invariant:
  Current time-slot volume is compared ONLY against historical same-slot volume.
  Opening volume is NEVER compared against lunchtime baseline, or vice versa.

RVOL does not create or modify Direction Score (Phase 5 invariant preserved).
"""

import math
from typing import Optional

from qx.tradeability.models import RVOLBaseline, RVOLResult


def compute_rvol(
    current_volume: float,
    baseline: RVOLBaseline,
    minimum_valid_sessions: int = 10,
) -> RVOLResult:
    """Compute time-normalized RVOL from a pre-computed same-slot baseline.

    Args:
        current_volume: Volume accumulated in the current time slot.
        baseline: Pre-computed historical same-slot baseline.
        minimum_valid_sessions: Minimum sessions required for reliable baseline.

    Returns:
        RVOLResult with mean/median ratios, percentile, and normalized=True if
        the baseline met the minimum session requirement. If baseline is below
        minimum, normalized=False and ratios are 0.0.
    """
    if baseline.baseline_sessions_used < minimum_valid_sessions:
        # Insufficient historical data — do not fabricate RVOL
        return RVOLResult(
            current_volume=current_volume,
            slot_mean_volume=baseline.slot_mean_volume,
            slot_median_volume=baseline.slot_median_volume,
            slot_std=baseline.slot_std,
            rvol_mean_ratio=0.0,
            rvol_median_ratio=0.0,
            volume_percentile=0.0,
            baseline_sessions_used=baseline.baseline_sessions_used,
            time_slot=baseline.time_slot,
            normalized=False,
        )

    # Compute mean ratio
    rvol_mean = (
        current_volume / baseline.slot_mean_volume
        if baseline.slot_mean_volume > 0
        else 0.0
    )

    # Compute median ratio
    rvol_median = (
        current_volume / baseline.slot_median_volume
        if baseline.slot_median_volume > 0
        else 0.0
    )

    # Compute volume percentile via normal CDF approximation
    # Uses error function (erf) — same time slot baseline so comparison is valid
    if baseline.slot_std > 0:
        z = (current_volume - baseline.slot_mean_volume) / baseline.slot_std
        # Standard normal CDF approximation: Phi(z) = 0.5 * (1 + erf(z / sqrt(2)))
        percentile = 50.0 + 50.0 * math.erf(z / math.sqrt(2))
        percentile = max(0.0, min(100.0, percentile))
    else:
        # Zero std: all historical slots had same volume; compare directly
        if current_volume > baseline.slot_mean_volume:
            percentile = 100.0
        elif current_volume < baseline.slot_mean_volume:
            percentile = 0.0
        else:
            percentile = 50.0

    return RVOLResult(
        current_volume=current_volume,
        slot_mean_volume=baseline.slot_mean_volume,
        slot_median_volume=baseline.slot_median_volume,
        slot_std=baseline.slot_std,
        rvol_mean_ratio=rvol_mean,
        rvol_median_ratio=rvol_median,
        volume_percentile=percentile,
        baseline_sessions_used=baseline.baseline_sessions_used,
        time_slot=baseline.time_slot,
        normalized=True,
    )


def compute_rvol_optional(
    current_volume: float,
    baseline: Optional[RVOLBaseline],
    minimum_valid_sessions: int = 10,
) -> Optional[RVOLResult]:
    """Compute RVOL if a valid baseline is available; return None otherwise."""
    if baseline is None:
        return None
    return compute_rvol(current_volume, baseline, minimum_valid_sessions)
