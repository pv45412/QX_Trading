"""End-to-end integration test for SignalService and TelemetryService."""

from datetime import datetime, timedelta, timezone
import pytest

from qx.options_scanner.config import ScannerConfig
from qx.options_scanner.models import UnderlyingQuote, OptionContract, OptionChain, OptionTypeEnum
from qx.options_scanner.services.signal_service import SignalService
from qx.options_scanner.services.telemetry import TelemetryService


def test_full_signal_pipeline_end_to_end(tmp_path):
    now = datetime.now(timezone.utc)
    quote = UnderlyingQuote(
        symbol="AAPL",
        last_price=220.0,
        bid=219.90,
        ask=220.10,
        volume=15000000,
        timestamp=now
    )

    exp_date = (now + timedelta(days=35)).strftime("%Y-%m-%d")

    contracts = [
        # Call contracts
        OptionContract(
            symbol="AAPL260918C00215000",
            underlying_symbol="AAPL",
            strike=215.0,
            expiration=exp_date,
            dte=35,
            option_type=OptionTypeEnum.CALL,
            bid=10.0,
            ask=10.5,
            delta=0.65,
            open_interest=500,
            volume=200,
            implied_volatility=0.22
        ),
        OptionContract(
            symbol="AAPL260918C00225000",
            underlying_symbol="AAPL",
            strike=225.0,
            expiration=exp_date,
            dte=35,
            option_type=OptionTypeEnum.CALL,
            bid=4.0,
            ask=4.3,
            delta=0.40,
            open_interest=600,
            volume=250,
            implied_volatility=0.21
        ),
        # Put contracts
        OptionContract(
            symbol="AAPL260918P00215000",
            underlying_symbol="AAPL",
            strike=215.0,
            expiration=exp_date,
            dte=35,
            option_type=OptionTypeEnum.PUT,
            bid=4.5,
            ask=4.8,
            delta=-0.35,
            open_interest=500,
            volume=150,
            implied_volatility=0.23
        ),
        OptionContract(
            symbol="AAPL260918P00205000",
            underlying_symbol="AAPL",
            strike=205.0,
            expiration=exp_date,
            dte=35,
            option_type=OptionTypeEnum.PUT,
            bid=1.8,
            ask=2.0,
            delta=-0.15,
            open_interest=400,
            volume=100,
            implied_volatility=0.24
        )
    ]

    chain = OptionChain(underlying_symbol="AAPL", retrieved_at=now, contracts=contracts)

    signal_service = SignalService()
    res = signal_service.scan_ticker(
        quote=quote,
        chain=chain,
        daily_returns=[0.01, -0.005, 0.012, 0.008, -0.003],
        bos_choch=85, vwap=80, ema=85, rvol=75, cum_delta=80, fvg=70, rs=75,
        current_iv=0.21,
        account_equity=50000.0
    )

    assert res.passed_veto is True
    assert res.symbol == "AAPL"
    assert res.overall_score > 60.0
    assert res.direction_result.bias == "BULLISH"
    assert res.trade is not None
    assert res.trade.strategy_name in ("Bull Call Debit Spread", "Bull Put Credit Spread", "Long Call")
    assert res.risk_result is not None

    # Test Telemetry logging
    telemetry = TelemetryService(storage_dir=tmp_path)
    snapshot_file = telemetry.log_scan_snapshot(res)
    assert snapshot_file.exists()

    loaded = telemetry.load_snapshots_for_symbol("AAPL")
    assert len(loaded) == 1
    assert loaded[0]["symbol"] == "AAPL"
    assert loaded[0]["config_version"] == "1.0.0"
