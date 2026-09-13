from qx.brokers.schwab.quotes import SchwabQuoteProvider


class FakeClient:
    def get(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, object]:
        assert path == "/marketdata/v1/quotes"
        assert params == {"symbols": "/ES"}
        return {
            "/ES": {
                "quote": {
                    "lastPrice": 5100.25,
                    "netPercentChange": 0.42,
                    "bidPrice": 5100.0,
                    "askPrice": 5100.5,
                    "totalVolume": 1000,
                }
            }
        }


def test_schwab_quote_provider_maps_yfinance_future_symbol_to_schwab_symbol() -> None:
    provider = SchwabQuoteProvider(FakeClient())  # type: ignore[arg-type]

    quote = provider.get_quote("ES=F")

    assert quote.symbol == "ES=F"
    assert quote.provider == "schwab"
    assert quote.last == 5100.25
    assert quote.change_pct == 0.0042
