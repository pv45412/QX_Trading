from qx.market.ticker_service import fetch_ticker_quote, fetch_all_watchlist_quotes, fetch_terminal_detail, TickerQuote


def test_fetch_ticker_quote():
    q = fetch_ticker_quote("AAPL")
    assert isinstance(q, TickerQuote)
    assert q.symbol == "AAPL"
    assert q.price >= 0


def test_fetch_all_watchlist_quotes():
    quotes = fetch_all_watchlist_quotes()
    assert len(quotes) >= 7
    symbols = [item["symbol"] for item in quotes]
    assert "SPX" in symbols
    assert "AAPL" in symbols
    assert "NVDA" in symbols


def test_fetch_terminal_detail():
    detail = fetch_terminal_detail("NVDA")
    assert detail["symbol"] == "NVDA"
    assert detail["price"] >= 0
    assert isinstance(detail["ai_signals"], list)
    assert len(detail["ai_signals"]) == 0
    assert len(detail["level2_asks"]) == 3
    assert len(detail["level2_bids"]) == 3
    assert len(detail["tape_prints"]) == 5
