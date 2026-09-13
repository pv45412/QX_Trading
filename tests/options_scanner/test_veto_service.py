from datetime import datetime, timedelta, timezone

from qx.options_scanner.config import get_scanner_config
from qx.options_scanner.models import (
    OptionChain, OptionContract, OptionTypeEnum, UnderlyingQuote, VetoReasonEnum
)
from qx.options_scanner.services.veto_service import VetoService


def test_veto_insolvency():
    config = get_scanner_config()
    service = VetoService(config)
    now = datetime.now(timezone.utc)
    quote = UnderlyingQuote(
        symbol="XYZ",
        last_price=10.0,
        bid=9.9,
        ask=10.1,
        volume=1000,
        timestamp=now,
        is_insolvent=True
    )
    res = service.check_underlying(quote, now=now)
    assert not res.passed
    assert res.reason == VetoReasonEnum.INSOLVENCY_FLAG


def test_veto_stale_data():
    config = get_scanner_config()
    service = VetoService(config)
    now = datetime.now(timezone.utc)
    stale_ts = now - timedelta(seconds=1200)  # 20 mins > 15 mins
    quote = UnderlyingQuote(
        symbol="AAPL",
        last_price=150.0,
        bid=149.9,
        ask=150.1,
        volume=50000,
        timestamp=stale_ts
    )
    res = service.check_underlying(quote, now=now)
    assert not res.passed
    assert res.reason == VetoReasonEnum.DATA_STALE


def test_veto_earnings_blackout():
    config = get_scanner_config()
    service = VetoService(config)
    now = datetime.now(timezone.utc)
    earnings_dt = now + timedelta(days=2)  # Inside 5-day window
    quote = UnderlyingQuote(
        symbol="NVDA",
        last_price=200.0,
        bid=199.9,
        ask=200.1,
        volume=100000,
        timestamp=now,
        earnings_date=earnings_dt
    )
    res = service.check_underlying(quote, now=now)
    assert not res.passed
    assert res.reason == VetoReasonEnum.EARNINGS_BLACKOUT


def test_veto_event_blackout():
    config = get_scanner_config()
    service = VetoService(config)
    now = datetime.now(timezone.utc)
    fomc_dt = now + timedelta(hours=24)  # Inside 48h window
    quote = UnderlyingQuote(
        symbol="SPY",
        last_price=500.0,
        bid=499.9,
        ask=500.1,
        volume=1000000,
        timestamp=now,
        next_fomc_cpi_event=fomc_dt
    )
    res = service.check_underlying(quote, now=now)
    assert not res.passed
    assert res.reason == VetoReasonEnum.EVENT_BLACKOUT


def test_veto_chain_incomplete():
    config = get_scanner_config()
    service = VetoService(config)
    now = datetime.now(timezone.utc)
    quote = UnderlyingQuote(symbol="MSFT", last_price=400.0, bid=399.9, ask=401.0, volume=10000, timestamp=now)
    chain = OptionChain(underlying_symbol="MSFT", retrieved_at=now, contracts=[])
    res = service.check_chain(chain, quote, now=now)
    assert not res.passed
    assert res.reason == VetoReasonEnum.CHAIN_INCOMPLETE


def test_veto_contract_liquidity_oi():
    config = get_scanner_config()
    service = VetoService(config)
    contract = OptionContract(
        symbol="AAPL260918C00150000",
        underlying_symbol="AAPL",
        strike=150.0,
        expiration="2026-09-18",
        dte=5,
        option_type=OptionTypeEnum.CALL,
        bid=2.0,
        ask=2.1,
        open_interest=50  # Below 100 limit
    )
    res = service.check_contract_liquidity(contract)
    assert not res.passed
    assert res.reason == VetoReasonEnum.LIQUIDITY_OI


def test_veto_contract_liquidity_spread():
    config = get_scanner_config()
    service = VetoService(config)
    contract = OptionContract(
        symbol="AAPL260918C00150000",
        underlying_symbol="AAPL",
        strike=150.0,
        expiration="2026-09-18",
        dte=5,
        option_type=OptionTypeEnum.CALL,
        bid=2.0,
        ask=2.5,  # (2.5 - 2.0)/2.25 = 22.2% > 8% max limit
        open_interest=500
    )
    res = service.check_contract_liquidity(contract)
    assert not res.passed
    assert res.reason == VetoReasonEnum.LIQUIDITY_SPREAD
