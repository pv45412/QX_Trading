from qx.brokers.schwab.market_data import SchwabMarketDataProvider
from qx.models.market import BarDataRequest


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
