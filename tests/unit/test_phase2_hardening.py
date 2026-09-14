import pandas as pd
import pytest
from qx.execution.models import OrderRequest, OrderSide, OrderType
from qx.execution.order_router import OrderRouter
from qx.market.data_contracts import validate_api_payload_contract
from qx.options.gex import calculate_gamma_exposure, calculate_segregated_gamma_exposure


def test_dynamic_basis_tracking_order_router():
    router = OrderRouter()
    
    # Calculate live basis at order generation instant
    basis_info = router.calculate_live_basis(es_price=5800.50, spx_price=5780.00)
    assert basis_info["is_valid"] is True
    assert basis_info["basis"] == 20.50

    # Convert ES target to SPX strike
    spx_strike = router.get_live_spx_strike(es_target=5850.00, es_price=5800.50, spx_price=5780.00)
    assert spx_strike == 5829.50  # 5850.00 - 20.50

    # Submit order with dynamic basis parameters
    req = OrderRequest(
        symbol="SPX",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        limit_price=5829.50,
    )
    order = router.submit_order(req, es_price=5800.50, spx_price=5780.00)
    assert order.status.value in {"SUBMITTED", "PENDING"}


def test_ampm_gex_segregation():
    # Mock option chain with both SPX (AM monthly) and SPXW (PM weekly/0DTE)
    chain = pd.DataFrame([
        {"strike": 5700, "option_type": "call", "open_interest": 100, "volume": 50, "dte": 0, "symbol": "SPXW260914C05700000", "settlement_type": "PM"},
        {"strike": 5700, "option_type": "put", "open_interest": 80, "volume": 30, "dte": 0, "symbol": "SPXW260914P05700000", "settlement_type": "PM"},
        {"strike": 5800, "option_type": "call", "open_interest": 500, "volume": 200, "dte": 30, "symbol": "SPX261016C05800000", "settlement_type": "AM"},
        {"strike": 5800, "option_type": "put", "open_interest": 400, "volume": 150, "dte": 30, "symbol": "SPX261016P05800000", "settlement_type": "AM"},
    ])

    segregated = calculate_segregated_gamma_exposure("SPX", 5750.0, chain)
    assert "PM_WEEKLY" in segregated
    assert "AM_MONTHLY" in segregated
    assert "COMBINED" in segregated

    pm_gex = segregated["PM_WEEKLY"]
    am_gex = segregated["AM_MONTHLY"]

    assert pm_gex.top_call_gamma_strike == 5700.0
    assert am_gex.top_call_gamma_strike == 5800.0


def test_react_data_contract_audit():
    payload = {
        "publication_state": "VERIFIED",
        "symbol": "SPX",
        "current_price": 5750.0,
        "calendars": [],
    }
    required = ("publication_state", "symbol", "current_price")
    res = validate_api_payload_contract(payload, required)
    assert res["valid"] is True
    assert len(res["missing_keys"]) == 0

    missing_res = validate_api_payload_contract(payload, ("publication_state", "non_existent_key"))
    assert missing_res["valid"] is False
    assert missing_res["missing_keys"] == ["non_existent_key"]
