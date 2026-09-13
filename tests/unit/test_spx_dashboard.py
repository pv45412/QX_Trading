import pandas as pd
import pytest

from qx.market.spx_dashboard import (
    build_spx_dashboard,
    decision_levels_frame,
    futures_timing_frame,
    trading_plan_frame,
)
from qx.models.market import BarDataRequest
from qx.data.quotes import QuoteSnapshot


class StaticProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.frames[request.symbol].copy()


class StaticQuoteProvider:
    provider_name = "schwab"

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        assert symbol == "ES=F"
        return QuoteSnapshot(symbol=symbol, provider=self.provider_name, last=7085.0)


def test_regime_and_levels_share_one_spy_read() -> None:
    class ChangingSpyProvider(StaticProvider):
        reads = 0

        def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
            if request.symbol == "SPY":
                self.reads += 1
                return _bars(100.0 * self.reads, 0.4)
            return super().get_daily_bars(request)

    provider = ChangingSpyProvider({})
    dashboard = build_spx_dashboard(provider)
    assert provider.reads == 1
    assert dashboard.regime.spy_close == dashboard.spy_close == dashboard.spy_levels.close


@pytest.mark.parametrize("missing", [False, True])
def test_futures_tiles_reuse_decision_level_history(missing: bool) -> None:
    class ChangingProvider(StaticProvider):
        def __init__(self) -> None:
            super().__init__({symbol: _bars(100.0, 0.4) for symbol in ["SPY", "QQQ", "IWM"]})
            self.reads: dict[str, int] = {}

        def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
            if request.symbol in {"ES=F", "NQ=F"}:
                count = self.reads.get(request.symbol, 0) + 1
                self.reads[request.symbol] = count
                if missing and count == 1:
                    raise ValueError("Unavailable")
                return _bars(5000.0 * count, 8.0)
            return super().get_daily_bars(request)

    provider = ChangingProvider()
    dashboard = build_spx_dashboard(provider)
    rows = {row.symbol: row for row in dashboard.futures_rows}
    assert provider.reads == {"ES=F": 1, "NQ=F": 1}
    assert rows["ES=F"].close == dashboard.es_levels.close == dashboard.es_close
    assert rows["NQ=F"].close == dashboard.nq_levels.close == dashboard.nq_close
    if missing:
        assert rows["ES=F"].close is None
        assert rows["NQ=F"].close is None


def test_spx_dashboard_builds_levels_and_bias() -> None:
    provider = StaticProvider(
        {
            "SPY": _bars(100.0, 0.40),
            "QQQ": _bars(100.0, 0.60),
            "IWM": _bars(100.0, 0.25),
            "ES=F": _bars(5000.0, 8.0),
            "NQ=F": _bars(18000.0, 35.0),
            "YM=F": _bars(39000.0, 20.0),
            "RTY=F": _bars(2100.0, 2.0),
            "ZN=F": _bars(110.0, 0.01),
            "ZB=F": _bars(120.0, 0.01),
            "DX-Y.NYB": _bars(104.0, -0.01),
            "CL=F": _bars(75.0, 0.02),
            "GC=F": _bars(2300.0, 1.0),
            "^VIX": _bars(18.0, -0.01),
        }
    )

    dashboard = build_spx_dashboard(provider, quote_provider=StaticQuoteProvider())

    assert dashboard.trend_bias in {"Bullish Breakout", "Bullish Above Support"}
    assert dashboard.spy_prior_high > 0
    assert dashboard.spy_week_high >= dashboard.spy_prior_high
    assert dashboard.spy_20d_high >= dashboard.spy_week_high
    assert dashboard.es_overnight_move is not None
    assert dashboard.nq_overnight_move is not None
    assert dashboard.nq_bias
    assert dashboard.risk_appetite
    assert dashboard.confirmation_notes
    assert len(dashboard.futures_rows) >= 9
    assert dashboard.vix_close is not None
    assert dashboard.decision_levels
    assert len(dashboard.decision_level_sets) == 3
    assert dashboard.spy_levels.location == "Inside Range - Upper Half"
    assert dashboard.es_levels.buyer_zone.startswith("S&P 500 Futures buyers")
    assert dashboard.nq_levels.seller_zone.startswith("Nasdaq 100 Futures sellers")
    level_frame = decision_levels_frame(dashboard.decision_level_sets)
    assert {"symbol", "prior_high", "prior_low", "location"}.issubset(level_frame.columns)
    assert dashboard.trading_plan.day_type
    assert dashboard.trading_plan.long_plan
    assert dashboard.trading_plan.short_plan
    assert len(dashboard.timing_rows) == 3
    assert dashboard.timing_rows[0].trigger_level is not None
    assert dashboard.timing_rows[0].invalidation_level is not None
    assert dashboard.timing_rows[0].priority > 0
    timing_frame = futures_timing_frame(dashboard.timing_rows)
    assert {"symbol", "timing_state", "trigger_level", "invalidation_level"}.issubset(timing_frame.columns)
    plan_frame = trading_plan_frame(dashboard.trading_plan)
    assert list(plan_frame.columns) == ["area", "plan"]
    assert "Long Plan" in set(plan_frame["area"])
    assert "Buyers" in dashboard.buyer_zone
    assert "Sellers" in dashboard.seller_zone
    assert "chop" in dashboard.chop_zone
    assert dashboard.action_plan
    assert dashboard.opening_gap.data_source == "schwab"
    assert dashboard.opening_gap.es_last == 7085.0
    assert dashboard.opening_gap.implied_spx_open is None
    assert dashboard.opening_gap.implied_gap_pct is None
    assert dashboard.opening_gap.implied_gap_points is None
    assert dashboard.opening_gap.gap_type == "Unavailable"


def _bars(start: float, step: float, rows: int = 260) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=rows)
    close = pd.Series([start + index_num * step for index_num in range(rows)], index=index)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=index,
    )
