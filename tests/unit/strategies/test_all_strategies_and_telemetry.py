"""Unit tests for LEAP, PMCC, Wheel strategy modules and Telemetry Service."""

import pytest
from qx.strategies.base import StrategyContext
from qx.strategies.leaps.leap_call import LEAPCallModule
from qx.strategies.pmcc.pmcc import PMCCModule
from qx.strategies.wheel.wheel import WheelStrategyModule
from qx.telemetry.telemetry_service import TelemetryService, SignalTelemetryRecord


def test_leap_call_module():
    mod = LEAPCallModule()
    ctx = StrategyContext(symbol="NVDA", underlying_price=120.0, direction_score=85.0, iv_rank=20.0)
    score = mod.evaluate_compatibility(ctx)
    assert score >= 70.0

    trade = mod.construct_trade(ctx, {})
    assert trade is not None
    assert trade.strategy_name == "LEAP Long Call"
    assert trade.dte == 365


def test_pmcc_module():
    mod = PMCCModule()
    ctx = StrategyContext(symbol="AMD", underlying_price=160.0, direction_score=70.0, iv_rank=30.0)
    score = mod.evaluate_compatibility(ctx)
    assert score >= 50.0

    trade = mod.construct_trade(ctx, {})
    assert trade is not None
    assert trade.strategy_name == "Poor Man's Covered Call (PMCC)"
    assert len(trade.legs) == 2


def test_wheel_module():
    mod = WheelStrategyModule()
    ctx = StrategyContext(symbol="TSLA", underlying_price=220.0, direction_score=60.0, iv_rank=75.0)
    score = mod.evaluate_compatibility(ctx)
    assert score >= 60.0

    trade = mod.construct_trade(ctx, {})
    assert trade is not None
    assert trade.strategy_name == "Wheel Strategy (Cash-Secured Put)"


def test_telemetry_service(tmp_path):
    svc = TelemetryService(log_dir=tmp_path)
    record = SignalTelemetryRecord(
        symbol="SPY",
        underlying_price=540.0,
        direction_score=75.0,
        volatility_score=60.0,
        qx_score=67.5,
        recommended_strategy="Bull Call Debit Spread",
        max_risk_dollars=250.0,
    )
    sig_id = svc.record_signal(record)
    assert sig_id == record.signal_id

    records = svc.list_records()
    assert len(records) == 1
    assert records[0]["symbol"] == "SPY"
