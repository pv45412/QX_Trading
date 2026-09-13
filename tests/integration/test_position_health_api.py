"""Integration tests for /api/position-health FastAPI endpoint."""

import pytest
from fastapi.testclient import TestClient
from qx.interfaces.web import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test_scanner.db"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    app = create_app(database=db_path, cache_dir=cache_dir)
    return TestClient(app)


def test_position_health_endpoint_strong_hold(client):
    response = client.post(
        "/api/position-health",
        json={
            "trend_score": 90.0,
            "structure_score": 90.0,
            "invalidation_distance_pct": 5.0,
            "reward_remaining_pct": 80.0,
            "momentum_score": 85.0,
            "volatility_score": 80.0,
            "dte": 30,
            "stop_breached": False,
            "assignment_imminent": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["composite_score"] >= 80.0
    assert data["action"] == "STRONG HOLD"
    assert data["hard_override_active"] is False


def test_position_health_endpoint_stop_breached(client):
    response = client.post(
        "/api/position-health",
        json={
            "trend_score": 90.0,
            "structure_score": 90.0,
            "invalidation_distance_pct": 0.0,
            "reward_remaining_pct": 80.0,
            "momentum_score": 85.0,
            "volatility_score": 80.0,
            "dte": 30,
            "stop_breached": True,
            "assignment_imminent": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["composite_score"] == 0.0
    assert data["action"] == "EXIT / REVIEW"
    assert data["hard_override_active"] is True
