from datetime import date, datetime, timezone
from typing import cast

import pytest

from qx.backtesting.walk_forward import (
    WalkForwardConfig,
    build_walk_forward_folds,
)


AS_OF = date(2026, 1, 30)


def labels(count: int) -> list[str]:
    return [f"2026-01-{day:02d}" for day in range(1, count + 1)]


def test_expanding_folds_are_chronological_and_do_not_leak() -> None:
    folds = build_walk_forward_folds(
        labels(12),
        WalkForwardConfig(
            initial_train_sessions=4,
            holdout_sessions=2,
            step_sessions=2,
            embargo_sessions=1,
        ),
        as_of_date=AS_OF,
    )

    assert [fold.fold_number for fold in folds] == [1, 2, 3]
    assert folds[0].train_indices == (0, 1, 2, 3)
    assert folds[0].embargo_indices == (4,)
    assert folds[0].holdout_indices == (5, 6)
    assert folds[1].train_indices == tuple(range(6))
    assert folds[2].holdout_dates == (date(2026, 1, 10), date(2026, 1, 11))
    assert all(
        set(fold.train_indices).isdisjoint(fold.embargo_indices)
        and set(fold.train_indices).isdisjoint(fold.holdout_indices)
        and set(fold.embargo_indices).isdisjoint(fold.holdout_indices)
        and max(fold.train_dates) < min(fold.holdout_dates)
        for fold in folds
    )
    assert set(folds[0].holdout_indices).isdisjoint(folds[1].holdout_indices)


def test_returns_no_partial_holdout_fold() -> None:
    folds = build_walk_forward_folds(
        labels(6),
        WalkForwardConfig(4, 2, 2),
        as_of_date=AS_OF,
    )
    assert len(folds) == 1
    assert build_walk_forward_folds(
        labels(5), WalkForwardConfig(4, 2, 2), as_of_date=AS_OF
    ) == ()


@pytest.mark.parametrize(
    ("session_labels", "message"),
    [
        (["2026-01-01", "2026-01-01"], "Duplicate"),
        (["2026-01-02", "2026-01-01"], "strictly chronological"),
        (["2026-01-01", "not-a-date"], "Invalid"),
        (["2026-01-01T00:00:00"], "Invalid"),
        (["2026-02-01"], "Future"),
        ([datetime(2026, 1, 1, tzinfo=timezone.utc)], "time component"),
    ],
)
def test_rejects_invalid_or_unsafe_session_labels(
    session_labels: list[object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_walk_forward_folds(
            session_labels,
            WalkForwardConfig(1, 1, 1),
            as_of_date="2026-01-30",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_train_sessions": 0, "holdout_sessions": 1, "step_sessions": 1},
        {"initial_train_sessions": 1, "holdout_sessions": 0, "step_sessions": 1},
        {"initial_train_sessions": 1, "holdout_sessions": 1, "step_sessions": 0},
        {"initial_train_sessions": 1, "holdout_sessions": 2, "step_sessions": 1},
        {"initial_train_sessions": True, "holdout_sessions": 1, "step_sessions": 1},
        {"initial_train_sessions": 1, "holdout_sessions": 1, "step_sessions": 1, "embargo_sessions": -1},
    ],
)
def test_rejects_invalid_fold_configuration(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WalkForwardConfig(**cast(dict[str, int], kwargs))


def test_as_of_date_is_validated_without_using_the_system_clock() -> None:
    with pytest.raises(ValueError, match="Invalid"):
        build_walk_forward_folds(labels(2), WalkForwardConfig(1, 1, 1), as_of_date="bad")
