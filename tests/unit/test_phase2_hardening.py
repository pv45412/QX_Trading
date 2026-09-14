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

    # Convert ES trigger level to SPX cash strike (cash = trigger_es - live_basis)
    trigger_es = 5850.00
    expected_spx_cash = round(trigger_es - basis_info["basis"], 2)
    spx_strike = router.get_live_spx_strike(es_target=trigger_es, es_price=5800.50, spx_price=5780.00)
    assert spx_strike == expected_spx_cash  # 5850.00 - 20.50 = 5829.50

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


def test_atomic_basis_from_quotes():
    class MockQuote:
        def __init__(self, price):
            self.last_price = price

    class MockProvider:
        def get_quotes(self, symbols):
            return {
                "/ES": MockQuote(5800.50),
                "$SPX": MockQuote(5780.00),
            }

    router = OrderRouter()
    provider = MockProvider()
    atomic_basis = router.get_atomic_basis_from_quotes(provider)
    assert atomic_basis["is_valid"] is True
    assert atomic_basis["basis"] == 20.50


def test_gex_missing_settlement_type_0dte_fallback():
    # 0DTE monthly contract missing settlementType attribute (Schwab quote summary pattern)
    chain = pd.DataFrame([
        {"strike": 5750, "option_type": "call", "open_interest": 300, "volume": 100, "dte": 0, "symbol": "SPX260914C05750000"},  # root $SPX, missing settlementType, dte=0
        {"strike": 5850, "option_type": "call", "open_interest": 500, "volume": 200, "dte": 30, "symbol": "SPX261016C05850000"},  # monthly dte=30, missing settlementType
    ])

    segregated = calculate_segregated_gamma_exposure("SPX", 5750.0, chain)
    pm_gex = segregated["PM_WEEKLY"]
    
    # 0DTE active intraday contract (dte=0) should be included in PM_WEEKLY despite missing settlementType
    assert pm_gex.top_call_gamma_strike == 5750.0


def test_price_normalization_decoupled():
    from qx.market.price_normalization import calculate_es_spx_basis, normalize_es_target_to_spx
    basis_info = calculate_es_spx_basis(5800.50, 5780.00)
    assert basis_info["is_valid"] is True
    assert basis_info["basis"] == 20.50
    spx_target = normalize_es_target_to_spx(5850.00, basis_info["basis"])
    assert spx_target == 5829.50


def test_put_credit_spread_requires_valid_long_put():
    from datetime import datetime, timezone
    from qx.options_scanner.config import ScannerConfig
    from qx.options_scanner.models import OptionChain, OptionContract, OptionTypeEnum, UnderlyingQuote
    from qx.options_scanner.services.strategy_selector import StrategyFit
    from qx.options_scanner.services.trade_constructor import TradeConstructor

    constructor = TradeConstructor(ScannerConfig())
    quote = UnderlyingQuote(symbol="NVDA", last_price=120.0, bid=119.9, ask=120.1, volume=10000, timestamp=datetime.now(timezone.utc))

    # Chain with ONLY short put contract (no valid lower-strike long put)
    short_put = OptionContract(
        symbol="NVDA_P_115", underlying_symbol="NVDA", option_type=OptionTypeEnum.PUT,
        strike=115.0, expiration="30DTE", dte=30, bid=2.0, ask=2.2, volume=500, open_interest=1000, delta=-0.25
    )
    chain = OptionChain(underlying_symbol="NVDA", expirations=["30DTE"], retrieved_at=datetime.now(timezone.utc), contracts=[short_put])
    strategy = StrategyFit(strategy_name="Bull Put Credit Spread", fit_score=85, rationale="Support bounce", category="Bullish", explanation="Credit spread")

    trade = constructor.construct_trade(quote, chain, strategy)
    # Must return None instead of fabricating a 5.0 width spread with identical long put
    assert trade is None


def test_payoff_topology_analytical_legs():
    from qx.strategies.payoff import OptionLeg, generate_strategy_payoff
    # Unhedged short call leg (unlimited upside risk)
    short_call = OptionLeg(option_type="call", strike=100.0, action="sell", quantity=1.0, premium=2.50)
    res = generate_strategy_payoff("Short Call", 100.0, [short_call])
    assert res.max_risk_dollars == 999999.0  # analytical unlimited downside risk detected via legs


def test_options_ideas_simulated_gating_and_no_fallback_prices(monkeypatch):
    from qx.interfaces.web import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    res = client.get("/api/options-scanner/ideas")
    assert res.status_code == 200
    data = res.json()

    # Must be SIMULATED or BLOCKED, never executable
    assert data["publication_state"] in ("SIMULATED", "BLOCKED")
    assert data["executable"] is False
    assert data["evidence_reason"] == "Option contracts and Greeks are modeled and are not verified from a live option chain."

    # Test BLOCKED state when market quotes fail (zero price)
    from qx.market.ticker_service import TickerQuote
    def mock_failed_fetch(symbol, provider=None):
        return TickerQuote(symbol=symbol, price=0.0, prior_close=0.0, change_dollar=0.0, change_pct=0.0, gex_regime="Neutral", as_of="BLOCKED: Market Quote Unavailable")

    monkeypatch.setattr("qx.market.ticker_service.fetch_ticker_quote", mock_failed_fetch)
    blocked_res = client.get("/api/options-scanner/ideas")
    blocked_data = blocked_res.json()

    assert blocked_data["publication_state"] == "BLOCKED"
    assert blocked_data["executable"] is False
    assert blocked_data["ideas"] == []


def test_telemetry_zero_observations_returns_none(tmp_path):
    from qx.telemetry.service import TelemetryService
    telemetry = TelemetryService(log_dir=tmp_path)
    res = telemetry.calculate_calibrated_win_rate("NON_EXISTENT_SYMBOL")
    assert res["sample_size"] == 0
    assert res["empirical_win_rate_pct"] is None
    assert res["calibrated"] is False
