import pandas as pd
import pytest
from datetime import datetime, timezone
import pandas_market_calendars as mcal

from qx.market.regime import analyze_market_regime, market_regime_frame
from qx.models.market import BarDataRequest


class StaticProvider:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        return self.frames[request.symbol].copy()


def test_market_regime_detects_risk_on() -> None:
    provider = StaticProvider(
        {
            "SPY": _bars(100.0, 0.35),
            "QQQ": _bars(100.0, 0.50),
            "IWM": _bars(100.0, 0.25),
        }
    )

    result = analyze_market_regime(provider)
    frame = market_regime_frame(result)

    assert result.label == "Risk On"
    assert result.risk_level == "Low"
    assert result.spy_close > result.spy_sma50 > result.spy_sma200
    assert frame.iloc[0]["regime"] == "Risk On"


def test_market_regime_detects_risk_off() -> None:
    provider = StaticProvider(
        {
            "SPY": _bars(220.0, -0.35),
            "QQQ": _bars(220.0, -0.45),
            "IWM": _bars(220.0, -0.55),
        }
    )

    result = analyze_market_regime(provider)

    assert result.label == "Risk Off"
    assert result.risk_level == "High"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0.0, -1.0])
@pytest.mark.parametrize("position", [-1, -20])
def test_market_regime_rejects_invalid_spy_closes(value: float, position: int) -> None:
    bars = _bars(100.0, 0.35)
    bars.iloc[position, bars.columns.get_loc("close")] = value
    with pytest.raises(ValueError, match="finite and positive"):
        analyze_market_regime(StaticProvider({"SPY": bars}))


@pytest.mark.parametrize("order", ["duplicate", "reversed"])
def test_market_regime_rejects_invalid_spy_order(order: str) -> None:
    bars = _bars(100.0, 0.35)
    if order == "duplicate":
        bars.index = bars.index[:-1].append(bars.index[-2:-1])
    else:
        bars = bars.iloc[::-1]
    with pytest.raises(ValueError, match="unique ascending"):
        analyze_market_regime(StaticProvider({"SPY": bars}))


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


@pytest.mark.parametrize("mode", ["missing", "shifted", "short", "nan", "duplicate"])
def test_optional_benchmarks_are_unavailable_not_zero(mode: str) -> None:
    spy = _bars(100.0, 0.35)
    benchmark = _bars(100.0, 0.5)
    if mode == "shifted":
        benchmark.index += pd.Timedelta(days=1)
    elif mode == "short":
        benchmark = benchmark.tail(20)
    elif mode == "nan":
        benchmark.iloc[-1, benchmark.columns.get_loc("close")] = float("nan")
    elif mode == "duplicate":
        benchmark.index = benchmark.index[:-1].append(benchmark.index[-2:-1])
    frames = {"SPY": spy} if mode == "missing" else {"SPY": spy, "QQQ": benchmark, "IWM": benchmark}
    result = analyze_market_regime(StaticProvider(frames))
    assert result.qqq_return_20d is None
    assert result.iwm_return_20d is None
    assert result.label != "Risk On"
    assert sum("confirmation unavailable" in note for note in result.notes) == 2


def test_completed_equity_regime_ignores_partial_and_rejects_stale() -> None:
    spy = _bars(100.0, 0.35)
    sessions = mcal.get_calendar("NYSE").schedule(start_date="2025-01-01", end_date="2026-09-09").index
    spy.index = sessions[-len(spy):]
    now = datetime(2026, 9, 10, 14, tzinfo=timezone.utc)
    partial = spy.tail(1).copy()
    partial.index = pd.DatetimeIndex(["2026-09-10"])
    partial["close"] *= 2
    baseline = analyze_market_regime(StaticProvider({"SPY": spy}), as_of=now)
    result = analyze_market_regime(StaticProvider({"SPY": pd.concat([spy, partial])}), as_of=now)
    assert result == baseline
    with pytest.raises(ValueError, match="stale"):
        analyze_market_regime(StaticProvider({"SPY": spy.iloc[:-1]}), as_of=now)
