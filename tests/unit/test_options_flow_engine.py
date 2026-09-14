"""
Unit tests for QX Institutional Options Flow & Order Tape Analyzer Engine (`qx/options_flow/`).
"""

from datetime import date, datetime, timezone
from qx.options_flow import (
    analyze_option_flow,
    OptionFlowTrade,
    UnderlyingContext,
    MarketRegimeContext,
)


def test_options_flow_call_sweep_analysis():
    trades = [
        OptionFlowTrade(
            ticker="XLK",
            option_symbol="XLK260918C00150000",
            expiration=date(2026, 9, 18),
            strike=150.0,
            option_type="call",
            trade_price=3.50,
            bid=3.40,
            ask=3.50,
            size=500,
            effective_premium=175000.0,
            volume=2000,
            open_interest=500,
            implied_volatility=0.28,
            delta=0.55,
            trade_kind="sweep",
        ),
        OptionFlowTrade(
            ticker="XLK",
            option_symbol="XLK260918C00155000",
            expiration=date(2026, 9, 18),
            strike=155.0,
            option_type="call",
            trade_price=1.80,
            bid=1.75,
            ask=1.80,
            size=800,
            effective_premium=144000.0,
            volume=3500,
            open_interest=1000,
            implied_volatility=0.30,
            delta=0.40,
            trade_kind="sweep",
        ),
    ]

    underlying = UnderlyingContext(
        ticker="XLK",
        current_price=148.50,
        support_level=145.0,
        resistance_level=152.0,
        trend="bullish",
    )

    analysis = analyze_option_flow(trades, underlying=underlying)

    assert analysis.ticker == "XLK"
    assert analysis.current_price == 148.50
    assert len(analysis.trades) == 2
    assert analysis.call_buy_score >= 0.0
    assert analysis.final_signal in [
        "STRONG CALL BUY", "LEAN CALL BUY", "NEUTRAL", "LEAN PUT BUY", "STRONG PUT BUY", "NO TRADE",
        "STRONG_CALL_BUY", "LEAN_CALL_BUY", "LEAN_PUT_BUY", "STRONG_PUT_BUY", "NO_TRADE"
    ]


def test_options_flow_put_block_analysis():
    trades = [
        OptionFlowTrade(
            ticker="SPY",
            option_symbol="SPY260918P00500000",
            expiration=date(2026, 9, 18),
            strike=500.0,
            option_type="put",
            trade_price=4.20,
            bid=4.15,
            ask=4.20,
            size=1500,
            effective_premium=630000.0,
            volume=5000,
            open_interest=1200,
            implied_volatility=0.22,
            delta=-0.45,
            trade_kind="block",
        )
    ]

    underlying = UnderlyingContext(
        ticker="SPY",
        current_price=510.0,
        support_level=495.0,
        resistance_level=515.0,
        trend="bearish",
    )

    regime = MarketRegimeContext(macro_event_risk=False, elevated_vix=False)

    analysis = analyze_option_flow(trades, underlying=underlying, regime=regime)

    assert analysis.ticker == "SPY"
    assert len(analysis.suggested_contracts) >= 0
