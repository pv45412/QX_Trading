"""Integration tests for /api/telemetry/signals and /api/market/{symbol}/snapshot endpoints."""

import pytest
from fastapi.testclient import TestClient
from qx.interfaces.web import create_app
from qx.telemetry.telemetry_service import TelemetryService, SignalTelemetryRecord


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test_scanner.db"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    app = create_app(database=db_path, cache_dir=cache_dir)
    return TestClient(app)


def test_telemetry_signals_endpoint(client):
    # Record dummy telemetry first
    svc = TelemetryService()
    svc.record_signal(
        SignalTelemetryRecord(
            symbol="QQQ",
            underlying_price=480.0,
            direction_score=80.0,
            volatility_score=55.0,
            qx_score=67.5,
            recommended_strategy="LEAP Long Call",
            max_risk_dollars=300.0,
        )
    )

    response = client.get("/api/telemetry/signals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[-1]["symbol"] == "QQQ"


def test_market_snapshot_endpoint(client):
    response = client.get("/api/market/AAPL/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AAPL"
    assert "status" in data
