"""Comprehensive test suite for Phase 3: Signal Quality & Validation.

Tests:
1. SignalValidator multi-factor technical scoring.
2. Out-of-sample walk-forward expectancy evaluation.
3. Portfolio sector risk veto checks.
4. Trade lifecycle state transitions and R-multiple tracking.
5. Signal calibration and Brier reliability scores.
6. Quote freshness and latency verification.
"""

from datetime import datetime, timedelta, timezone
import pytest

from qx.signals.validator import SignalValidator, ValidationStatus
from qx.backtesting.walk_forward import evaluate_walk_forward_metrics
from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.services.veto_service import VetoService
from qx.execution.lifecycle import TradeLifecycleRecord, LifecycleStage
from qx.signals.calibration import evaluate_signal_calibration
from qx.signals.freshness import FreshnessChecker, FreshnessStatus


def test_multi_factor_signal_validator() -> None:
    validator = SignalValidator(min_rvol=1.5, min_composite_score=70.0)

    # Strong setup with BOS and high RVOL
    res_strong = validator.validate_signal(
        symbol="NVDA",
        trend_bias="BULLISH",
        price=120.0,
        rvol=2.2,
        vwap=118.5,
        bos_confirmed=True,
        fvg_present=True,
        sector_relative_strength=1.5,
    )
    assert res_strong.status == ValidationStatus.VALIDATED
    assert res_strong.composite_score >= 70.0
    assert len(res_strong.factors) == 4

    # Weak setup without BOS
    res_weak = validator.validate_signal(
        symbol="XYZ",
        trend_bias="BULLISH",
        price=50.0,
        rvol=0.8,
        vwap=52.0,
        bos_confirmed=False,
        fvg_present=False,
    )
    assert res_weak.status != ValidationStatus.VALIDATED


def test_walk_forward_oos_expectancy_evaluation() -> None:
    in_sample = [100.0, 150.0, -50.0, 120.0, -40.0]
    out_of_sample_good = [80.0, 110.0, -30.0, 90.0]
    out_of_sample_bad = [-100.0, -50.0, -20.0]

    res_pass = evaluate_walk_forward_metrics(in_sample, out_of_sample_good)
    assert res_pass.is_overfitted is False
    assert res_pass.expectancy_decay_ratio > 0.50

    res_fail = evaluate_walk_forward_metrics(in_sample, out_of_sample_bad)
    assert res_fail.is_overfitted is True


def test_portfolio_sector_risk_veto() -> None:
    config = ScannerConfig()
    veto = VetoService(config)

    # Within limit
    res_ok = veto.check_portfolio_risk("AAPL", current_sector_exposure_pct=18.0, max_sector_limit_pct=25.0)
    assert res_ok.passed is True

    # Exceeds limit
    from qx.options_scanner.models import VetoReasonEnum
    res_fail = veto.check_portfolio_risk("NVDA", current_sector_exposure_pct=30.0, max_sector_limit_pct=25.0)
    assert res_fail.passed is False
    assert res_fail.reason == VetoReasonEnum.SECTOR_CONCENTRATION


def test_trade_lifecycle_state_transitions() -> None:
    trade = TradeLifecycleRecord(
        trade_id="TRD-101",
        symbol="MSFT",
        direction="BULLISH",
        proposed_entry=400.0,
        stop_loss=390.0,
        target_1=420.0,
        target_2=430.0,
    )
    assert trade.current_stage == LifecycleStage.PROPOSED

    # Transition to ACTIVE
    now_dt = datetime.now(timezone.utc)
    trade.transition_to(LifecycleStage.ACTIVE, price=401.0, timestamp=now_dt)
    assert trade.current_stage == LifecycleStage.ACTIVE
    assert trade.actual_entry_price == 401.0
    assert trade.entry_slippage == 1.0

    # Transition to TARGET_REACHED
    later_dt = now_dt + timedelta(hours=5)
    trade.transition_to(LifecycleStage.TARGET_REACHED, price=420.0, timestamp=later_dt)
    assert trade.current_stage == LifecycleStage.TARGET_REACHED
    assert trade.realized_r_multiple == 1.9  # (420 - 401) / 10 = 1.9
    assert trade.holding_hours == 5.0


def test_signal_score_calibration() -> None:
    # Tuple format: (score, is_win, r_multiple)
    history = [
        (90.0, True, 2.5),
        (85.0, True, 2.0),
        (82.0, False, -1.0),
        (70.0, True, 1.2),
        (65.0, False, -1.0),
        (45.0, False, -1.0),
    ]

    report = evaluate_signal_calibration(history)
    assert report.total_trades_analyzed == 6
    assert len(report.buckets) == 3
    assert report.buckets[0].sample_count == 3
    assert report.buckets[0].win_rate == pytest.approx(0.6667, abs=1e-3)


def test_freshness_latency_checker() -> None:
    checker = FreshnessChecker(max_intraday_age_seconds=5.0, max_swing_age_seconds=60.0)
    now_dt = datetime.now(timezone.utc)

    # Fresh quote
    q_fresh = now_dt - timedelta(seconds=2)
    res_fresh = checker.check_freshness("SPY", q_fresh, mode="swing", now=now_dt)
    assert res_fresh.status == FreshnessStatus.FRESH
    assert res_fresh.is_executable is True

    # Stale quote
    q_stale = now_dt - timedelta(seconds=150)
    res_stale = checker.check_freshness("SPY", q_stale, mode="swing", now=now_dt)
    assert res_stale.status == FreshnessStatus.STALE_BLOCKED
    assert res_stale.is_executable is False
