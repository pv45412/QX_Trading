from qx.brokers.schwab.options import SchwabOptionsChainProvider


class FakeClient:
    def __init__(self) -> None:
        self.params: dict[str, object] | None = None

    def get(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, object]:
        assert path == "/marketdata/v1/chains"
        self.params = params
        return {
            "callExpDateMap": {
                "2026-01-16:60": {
                    "100.0": [
                        {
                            "symbol": "TEST_011626C100",
                            "strikePrice": 100.0,
                            "bid": 4.9,
                            "ask": 5.1,
                            "last": 5.0,
                            "totalVolume": 250,
                            "openInterest": 500,
                            "volatility": 35.0,
                        }
                    ]
                }
            }
        }


def test_schwab_options_chain_provider_parses_call_map() -> None:
    provider = SchwabOptionsChainProvider(FakeClient())  # type: ignore[arg-type]

    contracts = provider.get_calls("TEST")

    assert len(contracts) == 1
    assert contracts[0].contract_symbol == "TEST_011626C100"
    assert contracts[0].dte == 60
    assert contracts[0].open_interest == 500


def test_schwab_options_chain_provider_uses_index_chain_symbol() -> None:
    client = FakeClient()
    provider = SchwabOptionsChainProvider(client)  # type: ignore[arg-type]

    contracts = provider.get_calls("SPX")

    assert client.params is not None
    assert client.params["symbol"] == "$SPX"
    assert contracts[0].symbol == "SPX"
