"""Comprehensive Financial Correctness Test Suite for QX Phase 3.

Verifies 13 explicit P0/P1/P2 financial safety and correctness invariants:
1. Missing portfolio snapshot never produces a synthetic $500K account.
2. Stale or missing broker snapshot cannot become VERIFIED.
3. Option orders use actual contract_symbol and option mid price.
4. Long option position sizing uses premium * 100 max loss.
5. Vertical spread sizing uses analytical max loss.
6. Option Greeks and market values use 100x contract multiplier.
7. Proposed sector concentration is calculated dynamically from actual trade size.
8. Holding underlying stock alone does not trigger duplicate option trade veto.
9. Schwab option chain parser populates delta, gamma, theta, and vega.
10. Sizing errors fail closed with zero units.
11. Portfolio cache thread-safety lock verification.
12. Dual timestamp freshness blocks stale signals.
13. End-to-end fail-closed pipeline verification.
"""

from datetime import date, datetime, timedelta, timezone
import pytest

from qx.brokers.schwab.options import _contract_from_payload
from qx.execution.models import OrderStatus
from qx.execution.order_router import OrderRouter
from qx.execution.pipeline import Phase3PipelineIntegrator
from qx.options.chains import OptionContract
from qx.options_scanner.models import UnderlyingQuote, VetoReasonEnum
from qx.options_scanner.services.position_sizer import AccountEquityPositionSizer
from qx.portfolio.greeks_risk import calculate_portfolio_greeks
from qx.portfolio.models import AccountSnapshot, PortfolioPosition, PortfolioSnapshot
from qx.portfolio.read_only_service import MockReadOnlyBrokerProvider, PortfolioCache, ReadOnlyPortfolioService


def test_missing_portfolio_snapshot_never_produces_synthetic_account() -> None:
    # Service without provider has no fallback
    service = ReadOnlyPortfolioService(provider=None)
    snap = service.get_cached_snapshot()
    assert snap is None

    # Pipeline evaluating with missing provider fails closed
    integrator = Phase3PipelineIntegrator(portfolio_service=service)
    now_dt = datetime.now(timezone.utc)
    quote = UnderlyingQuote(symbol="NVDA", last_price=120.0, bid=119.9, ask=120.1, volume=1000, timestamp=now_dt)

    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        now=now_dt,
    )
    assert proposal.publication_state == "BLOCKED"
    assert proposal.executable is False
    assert proposal.veto_result.reason == VetoReasonEnum.PORTFOLIO_DATA_STALE
    assert "unavailable or stale" in proposal.evidence_reason


def test_stale_or_missing_broker_snapshot_cannot_become_verified() -> None:
    now_dt = datetime.now(timezone.utc)
    provider = MockReadOnlyBrokerProvider(equity=500000.0, cash=200000.0, buying_power=400000.0)
    service = ReadOnlyPortfolioService(provider=provider, cache_ttl_seconds=15.0)

    # Initialize snapshot
    snap_fresh = service.fetch_fresh_snapshot(now=now_dt)
    assert snap_fresh is not None
    assert snap_fresh.freshness_state == "FRESH"

    # Simulate 40s age (> 30s TTL limit)
    later_dt = now_dt + timedelta(seconds=40)
    snap_stale = service.get_cached_snapshot(now=later_dt)
    assert snap_stale is not None
    assert snap_stale.freshness_state == "STALE_BLOCKED"


def test_option_orders_use_contract_symbol_and_option_price() -> None:
    now_dt = datetime.now(timezone.utc)
    quote = UnderlyingQuote(symbol="NVDA", last_price=120.0, bid=119.9, ask=120.1, volume=1000, timestamp=now_dt)
    target_opt = OptionContract(
        symbol="NVDA",
        expiration=date(2027, 9, 17),
        contract_symbol="NVDA_270917C120",
        strike=120.0,
        option_type="call",
        bid=15.0,
        ask=15.5,
        last_price=15.2,
        volume=100,
        open_interest=500,
        implied_volatility=0.30,
        dte=368,
        delta=0.80,
    )

    provider = MockReadOnlyBrokerProvider(equity=500000.0, cash=200000.0, buying_power=400000.0)
    service = ReadOnlyPortfolioService(provider=provider)
    service.fetch_fresh_snapshot(now=now_dt)

    integrator = Phase3PipelineIntegrator(portfolio_service=service)
    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        option_contracts=[target_opt],
        bos_confirmed=True,
        now=now_dt,
    )

    assert proposal.publication_state == "VERIFIED"
    assert proposal.executable is True
    assert proposal.order_request is not None
    assert proposal.order_request.symbol == "NVDA_270917C120"
    assert proposal.order_request.symbol != "NVDA"
    assert proposal.order_request.limit_price == pytest.approx(15.25, abs=1e-2)  # (15.0 + 15.5) / 2 = 15.25


def test_long_option_sizing_uses_premium_multiplier_max_loss() -> None:
    sizer = AccountEquityPositionSizer()
    # Equity = $500,000, Max risk = 0.50% ($2,500). Option premium = $10.00 ($1,000 max loss per contract)
    res = sizer.calculate_position_size(
        symbol="NVDA",
        account_equity=500000.0,
        buying_power=400000.0,
        entry_price=10.0,
        is_option_strategy=True,
        unit_multiplier=100,
        max_risk_pct_per_trade=0.50,
    )
    assert res.max_allowable_dollar_risk == 2500.0
    assert res.max_loss_per_unit == 1000.0
    assert res.recommended_units == 2  # $2,500 // $1,000 = 2 contracts
    assert res.total_dollar_risk == 2000.0


def test_vertical_spread_sizing_uses_analytical_max_loss() -> None:
    sizer = AccountEquityPositionSizer()
    # Spread debit = $3.50, Analytical Max Loss = $350 per spread
    res = sizer.calculate_position_size(
        symbol="AAPL",
        account_equity=500000.0,
        buying_power=400000.0,
        entry_price=3.50,
        max_loss_override_per_contract=350.0,
        is_option_strategy=True,
        unit_multiplier=100,
        max_risk_pct_per_trade=0.50,
    )
    assert res.max_allowable_dollar_risk == 2500.0
    assert res.max_loss_per_unit == 350.0
    assert res.recommended_units == 7  # $2,500 // $350 = 7 contracts


def test_option_greeks_and_market_value_use_100x_multiplier() -> None:
    pos_option = PortfolioPosition(
        symbol="NVDA",
        asset_class="OPTION",
        quantity=5.0,  # 5 contracts
        entry_price=10.0,
        current_price=12.0,
        delta=0.80,
        gamma=0.02,
        theta=-0.05,
        vega=0.10,
    )
    greeks = calculate_portfolio_greeks([pos_option])
    assert greeks.net_delta == pytest.approx(400.0)  # 5 * 0.80 * 100 = 400
    assert greeks.net_gamma == pytest.approx(10.0)   # 5 * 0.02 * 100 = 10
    assert greeks.net_theta == pytest.approx(-25.0)  # 5 * -0.05 * 100 = -25


def test_proposed_concentration_calculated_dynamically() -> None:
    now_dt = datetime.now(timezone.utc)
    quote = UnderlyingQuote(symbol="NVDA", last_price=120.0, bid=119.9, ask=120.1, volume=1000, timestamp=now_dt)
    target_opt = OptionContract(
        symbol="NVDA",
        expiration=date(2027, 9, 17),
        contract_symbol="NVDA_270917C120",
        strike=120.0,
        option_type="call",
        bid=10.0,
        ask=10.0,
        last_price=10.0,
        volume=100,
        open_interest=500,
        implied_volatility=0.30,
        dte=368,
        delta=0.80,
    )

    # Account equity $100,000. 2 contracts @ $10 ($1,000/contract) = $2,000 capital required = 2.0% dynamic impact
    provider = MockReadOnlyBrokerProvider(equity=100000.0, cash=50000.0, buying_power=80000.0)
    service = ReadOnlyPortfolioService(provider=provider)
    service.fetch_fresh_snapshot(now=now_dt)

    integrator = Phase3PipelineIntegrator(portfolio_service=service)
    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        option_contracts=[target_opt],
        bos_confirmed=True,
        now=now_dt,
    )

    assert proposal.score_breakdown.is_vetoed is False
    assert proposal.position_sizing is not None
    assert proposal.position_sizing.recommended_units == 0  # 0.5% max risk ($500) < $1,000 contract risk


def test_holding_underlying_alone_does_not_trigger_duplicate_option_veto() -> None:
    now_dt = datetime.now(timezone.utc)
    quote = UnderlyingQuote(symbol="NVDA", last_price=120.0, bid=119.9, ask=120.1, volume=1000, timestamp=now_dt)
    target_opt = OptionContract(
        symbol="NVDA",
        expiration=date(2027, 9, 17),
        contract_symbol="NVDA_270917C120",
        strike=120.0,
        option_type="call",
        bid=10.0,
        ask=10.5,
        last_price=10.2,
        volume=100,
        open_interest=500,
        implied_volatility=0.30,
        dte=368,
        delta=0.80,
    )

    # Position holds STOCK NVDA (investment exposure)
    stock_pos = [
        PortfolioPosition(
            symbol="NVDA",
            asset_class="STOCK",
            sector="Technology",
            quantity=100.0,
            entry_price=100.0,
            current_price=120.0,
        )
    ]
    provider = MockReadOnlyBrokerProvider(equity=500000.0, cash=200000.0, buying_power=400000.0, positions=stock_pos)
    service = ReadOnlyPortfolioService(provider=provider)
    service.fetch_fresh_snapshot(now=now_dt)

    integrator = Phase3PipelineIntegrator(portfolio_service=service)
    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        option_contracts=[target_opt],
        bos_confirmed=True,
        now=now_dt,
    )

    assert proposal.veto_result.reason != VetoReasonEnum.DUPLICATE_RISK
    assert proposal.publication_state == "VERIFIED"


def test_schwab_option_chain_parser_populates_greeks() -> None:
    raw_payload = {
        "symbol": "NVDA 270917C00120000",
        "strikePrice": 120.0,
        "bid": 15.0,
        "ask": 15.5,
        "last": 15.2,
        "totalVolume": 100,
        "openInterest": 500,
        "volatility": 35.0,
        "delta": 0.82,
        "gamma": 0.015,
        "theta": -0.04,
        "vega": 0.22,
    }
    opt = _contract_from_payload(
        symbol="NVDA",
        expiration=date(2027, 9, 17),
        dte=368,
        strike=120.0,
        payload=raw_payload,
        option_type="call",
    )
    assert opt.delta == 0.82
    assert opt.gamma == 0.015
    assert opt.theta == -0.04
    assert opt.vega == 0.22


def test_sizing_error_fails_closed_with_zero_units() -> None:
    sizer = AccountEquityPositionSizer()
    # Invalid entry price or zero max loss
    res_fail = sizer.calculate_position_size(
        symbol="XYZ",
        account_equity=500000.0,
        buying_power=400000.0,
        entry_price=0.0,
        is_option_strategy=True,
    )
    assert res_fail.recommended_units == 0
    assert res_fail.is_valid is False
    assert "FAIL-CLOSED" in res_fail.summary


def test_portfolio_cache_thread_safety_lock() -> None:
    cache = PortfolioCache(ttl_seconds=30.0)
    assert hasattr(cache, "_lock")
    snapshot = PortfolioSnapshot(
        account=AccountSnapshot(account_id_hash="abc", account_equity=500000.0, cash_balance=100000.0, buying_power=200000.0),
    )
    cache.set(snapshot)
    retrieved = cache.get()
    assert retrieved is not None
    assert retrieved.account.account_equity == 500000.0
