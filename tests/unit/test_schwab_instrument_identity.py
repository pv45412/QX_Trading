from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from qx.brokers.schwab.market_data import SchwabMarketDataProvider
from qx.brokers.schwab.quotes import SchwabQuoteProvider, _extract_symbol_payload
from qx.brokers.schwab.symbols import schwab_equity_symbol, schwab_market_data_symbol
from qx.models.market import BarDataRequest, IntradayBarDataRequest


@pytest.mark.parametrize("symbol,expected", [("BRK-B","BRK/B"),("BRK.B","BRK/B"),
    ("BF-B","BF/B"),("BF.A","BF/A"),("AAPL","AAPL"),("OTHER-B","OTHER-B"),("/ESU26","/ESU26")])
def test_only_known_equity_aliases_change(symbol, expected):
    assert schwab_equity_symbol(symbol) == expected


@pytest.mark.parametrize("symbol,expected", [("ES=F", "/ES"), ("NQ=F", "/NQ"),
    ("/ESU26", "/ESU26"), ("BRK-B", "BRK/B"), ("SPX", "$SPX")])
def test_market_data_symbol_preserves_local_identity_and_maps_futures_roots(symbol, expected):
    assert schwab_market_data_symbol(symbol) == expected


@pytest.mark.parametrize("intraday", [False, True])
def test_history_uses_broker_alias_without_changing_request(intraday):
    requests = []
    def get(path, *, params):
        requests.append(params)
        return {"candles":[{"datetime":1789016400000,"open":100,"high":101,"low":99,"close":100,"volume":1000}]}
    provider = SchwabMarketDataProvider(SimpleNamespace(get=get))
    request = IntradayBarDataRequest(symbol="BRK-B", period="5d") if intraday else BarDataRequest(symbol="BRK-B", period="1y")
    result = provider.get_intraday_bars(request) if intraday else provider.get_daily_bars(request)
    assert requests[0]["symbol"] == "BRK/B"
    assert request.symbol == "BRK-B"
    assert len(result) == 1


def test_intraday_history_uses_schwab_futures_root_without_mutating_request():
    requests = []

    def get(path, *, params):
        requests.append(params)
        return {"candles":[{"datetime":1789016400000,"open":100,"high":101,"low":99,"close":100,"volume":1000}]}

    request = IntradayBarDataRequest(symbol="ES=F", period="5d")
    result = SchwabMarketDataProvider(SimpleNamespace(get=get)).get_intraday_bars(request)
    assert requests[0]["symbol"] == "/ES"
    assert request.symbol == "ES=F"
    assert len(result) == 1


def test_spx_history_uses_schwab_index_symbol_without_mutating_request():
    requests = []

    def get(path, *, params):
        requests.append(params)
        return {"candles":[{"datetime":1789016400000,"open":7000,"high":7010,"low":6990,"close":7005,"volume":1000}]}

    request = IntradayBarDataRequest(symbol="SPX", period="5d")
    result = SchwabMarketDataProvider(SimpleNamespace(get=get)).get_intraday_bars(request)
    assert requests[0]["symbol"] == "$SPX"
    assert request.symbol == "SPX"
    assert len(result) == 1


def test_quote_preserves_explicit_contract_and_market_timestamps():
    payload = {"/ESU26":{"symbol":"/ESU26","assetMainType":"FUTURE","realtime":True,
        "quote":{"lastPrice":100,"quoteTime":1789151392491,"tradeTime":1789151391618},
        "reference":{"futureExpirationDate":1789704000000}}}
    provider = SchwabQuoteProvider(SimpleNamespace(get=lambda *args, **kwargs:payload))
    quote = provider.get_quote("ES=F")
    assert quote.symbol == "ES=F" and quote.resolved_symbol == "/ESU26"
    assert quote.realtime is True and quote.asset_type == "FUTURE"
    assert quote.expiration == datetime.fromtimestamp(1789704000, timezone.utc)
    assert quote.trade_timestamp < quote.timestamp


@pytest.mark.parametrize("payload", [
    {"SPY":{"quote":{"lastPrice":100}}},
    {"/NQU26":{"quote":{"lastPrice":100}}},
    {"/ESU26":{"symbol":"/NQU26"}},
    {"/ESU26":{},"/ESZ26":{}},
    {"/ES":{"symbol":"/NQU26"}},
])
def test_unrelated_ambiguous_or_mismatched_quotes_are_not_substituted(payload):
    with pytest.raises(ValueError, match="identity"):
        _extract_symbol_payload(payload, "/ES")


@pytest.mark.parametrize("bad", [True,float("inf"),float("nan")])
def test_invalid_quote_price_stays_unknown(bad):
    provider = SchwabQuoteProvider(SimpleNamespace(get=lambda *args, **kwargs:{"SPY":{"quote":{"lastPrice":bad}}}))
    assert provider.get_quote("SPY").last is None
