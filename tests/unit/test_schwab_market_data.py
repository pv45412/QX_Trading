from datetime import UTC, datetime, timedelta

from qx.brokers.schwab.market_data import SchwabMarketDataProvider
from qx.models.market import BarDataRequest, IntradayBarDataRequest


class FakeClient:
    def get(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, object]:
        assert path == "/marketdata/v1/pricehistory"
        return {
            "candles": [
                {
                    "datetime": 1_735_689_600_000,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 1_000_000,
                }
            ]
        }


def test_schwab_market_data_provider_normalizes_candles() -> None:
    provider = SchwabMarketDataProvider(FakeClient())  # type: ignore[arg-type]

    bars = provider.get_daily_bars(BarDataRequest(symbol="SPY", period="1y"))

    assert len(bars) == 1
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]


def test_intraday_request_uses_bounded_window_for_current_session() -> None:
    calls = []
    now = datetime(2026, 9, 17, 17, 5, tzinfo=UTC)

    class CapturingClient(FakeClient):
        def get(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, object]:
            calls.append(params)
            return super().get(path, params=params)

    provider = SchwabMarketDataProvider(  # type: ignore[arg-type]
        CapturingClient(),
        now_provider=lambda: now,
    )

    provider.get_intraday_bars(IntradayBarDataRequest(symbol="SPY", period="5d"))

    assert calls[0]["periodType"] == "day"
    assert calls[0]["period"] == 5
    assert calls[0]["endDate"] == int(now.timestamp() * 1000)
    assert calls[0]["startDate"] == int((now - timedelta(days=9)).timestamp() * 1000)
    assert calls[0]["startDate"] < calls[0]["endDate"]
