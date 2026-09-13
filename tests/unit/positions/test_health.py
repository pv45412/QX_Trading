"""Unit tests for qx.positions.health module."""

import pytest
from qx.positions.health import calculate_position_health


def test_position_health_strong_hold():
    res = calculate_position_health(
        trend_score=90.0,
        structure_score=95.0,
        invalidation_distance_pct=6.0,
        reward_remaining_pct=85.0,
        momentum_score=90.0,
        volatility_score=85.0,
        dte=30,
    )
    assert res.composite_score >= 85.0
    assert res.action == "STRONG HOLD"
    assert not res.hard_override_active


def test_position_health_stop_override():
    res = calculate_position_health(
        trend_score=90.0,
        structure_score=95.0,
        invalidation_distance_pct=0.0,
        reward_remaining_pct=85.0,
        momentum_score=90.0,
        volatility_score=85.0,
        dte=30,
        stop_breached=True,
    )
    assert res.composite_score == 0.0
    assert res.action == "EXIT / REVIEW"
    assert res.hard_override_active
    assert "Stop loss" in res.override_reason
