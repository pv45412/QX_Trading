from datetime import date, timedelta

import pandas as pd

from qx.liquidity.engine import (
    build_liquidity_map,
    generate_tos_liquidity_study,
    liquidity_levels_frame,
    normalize_data_symbol,
    option_walls_frame,
)
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.ui.tradingview import build_lightweight_chart_html
from qx.options.chains import OptionContract
from qx.ui.pages.liquidity_map import _latest_bar_age_days, _latest_bar_label, _quote_price_text
from qx.ui.pages.liquidity_map import CHART_INTERVAL_OPTIONS
from qx.ui.defaults import default_market_data_provider


class StaticProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.requests: list[str] = []

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        self.requests.append(request.symbol)
        return self.frame.copy()

    def get_intraday_bars(self, request: IntradayBarDataRequest) -> pd.DataFrame:
        self.requests.append(f"{request.symbol}:{request.interval_minutes}m")
        return self.frame.copy()


class StaticOptionsProvider:
    def get_calls(self, symbol: str) -> list[OptionContract]:
        expiration = date.today() + timedelta(days=45)
        return [
            _contract(symbol, expiration, 110.0, "call", open_interest=10_000, volume=900),
            _contract(symbol, expiration, 115.0, "call", open_interest=4_000, volume=200),
        ]

    def get_puts(self, symbol: str) -> list[OptionContract]:
        expiration = date.today() + timedelta(days=45)
        return [
            _contract(symbol, expiration, 95.0, "put", open_interest=12_000, volume=1_100),
            _contract(symbol, expiration, 90.0, "put", open_interest=2_000, volume=100),
        ]


def test_liquidity_map_builds_price_levels_and_option_walls() -> None:
    provider = StaticProvider(_bars())

    snapshot = build_liquidity_map("SPY", provider, options_provider=StaticOptionsProvider())

    assert snapshot.symbol == "SPY"
    assert snapshot.data_symbol == "SPY"
    assert snapshot.asset_type == "ETF"
    assert snapshot.current_price > 0
    assert snapshot.nearest_support is not None
    assert snapshot.nearest_resistance is not None
    assert snapshot.top_call_wall is not None
    assert snapshot.top_put_wall is not None
    assert any(level.source == "options" for level in snapshot.levels)
    level_frame = liquidity_levels_frame(snapshot.levels)
    wall_frame = option_walls_frame(snapshot.option_walls)
    assert {"price", "label", "side", "score"}.issubset(level_frame.columns)
    assert {"strike", "side", "open_interest", "score"}.issubset(wall_frame.columns)


def test_liquidity_map_normalizes_futures_and_skips_option_walls() -> None:
    provider = StaticProvider(_bars(start=5000, step=3))

    snapshot = build_liquidity_map("/ES", provider, options_provider=StaticOptionsProvider())

    assert normalize_data_symbol("/ES") == "ES=F"
    assert provider.requests == ["ES=F"]
    assert snapshot.asset_type == "Future"
    assert snapshot.option_walls == []
    assert snapshot.diagnostics


def test_tos_export_contains_level_plots() -> None:
    snapshot = build_liquidity_map("SPY", StaticProvider(_bars()))

    script = generate_tos_liquidity_study(snapshot)

    assert "declare upper;" in script
    assert "plot QX_Level_1" in script
    assert "QX Liquidity" in script


def test_liquidity_latest_bar_label_uses_last_index_date() -> None:
    bars = _bars(rows=3)

    assert _latest_bar_label(bars) == "Jan 05, 2026"


def test_liquidity_latest_bar_age_accepts_timezone_aware_index() -> None:
    bars = _bars(rows=3)
    bars.index = pd.date_range("2026-01-05 09:30", periods=3, freq="5min", tz="America/New_York")

    assert _latest_bar_age_days(bars) is not None


def test_quote_price_text_falls_back_to_bar_close() -> None:
    assert _quote_price_text(None, 7400.5) == "7400.50"


def test_liquidity_map_defaults_to_intraday_day_trading_view() -> None:
    assert CHART_INTERVAL_OPTIONS[0] == "5m"


def test_ui_market_data_default_prefers_schwab() -> None:
    assert default_market_data_provider() == "schwab"


def test_lightweight_chart_uses_timestamp_for_intraday() -> None:
    bars = _bars(rows=3)
    bars.index = pd.date_range("2026-01-05 09:30", periods=3, freq="5min")

    html = build_lightweight_chart_html(bars, title="Test", interval="5m")

    assert "timeVisible: true" in html
    assert '"time": "2026-01-05"' not in html


def _contract(
    symbol: str,
    expiration: date,
    strike: float,
    option_type: str,
    *,
    open_interest: int,
    volume: int,
) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        expiration=expiration,
        contract_symbol=f"{symbol}{strike}",
        strike=strike,
        option_type=option_type,
        bid=1.0,
        ask=1.2,
        last_price=1.1,
        volume=volume,
        open_interest=open_interest,
        implied_volatility=0.25,
        dte=(expiration - date.today()).days,
    )


def _bars(start: float = 100.0, step: float = 0.1, rows: int = 90) -> pd.DataFrame:
    index = pd.bdate_range("2026-01-01", periods=rows)
    close = pd.Series([start + index_num * step for index_num in range(rows)], index=index)
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=index,
    )
