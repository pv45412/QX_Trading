"""Unit tests for QX Telemetry & Signal Audit Logging Service."""

import pytest
from qx.telemetry import SignalTelemetryRecord, TelemetryService
from qx.telemetry.telemetry_service import TelemetryService as ReexportedService


def test_record_signal_and_retrieve(tmp_path):
    """Verify recording signal telemetry to JSONL log and reading it back."""
    service = TelemetryService(log_dir=tmp_path)
    record = SignalTelemetryRecord(
        symbol="NVDA",
        underlying_price=120.0,
        direction_score=85.0,
        volatility_score=70.0,
        qx_score=82.5,
        recommended_strategy="Bull Call Spread",
        max_risk_dollars=250.0,
        quality_grade="A",
    )

    signal_id = service.record_signal(record)
    assert signal_id == record.signal_id

    records = service.list_records(limit=10)
    assert len(records) == 1
    assert records[0]["symbol"] == "NVDA"
    assert records[0]["direction_score"] == 85.0
    assert records[0]["quality_grade"] == "A"


def test_list_records_limit(tmp_path):
    """Verify limit slicing on telemetry record retrieval."""
    service = TelemetryService(log_dir=tmp_path)
    for i in range(10):
        record = SignalTelemetryRecord(
            symbol=f"SYM_{i}",
            underlying_price=100.0 + i,
            direction_score=50.0 + i,
            volatility_score=60.0,
            qx_score=70.0,
            recommended_strategy="Long Call",
            max_risk_dollars=100.0,
        )
        service.record_signal(record)

    all_records = service.list_records(limit=100)
    assert len(all_records) == 10

    limited_records = service.list_records(limit=3)
    assert len(limited_records) == 3
    assert limited_records[0]["symbol"] == "SYM_7"
    assert limited_records[2]["symbol"] == "SYM_9"


def test_telemetry_service_backward_compatibility(tmp_path):
    """Verify re-exported TelemetryService works identically."""
    service = ReexportedService(log_dir=tmp_path)
    record = SignalTelemetryRecord(
        symbol="AAPL",
        underlying_price=220.0,
        direction_score=75.0,
        volatility_score=65.0,
        qx_score=72.0,
        recommended_strategy="PMCC",
        max_risk_dollars=500.0,
    )
    service.record_signal(record)
    recs = service.list_records()
    assert len(recs) == 1
    assert recs[0]["symbol"] == "AAPL"
