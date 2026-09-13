"""Deterministic chronological folds for daily-bar strategy evaluation.

This module deliberately knows nothing about prices, indicators, or exchange
calendars.  Callers must provide the already-audited daily session labels and
the snapshot's recorded as-of date.  That keeps the split reproducible and
prevents a later clock or a provider response from moving evaluation windows.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for expanding-window chronological evaluation.

    ``step_sessions`` must be at least the holdout length.  This ensures that
    separate folds never evaluate the same holdout session twice.
    """

    initial_train_sessions: int
    holdout_sessions: int
    step_sessions: int
    embargo_sessions: int = 0

    def __post_init__(self) -> None:
        values = {
            "initial_train_sessions": self.initial_train_sessions,
            "holdout_sessions": self.holdout_sessions,
            "step_sessions": self.step_sessions,
            "embargo_sessions": self.embargo_sessions,
        }
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.initial_train_sessions < 1:
            raise ValueError("initial_train_sessions must be at least one")
        if self.holdout_sessions < 1:
            raise ValueError("holdout_sessions must be at least one")
        if self.step_sessions < 1:
            raise ValueError("step_sessions must be at least one")
        if self.step_sessions < self.holdout_sessions:
            raise ValueError("step_sessions must not create overlapping holdout windows")


@dataclass(frozen=True)
class WalkForwardFold:
    """One leak-free expanding train / embargo / holdout partition."""

    fold_number: int
    train_indices: tuple[int, ...]
    embargo_indices: tuple[int, ...]
    holdout_indices: tuple[int, ...]
    train_dates: tuple[date, ...]
    embargo_dates: tuple[date, ...]
    holdout_dates: tuple[date, ...]


def _normalize_label(label: object) -> date:
    if isinstance(label, datetime):
        raise ValueError("Daily session labels must not include a time component")
    if isinstance(label, date):
        return label
    if isinstance(label, str):
        try:
            parsed = date.fromisoformat(label)
        except ValueError as exc:
            raise ValueError(f"Invalid daily session label: {label!r}") from exc
        if parsed.isoformat() != label:
            raise ValueError(f"Daily session labels must use YYYY-MM-DD: {label!r}")
        return parsed
    raise ValueError("Daily session labels must be date values or YYYY-MM-DD strings")


def _normalize_as_of(as_of_date: date | str) -> date:
    return _normalize_label(as_of_date)


def build_walk_forward_folds(
    session_labels: Iterable[object],
    config: WalkForwardConfig,
    *,
    as_of_date: date | str,
) -> tuple[WalkForwardFold, ...]:
    """Build complete chronological folds from daily session labels.

    A fold's training and holdout regions are separated by the configured
    embargo.  Future, duplicate, and out-of-order labels are rejected before
    any fold is returned.  Later training windows may contain *earlier*
    holdouts, which is the intended expanding-window walk-forward convention;
    no fold can train on its own holdout or embargo sessions.
    """

    labels = tuple(_normalize_label(label) for label in session_labels)
    reference_date = _normalize_as_of(as_of_date)
    if not labels:
        raise ValueError("At least one daily session label is required")
    if any(label > reference_date for label in labels):
        raise ValueError("Future daily session labels are not permitted")
    if len(set(labels)) != len(labels):
        raise ValueError("Duplicate daily session labels are not permitted")
    if any(left >= right for left, right in zip(labels, labels[1:])):
        raise ValueError("Daily session labels must be strictly chronological")

    folds: list[WalkForwardFold] = []
    train_end = config.initial_train_sessions
    required = config.embargo_sessions + config.holdout_sessions
    while train_end + required <= len(labels):
        embargo_start = train_end
        holdout_start = embargo_start + config.embargo_sessions
        holdout_end = holdout_start + config.holdout_sessions
        train_indices = tuple(range(train_end))
        embargo_indices = tuple(range(embargo_start, holdout_start))
        holdout_indices = tuple(range(holdout_start, holdout_end))
        folds.append(WalkForwardFold(
            fold_number=len(folds) + 1,
            train_indices=train_indices,
            embargo_indices=embargo_indices,
            holdout_indices=holdout_indices,
            train_dates=tuple(labels[index] for index in train_indices),
            embargo_dates=tuple(labels[index] for index in embargo_indices),
            holdout_dates=tuple(labels[index] for index in holdout_indices),
        ))
        train_end += config.step_sessions
    return tuple(folds)
