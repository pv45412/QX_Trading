"""Unit tests for Schwab Broker Adapter & Movers Integration."""

import pytest
from qx.brokers.schwab import (
    DEFAULT_SCHWAB_ENV_VALUES,
    SchwabApiClient,
    SchwabTokenManager,
    fetch_top_movers,
    normalize_screeners,
    save_schwab_env,
)


def test_normalize_screeners_valid_payload():
    """Verify normalize_screeners correctly calculates daily returns for market movers."""
    payload = {
        "screeners": [
            {"symbol": "NVDA", "lastPrice": 120.0, "netChange": 6.0},
            {"symbol": "AAPL", "lastPrice": 220.0, "netChange": -4.0},
        ]
    }
    result = normalize_screeners(payload)
    assert len(result) == 2
    assert result[0]["symbol"] == "NVDA"
    assert result[0]["last"] == 120.0
    assert result[0]["change"] == 6.0
    assert abs(result[0]["return"] - (6.0 / 114.0)) < 1e-4

    assert result[1]["symbol"] == "AAPL"
    assert result[1]["change"] == -4.0
    assert abs(result[1]["return"] - (-4.0 / 224.0)) < 1e-4


def test_normalize_screeners_invalid_payload():
    """Verify normalize_screeners raises ValueError for bad inputs or zero reference prices."""
    with pytest.raises(ValueError, match="Unexpected movers response"):
        normalize_screeners({"screeners": "invalid_type"})

    with pytest.raises(ValueError, match="Invalid reference price"):
        normalize_screeners({"screeners": [{"symbol": "BAD", "lastPrice": 0.0, "netChange": 0.0}]})


def test_schwab_package_exports():
    """Verify public symbols are accessible via qx.brokers.schwab package."""
    assert callable(normalize_screeners)
    assert callable(fetch_top_movers)
    assert callable(save_schwab_env)
    assert SchwabApiClient is not None
    assert SchwabTokenManager is not None
    assert "SCANNER_SCHWAB_API_BASE_URL" in DEFAULT_SCHWAB_ENV_VALUES
