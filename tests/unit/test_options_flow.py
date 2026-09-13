from __future__ import annotations

from datetime import date

import pandas as pd

from qx.options_flow.engine import analyze_option_flow, parse_flow_csv
from qx.options_flow.models import MarketRegimeContext, OptionFlowTrade, UnderlyingContext
from qx.storage.options_flow import SQLiteOptionFlowRepository
from qx.ui.pages.options_flow import _filter_trades_for_ticker, _sample_flow_frame


def _underlying(*, trend: str = "up") -> UnderlyingContext:
    return UnderlyingContext(
        ticker="SPY",
        current_price=505.0,
        vwap=501.0,
        prior_day_high=504.0,
        prior_day_low=496.0,
        opening_range_high=503.5,
        opening_range_low=499.0,
        relative_volume=1.4,
        trend_direction=trend,  # type: ignore[arg-type]
        nearest_demand=499.0,
        nearest_supply=503.0,
    )


def _bull_regime() -> MarketRegimeContext:
    return MarketRegimeContext(
        spy_trend="bullish",
        qqq_trend="bullish",
        vix_trend="falling",
        sector_strength="strong",
    )


def test_bullish_ask_call_flow_scores_calls_above_puts() -> None:
    trades = [
        OptionFlowTrade(
            ticker="SPY",
            option_symbol="SPY260619C00510000",
            expiration=date(2026, 6, 19),
            strike=510,
            option_type="CALL",
            trade_price=3.1,
            bid=2.95,
            ask=3.1,
            size=500,
            volume=5_000,
            open_interest=12_000,
            implied_volatility=0.24,
            delta=0.45,
            trade_kind="sweep",
        )
    ]

    analysis = analyze_option_flow(trades, underlying=_underlying(), regime=_bull_regime())

    assert analysis.call_buy_score > analysis.put_buy_score
    assert analysis.final_signal in {"CALLS STRONG", "CALLS WATCH"}
    assert analysis.no_trade_risk < 75
    assert any("above VWAP" in reason for reason in analysis.why)


def test_conflicting_call_and_put_flow_raises_no_trade_risk() -> None:
    trades = [
        OptionFlowTrade(
            ticker="SPY",
            option_symbol="SPY260619C00510000",
            expiration=date(2026, 6, 19),
            strike=510,
            option_type="CALL",
            trade_price=3.1,
            bid=2.95,
            ask=3.1,
            size=400,
            volume=4_000,
            open_interest=8_000,
            implied_volatility=0.3,
        ),
        OptionFlowTrade(
            ticker="SPY",
            option_symbol="SPY260619P00495000",
            expiration=date(2026, 6, 19),
            strike=495,
            option_type="PUT",
            trade_price=3.0,
            bid=2.85,
            ask=3.0,
            size=400,
            volume=4_000,
            open_interest=8_000,
            implied_volatility=0.3,
        ),
    ]

    analysis = analyze_option_flow(trades, underlying=_underlying(), regime=_bull_regime())

    assert analysis.no_trade_risk >= 35
    assert any("conflicted" in warning.lower() for warning in analysis.warnings)


def test_high_iv_event_flow_flags_iv_chase_risk() -> None:
    trades = [
        OptionFlowTrade(
            ticker="SPY",
            option_symbol="SPY260619C00510000",
            expiration=date(2026, 6, 19),
            strike=510,
            option_type="CALL",
            trade_price=8.0,
            bid=7.8,
            ask=8.0,
            size=300,
            volume=3_000,
            open_interest=5_000,
            implied_volatility=1.25,
            delta=0.5,
        )
    ]

    analysis = analyze_option_flow(
        trades,
        underlying=_underlying(),
        regime=_bull_regime(),
        event_risk=True,
    )

    assert "IV CHASE RISK" in analysis.final_signal or any("IV" in warning for warning in analysis.warnings)
    assert analysis.no_trade_risk >= 35


def test_parse_flow_csv_accepts_common_aliases() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "spy",
                "contract": "SPY260619C00510000",
                "expiry": "2026-06-19",
                "call_put": "c",
                "price": "$3.10",
                "bid": "2.95",
                "ask": "3.10",
                "qty": "500",
                "vol": "5000",
                "oi": "12000",
                "iv": "24%",
            }
        ]
    )

    trades = parse_flow_csv(frame, default_ticker="SPY")

    assert len(trades) == 1
    assert trades[0].ticker == "SPY"
    assert trades[0].option_type == "CALL"
    assert trades[0].implied_volatility == 0.24
    assert trades[0].size == 500


def test_sample_flow_uses_selected_ticker() -> None:
    frame = _sample_flow_frame("/ES", 7400)
    trades = parse_flow_csv(frame, default_ticker="/ES")

    assert {trade.ticker for trade in trades} == {"/ES"}
    assert all("SPY" not in trade.option_symbol for trade in trades)


def test_filter_trades_for_ticker_removes_mismatched_rows() -> None:
    frame = pd.DataFrame(
        [
            {"ticker": "SPY", "call_put": "CALL", "price": 1.0},
            {"ticker": "/ES", "call_put": "CALL", "price": 1.0},
        ]
    )
    trades = parse_flow_csv(frame, default_ticker="/ES")

    filtered, skipped = _filter_trades_for_ticker(trades, "/ES")

    assert skipped == 1
    assert len(filtered) == 1
    assert filtered[0].ticker == "/ES"


def test_option_flow_repository_persists_events_and_signals(tmp_path) -> None:
    trades = [
        OptionFlowTrade(
            ticker="SPY",
            option_symbol="SPY260619C00510000",
            expiration=date(2026, 6, 19),
            strike=510,
            option_type="CALL",
            trade_price=3.1,
            bid=2.95,
            ask=3.1,
            size=500,
            volume=5_000,
            open_interest=12_000,
            implied_volatility=0.24,
        )
    ]
    analysis = analyze_option_flow(trades, underlying=_underlying(), regime=_bull_regime())
    repository = SQLiteOptionFlowRepository(tmp_path / "options_flow.db")

    signal_id = repository.save_analysis(analysis)
    latest = repository.latest_trades("SPY")

    assert signal_id > 0
    assert len(latest) == 1
    assert latest[0].option_symbol == "SPY260619C00510000"
