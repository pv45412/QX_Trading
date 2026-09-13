"""Integration tests for /api/options-scanner/scan endpoint."""

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


def test_options_scanner_api(client):
    response = client.post(
        "/api/options-scanner/scan",
        json={
            "symbol": "NVDA",
            "account_equity": 100000.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "NVDA"
    assert data["passed_veto"] is True
    assert "overall_score" in data
    assert "direction_result" in data
    assert "volatility_result" in data
    assert "strategy_result" in data
