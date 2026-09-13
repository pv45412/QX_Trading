"""Read-only walk-forward auditing for Rectangle V2 candidates.

The audit deliberately records structure only.  It does not assign a trade
direction, score a setup, calculate an outcome, or inspect data after the
completed bar available at each cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from qx.patterns.rectangle_v2 import (
    RectangleV2Candidate,
    RectangleV2Config,
    detect_rectangle_candidates,
)


@dataclass(frozen=True)
class RectangleV2AuditObservation:
    """A candidate first observable using bars through ``cutoff_date`` only."""

    cutoff_date: pd.Timestamp
    candidate_start_date: pd.Timestamp
    candidate_end_date: pd.Timestamp
    window_size: int
    support_start: float
    support_end: float
    resistance_start: float
    resistance_end: float
    support_pivot_count: int
    resistance_pivot_count: int
    containment_ratio: float
    height_pct: float
    parallelism_pct: float


@dataclass(frozen=True)
class RectangleV2AuditSummary:
    """Counts for a chronological, no-lookahead candidate audit."""

    completed_cutoff_count: int
    candidate_observation_count: int


@dataclass(frozen=True)
class RectangleV2AuditResult:
    """Chronological observations and their compact audit summary."""

    observations: tuple[RectangleV2AuditObservation, ...]
    summary: RectangleV2AuditSummary


def audit_rectangle_candidates(
    bars: pd.DataFrame,
    config: RectangleV2Config | None = None,
) -> RectangleV2AuditResult:
    """Audit candidates as successive completed-bar prefixes become available.

    A candidate is recorded only at the cutoff matching its ``end_index``.
    Consequently, each observation is based solely on data available by its
    reported cutoff and later rows cannot change the historical audit record.
    """
    _validate_chronological_index(bars)
    settings = config or RectangleV2Config()
    first_cutoff = min(settings.window_sizes) - 1
    chronological_index = pd.DatetimeIndex(bars.index)
    observations: list[RectangleV2AuditObservation] = []

    for cutoff_index in range(first_cutoff, len(bars)):
        prefix = bars.iloc[: cutoff_index + 1]
        candidates = detect_rectangle_candidates(prefix, settings)
        observations.extend(
            _observation_from_candidate(chronological_index, chronological_index[cutoff_index], candidate)
            for candidate in candidates
            if candidate.end_index == cutoff_index
        )

    chronological = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.cutoff_date,
                item.candidate_end_date,
                item.candidate_start_date,
                item.window_size,
            ),
        )
    )
    return RectangleV2AuditResult(
        observations=chronological,
        summary=RectangleV2AuditSummary(
            completed_cutoff_count=max(0, len(bars) - first_cutoff),
            candidate_observation_count=len(chronological),
        ),
    )


def _observation_from_candidate(
    index: pd.DatetimeIndex,
    cutoff_date: pd.Timestamp,
    candidate: RectangleV2Candidate,
) -> RectangleV2AuditObservation:
    return RectangleV2AuditObservation(
        cutoff_date=cutoff_date,
        candidate_start_date=index[candidate.start_index],
        candidate_end_date=index[candidate.end_index],
        window_size=candidate.window_size,
        support_start=candidate.support_start,
        support_end=candidate.support_end,
        resistance_start=candidate.resistance_start,
        resistance_end=candidate.resistance_end,
        support_pivot_count=len(candidate.support_pivots),
        resistance_pivot_count=len(candidate.resistance_pivots),
        containment_ratio=candidate.containment_ratio,
        height_pct=candidate.height_pct,
        parallelism_pct=candidate.parallelism_pct,
    )


def _validate_chronological_index(bars: pd.DataFrame) -> None:
    """Reject indexes that cannot represent successive completed-bar cutoffs."""
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("bars index must be a DatetimeIndex for chronological audit")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("bars index must be unique and ascending for chronological audit")
