from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qx.data.universe import (
    UNIVERSE_OPTIONS,
    UniverseLoader,
    _is_supported_symbol,
    _normalize_symbol,
    _fetch_nasdaq_100_symbols,
    parse_stockanalysis_holdings_symbols,
    parse_sp500_symbols,
    parse_wikipedia_symbols,
)


def test_nasdaq_fetch_uses_dedicated_constituent_page() -> None:
    symbols = [f"S{index}" for index in range(100)]
    html = '<table class="wikitable sortable"><tr><th>Company</th><th>Ticker</th></tr>'
    html += ''.join(f'<tr><td>Company {index}</td><td>{symbol}</td></tr>'
                    for index, symbol in enumerate(symbols)) + '</table>'
    with patch('qx.data.universe._get', return_value=SimpleNamespace(text=html)) as get:
        assert _fetch_nasdaq_100_symbols() == symbols
        get.assert_called_once_with('https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies')


def test_parse_sp500_symbols_from_constituents_table() -> None:
    html = """
    <table id="constituents">
      <tr><th>Symbol</th><th>Name</th></tr>
      <tr><td>BRK.B</td><td>Berkshire Hathaway</td></tr>
      <tr><td>AAPL</td><td>Apple</td></tr>
    </table>
    """

    assert parse_sp500_symbols(html) == ["BRK-B", "AAPL"]


def test_universe_options_include_requested_indices() -> None:
    assert UNIVERSE_OPTIONS == {
        "Dow Jones": "dow_jones",
        "NASDAQ 100": "nasdaq_100",
        "Russell 2000": "russell_2000",
        "S&P 100": "sp100",
        "S&P 500": "sp500",
    }


def test_parse_generic_wikipedia_symbols() -> None:
    html = """
    <table class="wikitable">
      <tr><th>Name</th><th>Symbol</th></tr>
      <tr><td>Apple</td><td>AAPL</td></tr>
      <tr><td>Microsoft</td><td>MSFT</td></tr>
      <tr><td>Nvidia</td><td>NVDA</td></tr>
      <tr><td>Amazon</td><td>AMZN</td></tr>
      <tr><td>Meta</td><td>META</td></tr>
      <tr><td>Alphabet</td><td>GOOGL</td></tr>
      <tr><td>Broadcom</td><td>AVGO</td></tr>
      <tr><td>Tesla</td><td>TSLA</td></tr>
      <tr><td>Costco</td><td>COST</td></tr>
      <tr><td>Netflix</td><td>NFLX</td></tr>
      <tr><td>Pepsi</td><td>PEP</td></tr>
      <tr><td>Adobe</td><td>ADBE</td></tr>
      <tr><td>Cisco</td><td>CSCO</td></tr>
      <tr><td>AMD</td><td>AMD</td></tr>
      <tr><td>Comcast</td><td>CMCSA</td></tr>
      <tr><td>Intel</td><td>INTC</td></tr>
      <tr><td>Intuit</td><td>INTU</td></tr>
      <tr><td>QCOM</td><td>QCOM</td></tr>
      <tr><td>TXN</td><td>TXN</td></tr>
      <tr><td>AMAT</td><td>AMAT</td></tr>
      <tr><td>BKNG</td><td>BKNG</td></tr>
      <tr><td>SBUX</td><td>SBUX</td></tr>
      <tr><td>ISRG</td><td>ISRG</td></tr>
      <tr><td>ADP</td><td>ADP</td></tr>
      <tr><td>VRTX</td><td>VRTX</td></tr>
    </table>
    """

    assert parse_wikipedia_symbols(html, table_match="wikitable", symbol_column=1)[:2] == [
        "AAPL",
        "MSFT",
    ]


def test_parse_stockanalysis_holdings_symbols() -> None:
    html = """
    <table>
      <tr><th>No.</th><th>Symbol</th><th>Name</th></tr>
      <tr><td>1</td><td>BE</td><td>Bloom Energy</td></tr>
      <tr><td>2</td><td>CRDO</td><td>Credo Technology</td></tr>
      <tr><td>3</td><td>BRK.B</td><td>Berkshire</td></tr>
      <tr><td>4</td><td>CASH</td><td>Cash</td></tr>
    </table>
    """

    assert parse_stockanalysis_holdings_symbols(html, minimum_count=3) == ["BE", "CRDO", "BRK-B"]


def test_normalize_symbol_removes_market_prefixes() -> None:
    assert _normalize_symbol("$BRK.B") == "BRK-B"
    assert _normalize_symbol(" abc ") == "ABC"


def test_supported_symbol_filter_rejects_non_tickers() -> None:
    assert _is_supported_symbol("AAPL")
    assert _is_supported_symbol("BRK-B")
    assert not _is_supported_symbol("CASH")
    assert not _is_supported_symbol("")
    assert not _is_supported_symbol("THIS-IS-NOT-A-TICKER")


def test_wikipedia_parser_accepts_multi_class_tables_and_symbol_headers() -> None:
    html = """
    <table class="wikitable sortable">
      <tr><th>Company</th><th>Ticker</th></tr>
      <tr><td>Apple</td><td>AAPL</td></tr>
      <tr><td>Microsoft</td><td>MSFT</td></tr>
    </table>
    """

    assert parse_wikipedia_symbols(html, table_match="wikitable", symbol_column=0, minimum_count=2) == [
        "AAPL",
        "MSFT",
    ]


def test_universe_loader_uses_stale_cache_when_parser_fails(tmp_path: Path) -> None:
    cache_path = tmp_path / "nasdaq_100_symbols.csv"
    cache_path.write_text("symbol\nAAPL\nMSFT\n", encoding="utf-8")

    loader = UniverseLoader(tmp_path)
    symbols = loader._load_cached("nasdaq_100", lambda: (_ for _ in ()).throw(ValueError("parser changed")))

    assert symbols == ["AAPL", "MSFT"]
