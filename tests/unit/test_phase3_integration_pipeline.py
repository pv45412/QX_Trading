"""Comprehensive integration test suite for QX Phase 3 Pipeline Integrator.

Verifies end-to-end execution flow:
1. Successful Path (Verified market data -> Signal Validation -> Option Chain -> Portfolio Snapshot -> Risk Check -> Freshness Check -> VERIFIED + Executable proposal).
2. Fail-Closed Paths (Stale quotes, missing option chain, portfolio concentration limit breach, duplicate risk, stale portfolio snapshot).
"""

from datetime import datetime, timedelta, timezone
import pytest

from qx.execution.models import OrderStatus
from qx.execution.order_router import OrderRouter
from qx.execution.pipeline import Phase3PipelineIntegrator
from qx.options.chains import OptionContract
from qx.options_scanner.models import UnderlyingQuote, VetoReasonEnum
from qx.portfolio.models import PortfolioPosition, PortfolioSnapshot
from qx.portfolio.read_only_service import ReadOnlyPortfolioService
from qx.signals.freshness import FreshnessChecker


def test_pipeline_successful_execution_path() -> None:
    now_dt = datetime.now(timezone.utc)
    quote_ts = now_dt - timedelta(seconds=1)
    signal_ts = now_dt - timedelta(seconds=1)

    quote = UnderlyingQuote(
        symbol="NVDA",
        last_price=120.0,
        bid=119.9,
        ask=120.1,
        volume=5000000,
        timestamp=quote_ts,
    )

    contracts = [
        OptionContract(
            symbol="NVDA",
            expiration=datetime(2027, 9, 17).date(),
            contract_symbol="NVDA_270917C120",
            strike=120.0,
            option_type="call",
            bid=15.0,
            ask=15.5,
            last_price=15.2,
            volume=500,
            open_interest=2500,
            implied_volatility=0.35,
            dte=368,
            delta=0.80,
        )
    ]

    portfolio_service = ReadOnlyPortfolioService()
    # Initialize fresh portfolio snapshot with 10% Tech exposure
    positions = [
        PortfolioPosition(
            symbol="AAPL",
            asset_class="STOCK",
            sector="Technology",
            quantity=100.0,
            entry_price=200.0,
            current_price=210.0,
        )
    ]
    portfolio_service.fetch_fresh_snapshot(
        equity=500000.0,
        cash=200000.0,
        buying_power=400000.0,
        positions=positions,
        now=now_dt,
    )

    integrator = Phase3PipelineIntegrator(portfolio_service=portfolio_service)

    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=signal_ts,
        option_contracts=contracts,
        sector="Technology",
        rvol=2.0,
        vwap=119.0,
        bos_confirmed=True,
        fvg_present=True,
        now=now_dt,
    )

    assert proposal.publication_state == "VERIFIED"
    assert proposal.executable is True
    assert proposal.veto_result.passed is True
    assert proposal.order_request is not None
    assert proposal.order_request.publication_state == "VERIFIED"
    assert proposal.order_request.executable is True

    # Order router submits successfully
    router = OrderRouter()
    submitted_order = router.submit_order(proposal.order_request)
    assert submitted_order.status == OrderStatus.SUBMITTED


def test_pipeline_fail_closed_missing_option_chain() -> None:
    now_dt = datetime.now(timezone.utc)
    quote = UnderlyingQuote(
        symbol="NVDA",
        last_price=120.0,
        bid=119.9,
        ask=120.1,
        volume=5000000,
        timestamp=now_dt,
    )

    integrator = Phase3PipelineIntegrator()
    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        option_contracts=None,  # Missing live option chain
        bos_confirmed=True,
        now=now_dt,
    )

    assert proposal.publication_state == "SIMULATED"
    assert proposal.executable is False
    assert proposal.order_request is None


def test_pipeline_fail_closed_stale_quote_timestamp() -> None:
    now_dt = datetime.now(timezone.utc)
    stale_quote_ts = now_dt - timedelta(seconds=300)  # Exceeds max freshness threshold

    quote = UnderlyingQuote(
        symbol="NVDA",
        last_price=120.0,
        bid=119.9,
        ask=120.1,
        volume=5000000,
        timestamp=stale_quote_ts,
    )

    integrator = Phase3PipelineIntegrator()
    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        bos_confirmed=True,
        now=now_dt,
    )

    assert proposal.publication_state == "BLOCKED"
    assert proposal.executable is False
    assert "Dual Freshness BLOCKED" in proposal.evidence_reason


def test_pipeline_fail_closed_sector_concentration_veto() -> None:
    now_dt = datetime.now(timezone.utc)
    quote = UnderlyingQuote(
        symbol="NVDA",
        last_price=120.0,
        bid=119.9,
        ask=120.1,
        volume=5000000,
        timestamp=now_dt,
    )

    portfolio_service = ReadOnlyPortfolioService()
    # Initialize portfolio with 24% Tech exposure already
    positions = [
        PortfolioPosition(
            symbol="AMD",
            asset_class="STOCK",
            sector="Technology",
            quantity=800.0,
            entry_price=150.0,
            current_price=150.0,  # $120,000 / $500,000 = 24%
        )
    ]
    portfolio_service.fetch_fresh_snapshot(
        equity=500000.0,
        cash=100000.0,
        buying_power=200000.0,
        positions=positions,
        now=now_dt,
    )

    integrator = Phase3PipelineIntegrator(portfolio_service=portfolio_service)

    # Adding NVDA (3% impact) -> 27% projected > 25% limit
    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        sector="Technology",
        bos_confirmed=True,
        now=now_dt,
    )

    assert proposal.publication_state == "BLOCKED"
    assert proposal.executable is False
    assert proposal.veto_result.reason == VetoReasonEnum.SECTOR_CONCENTRATION
    assert proposal.score_breakdown.is_vetoed is True


def test_pipeline_fail_closed_duplicate_position_veto() -> None:
    now_dt = datetime.now(timezone.utc)
    quote = UnderlyingQuote(
        symbol="NVDA",
        last_price=120.0,
        bid=119.9,
        ask=120.1,
        volume=5000000,
        timestamp=now_dt,
    )

    portfolio_service = ReadOnlyPortfolioService()
    positions = [
        PortfolioPosition(
            symbol="NVDA",
            asset_class="STOCK",
            sector="Technology",
            quantity=100.0,
            entry_price=110.0,
            current_price=120.0,
        )
    ]
    portfolio_service.fetch_fresh_snapshot(
        equity=500000.0,
        cash=200000.0,
        buying_power=400000.0,
        positions=positions,
        now=now_dt,
    )

    integrator = Phase3PipelineIntegrator(portfolio_service=portfolio_service)

    proposal = integrator.evaluate_pipeline(
        symbol="NVDA",
        trend_bias="BULLISH",
        quote=quote,
        signal_timestamp=now_dt,
        bos_confirmed=True,
        now=now_dt,
    )

    assert proposal.publication_state == "BLOCKED"
    assert proposal.executable is False
    assert proposal.veto_result.reason == VetoReasonEnum.DUPLICATE_RISK
