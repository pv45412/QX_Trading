"""Unit tests for QX Options Scanner & Signal Service."""

from datetime import datetime, timezone
import pytest
from qx.options_scanner import (
    DirectionService,
    OptionChain,
    OptionContract,
    OptionTypeEnum,
    ScanResult,
    SignalService,
    UnderlyingQuote,
    VetoService,
)


def test_underlying_quote_mid_price():
    """Verify UnderlyingQuote mid_price calculation."""
    now = datetime.now(timezone.utc)
    quote = UnderlyingQuote(
        symbol="NVDA",
        last_price=120.0,
        bid=119.90,
        ask=120.10,
        volume=1000000,
        timestamp=now,
    )
    assert quote.mid_price == 120.0


def test_option_contract_spread_pct():
    """Verify OptionContract spread_pct calculation."""
    contract = OptionContract(
        symbol="NVDA261015C120",
        underlying_symbol="NVDA",
        strike=120.0,
        expiration="2026-10-15",
        dte=30,
        option_type=OptionTypeEnum.CALL,
        bid=5.00,
        ask=5.20,
        implied_volatility=0.30,
    )
    assert contract.mid_price == 5.10
    assert abs(contract.spread_pct - (0.20 / 5.10)) < 1e-3


def test_signal_service_ticker_scan():
    """Verify SignalService ticker scanning producing a ScanResult."""
    now = datetime.now(timezone.utc)
    quote = UnderlyingQuote(
        symbol="AAPL",
        last_price=220.0,
        bid=219.95,
        ask=220.05,
        volume=5000000,
        timestamp=now,
    )
    contracts = [
        OptionContract(
            symbol="AAPL261015C220",
            underlying_symbol="AAPL",
            strike=220.0,
            expiration="2026-10-15",
            dte=30,
            option_type=OptionTypeEnum.CALL,
            bid=8.00,
            ask=8.20,
            open_interest=5000,
            volume=1200,
            implied_volatility=0.25,
        ),
        OptionContract(
            symbol="AAPL261015P220",
            underlying_symbol="AAPL",
            strike=220.0,
            expiration="2026-10-15",
            dte=30,
            option_type=OptionTypeEnum.PUT,
            bid=7.50,
            ask=7.70,
            open_interest=4000,
            volume=900,
            implied_volatility=0.25,
        ),
    ]
    chain = OptionChain(underlying_symbol="AAPL", retrieved_at=now, contracts=contracts)

    service = SignalService()
    result = service.scan_ticker(quote=quote, chain=chain, account_equity=100000.0)

    assert isinstance(result, ScanResult)
    assert result.symbol == "AAPL"


def test_options_scanner_package_exports():
    """Verify public symbols are exported via qx.options_scanner package."""
    assert SignalService is not None
    assert VetoService is not None
    assert DirectionService is not None
    assert UnderlyingQuote is not None
    assert OptionContract is not None
