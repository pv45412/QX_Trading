"""Confirmed-pivot rectangle candidate detection.

This module deliberately does not issue trade signals.  It finds geometric
rectangle candidates that were knowable using completed daily bars only.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Literal

import math
import pandas as pd


_REQUIRED_COLUMNS = frozenset({"high", "low", "close"})


@dataclass(frozen=True)
class RectangleV2Config:
    """Bounded, deterministic controls for confirmed-pivot discovery."""

    pivot_order: int = 2
    window_sizes: tuple[int, ...] = (20, 30, 40, 60)
    min_pivots_per_side: int = 2
    cluster_tolerance_pct: float = 0.02
    containment_tolerance_pct: float = 0.02
    min_containment_ratio: float = 0.80
    min_height_pct: float = 0.01
    max_height_pct: float = 0.25
    max_parallelism_pct: float = 0.10
    dedup_overlap_ratio: float = 0.80

    def __post_init__(self) -> None:
        if self.pivot_order < 1:
            raise ValueError("pivot_order must be at least 1")
        if not self.window_sizes or any(size < (self.pivot_order * 2 + 3) for size in self.window_sizes):
            raise ValueError("window_sizes must accommodate confirmed pivots")
        if tuple(sorted(set(self.window_sizes))) != self.window_sizes:
            raise ValueError("window_sizes must be unique and ascending")
        if self.min_pivots_per_side < 2:
            raise ValueError("min_pivots_per_side must be at least 2")
        for name in (
            "cluster_tolerance_pct",
            "containment_tolerance_pct",
            "min_containment_ratio",
            "min_height_pct",
            "max_height_pct",
            "max_parallelism_pct",
            "dedup_overlap_ratio",
        ):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.min_height_pct > self.max_height_pct:
            raise ValueError("min_height_pct cannot exceed max_height_pct")


@dataclass(frozen=True)
class ConfirmedPivot:
    """A local extreme that became knowable at ``confirmed_index``."""

    kind: Literal["high", "low"]
    index: int
    confirmed_index: int
    price: float


@dataclass(frozen=True)
class RectangleV2Candidate:
    """A descriptive chart candidate, not a forecast, recommendation, or signal."""

    start_index: int
    end_index: int
    window_size: int
    support_start: float
    support_end: float
    resistance_start: float
    resistance_end: float
    support_pivots: tuple[ConfirmedPivot, ...]
    resistance_pivots: tuple[ConfirmedPivot, ...]
    containment_ratio: float
    height_pct: float
    parallelism_pct: float

    @property
    def status(self) -> str:
        return "confirmed_rectangle_candidate"


@dataclass(frozen=True)
class _Line:
    intercept: float
    slope: float

    def at(self, index: int) -> float:
        return self.intercept + self.slope * index


def confirmed_pivots(bars: pd.DataFrame, pivot_order: int = 2) -> tuple[ConfirmedPivot, ...]:
    """Return pivots only after their right-hand confirmation bars exist.

    A pivot at index ``i`` is emitted with ``confirmed_index=i + pivot_order``.
    No value after that confirmation bar is used to classify the pivot.
    """
    _validate_bars(bars)
    if pivot_order < 1:
        raise ValueError("pivot_order must be at least 1")

    highs = bars["high"].astype(float).tolist()
    lows = bars["low"].astype(float).tolist()
    pivots: list[ConfirmedPivot] = []
    for index in range(pivot_order, len(bars) - pivot_order):
        left_highs = highs[index - pivot_order:index]
        right_highs = highs[index + 1:index + pivot_order + 1]
        left_lows = lows[index - pivot_order:index]
        right_lows = lows[index + 1:index + pivot_order + 1]
        if highs[index] > max(left_highs) and highs[index] >= max(right_highs):
            pivots.append(ConfirmedPivot("high", index, index + pivot_order, highs[index]))
        if lows[index] < min(left_lows) and lows[index] <= min(right_lows):
            pivots.append(ConfirmedPivot("low", index, index + pivot_order, lows[index]))
    return tuple(pivots)


def detect_rectangle_candidates(
    bars: pd.DataFrame,
    config: RectangleV2Config | None = None,
) -> tuple[RectangleV2Candidate, ...]:
    """Find de-duplicated, confirmed-pivot rectangle candidates in daily bars.

    Each returned candidate uses only rows at or before its ``end_index``.  The
    function does not inspect future bars to score, filter, or deduplicate a
    candidate, making each result reproducible at its reported end bar.
    """
    _validate_bars(bars)
    settings = config or RectangleV2Config()
    pivots = confirmed_pivots(bars, settings.pivot_order)
    discovered: list[RectangleV2Candidate] = []

    for end_index in range(min(settings.window_sizes) - 1, len(bars)):
        for window_size in settings.window_sizes:
            start_index = end_index - window_size + 1
            if start_index < 0:
                continue
            candidate = _candidate_for_window(
                bars,
                pivots,
                start_index,
                end_index,
                window_size,
                settings,
            )
            if candidate is not None:
                discovered.append(candidate)
    return _deduplicate(discovered, settings.dedup_overlap_ratio)


def _candidate_for_window(
    bars: pd.DataFrame,
    pivots: tuple[ConfirmedPivot, ...],
    start_index: int,
    end_index: int,
    window_size: int,
    config: RectangleV2Config,
) -> RectangleV2Candidate | None:
    eligible = tuple(
        pivot
        for pivot in pivots
        if start_index <= pivot.index <= end_index and pivot.confirmed_index <= end_index
    )
    support_pivots = _best_cluster(
        (pivot for pivot in eligible if pivot.kind == "low"), config.cluster_tolerance_pct
    )
    resistance_pivots = _best_cluster(
        (pivot for pivot in eligible if pivot.kind == "high"), config.cluster_tolerance_pct
    )
    if len(support_pivots) < config.min_pivots_per_side or len(resistance_pivots) < config.min_pivots_per_side:
        return None

    support = _fit_line(support_pivots)
    resistance = _fit_line(resistance_pivots)
    midpoint = (support.at(start_index) + resistance.at(start_index)) / 2
    height = resistance.at(start_index) - support.at(start_index)
    if midpoint <= 0 or height <= 0:
        return None
    height_pct = height / midpoint
    if not config.min_height_pct <= height_pct <= config.max_height_pct:
        return None

    span = max(end_index - start_index, 1)
    parallelism_pct = abs(resistance.slope - support.slope) * span / height
    if parallelism_pct > config.max_parallelism_pct:
        return None

    containment_ratio = _containment_ratio(
        bars, start_index, end_index, support, resistance, config.containment_tolerance_pct
    )
    if containment_ratio < config.min_containment_ratio:
        return None

    return RectangleV2Candidate(
        start_index=start_index,
        end_index=end_index,
        window_size=window_size,
        support_start=support.at(start_index),
        support_end=support.at(end_index),
        resistance_start=resistance.at(start_index),
        resistance_end=resistance.at(end_index),
        support_pivots=support_pivots,
        resistance_pivots=resistance_pivots,
        containment_ratio=containment_ratio,
        height_pct=height_pct,
        parallelism_pct=parallelism_pct,
    )


def _best_cluster(
    pivots: Iterable[ConfirmedPivot],
    tolerance_pct: float,
) -> tuple[ConfirmedPivot, ...]:
    values: tuple[ConfirmedPivot, ...] = tuple(pivots)
    if not values:
        return ()
    clusters: list[tuple[ConfirmedPivot, ...]] = []
    for anchor in values:
        tolerance = abs(anchor.price) * tolerance_pct
        cluster = tuple(pivot for pivot in values if abs(pivot.price - anchor.price) <= tolerance)
        clusters.append(cluster)
    return max(clusters, key=lambda cluster: (len(cluster), max(pivot.index for pivot in cluster)))


def _fit_line(pivots: tuple[ConfirmedPivot, ...]) -> _Line:
    count = len(pivots)
    mean_x = sum(pivot.index for pivot in pivots) / count
    mean_y = sum(pivot.price for pivot in pivots) / count
    denominator = sum((pivot.index - mean_x) ** 2 for pivot in pivots)
    slope = 0.0 if denominator == 0 else sum(
        (pivot.index - mean_x) * (pivot.price - mean_y) for pivot in pivots
    ) / denominator
    return _Line(intercept=mean_y - slope * mean_x, slope=slope)


def _containment_ratio(
    bars: pd.DataFrame,
    start_index: int,
    end_index: int,
    support: _Line,
    resistance: _Line,
    tolerance_pct: float,
) -> float:
    contained = 0
    total = end_index - start_index + 1
    for index in range(start_index, end_index + 1):
        support_value = support.at(index)
        resistance_value = resistance.at(index)
        midpoint = (support_value + resistance_value) / 2
        tolerance = midpoint * tolerance_pct
        high = float(bars["high"].iloc[index])
        low = float(bars["low"].iloc[index])
        if high <= resistance_value + tolerance and low >= support_value - tolerance:
            contained += 1
    return contained / total


def _deduplicate(
    candidates: list[RectangleV2Candidate], overlap_threshold: float,
) -> tuple[RectangleV2Candidate, ...]:
    selected: list[RectangleV2Candidate] = []
    ordered = sorted(
        candidates,
        key=lambda item: (item.containment_ratio, len(item.support_pivots) + len(item.resistance_pivots), item.end_index),
        reverse=True,
    )
    for candidate in ordered:
        if not any(_is_duplicate(candidate, existing, overlap_threshold) for existing in selected):
            selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: (item.end_index, item.start_index, item.window_size)))


def _is_duplicate(
    left: RectangleV2Candidate,
    right: RectangleV2Candidate,
    overlap_threshold: float,
) -> bool:
    intersection = max(0, min(left.end_index, right.end_index) - max(left.start_index, right.start_index) + 1)
    union = max(left.end_index, right.end_index) - min(left.start_index, right.start_index) + 1
    overlap = intersection / union
    left_midpoint = (left.support_end + left.resistance_end) / 2
    right_midpoint = (right.support_end + right.resistance_end) / 2
    boundary_distance = max(
        abs(left.support_end - right.support_end),
        abs(left.resistance_end - right.resistance_end),
    ) / max((left_midpoint + right_midpoint) / 2, 1e-9)
    return overlap >= overlap_threshold and boundary_distance <= 0.03


def _validate_bars(bars: pd.DataFrame) -> None:
    missing = _REQUIRED_COLUMNS.difference(bars.columns)
    if missing:
        raise ValueError(f"bars are missing required columns: {', '.join(sorted(missing))}")
    if bars.empty:
        raise ValueError("bars must not be empty")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("bars index must be unique and ascending")
    values = bars.loc[:, list(_REQUIRED_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or not all(
        math.isfinite(float(value)) and float(value) > 0
        for value in values.to_numpy().ravel()
    ):
        raise ValueError("bars contain missing price values")
    if (values["high"] < values["low"]).any():
        raise ValueError("bars contain inverted high/low values")
