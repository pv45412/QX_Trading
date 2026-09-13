from pathlib import Path

import pandas as pd

from qx.data.metadata import SymbolMetadata, SymbolMetadataStore, parse_sp500_metadata


def test_parse_sp500_metadata_from_constituents_table() -> None:
    html = """
    <table id="constituents">
      <tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>
      <tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td></tr>
      <tr><td>AAPL</td><td>Apple</td><td>Information Technology</td><td>Technology Hardware</td></tr>
    </table>
    """

    metadata = parse_sp500_metadata(html)

    assert metadata[0].symbol == "BRK-B"
    assert metadata[1].sector == "Information Technology"


def test_symbol_metadata_store_reads_cache_and_falls_back(tmp_path: Path) -> None:
    cache_path = tmp_path / "metadata.csv"
    pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "name": "Apple",
                "sector": "Information Technology",
                "industry": "Technology Hardware",
            }
        ]
    ).to_csv(cache_path, index=False)

    store = SymbolMetadataStore(cache_path)

    assert store.get("AAPL").sector == "Information Technology"
    assert store.get("MSFT").sector == "Unknown"


def test_symbol_metadata_store_enriches_missing_profiles(tmp_path: Path, monkeypatch) -> None:
    cache_path = tmp_path / "metadata.csv"
    pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "name": "Apple",
                "sector": "Information Technology",
                "industry": "Technology Hardware",
            }
        ]
    ).to_csv(cache_path, index=False)

    def fake_fetch(symbol: str) -> SymbolMetadata:
        return SymbolMetadata(symbol=symbol, name="Dycom", sector="Industrials", industry="Engineering")

    monkeypatch.setattr("qx.data.metadata.fetch_yfinance_metadata", fake_fetch)
    store = SymbolMetadataStore(cache_path)

    assert store.enrich_yfinance(["DY"], max_symbols=5) == 1
    assert store.get("DY").sector == "Industrials"
    assert store.get("AAPL").sector == "Information Technology"


def test_symbol_metadata_store_enriches_incomplete_cached_profiles(tmp_path: Path, monkeypatch) -> None:
    cache_path = tmp_path / "metadata.csv"
    pd.DataFrame(
        [
            {
                "symbol": "DY",
                "name": "Dycom",
                "sector": "Unknown",
                "industry": "Unknown",
            }
        ]
    ).to_csv(cache_path, index=False)

    def fake_fetch(symbol: str) -> SymbolMetadata:
        return SymbolMetadata(symbol=symbol, name="Dycom", sector="Industrials", industry="Engineering")

    monkeypatch.setattr("qx.data.metadata.fetch_yfinance_metadata", fake_fetch)
    store = SymbolMetadataStore(cache_path)

    assert store.enrich_yfinance(["DY"], max_symbols=5) == 1
    assert store.get("DY").sector == "Industrials"
    assert store.get("DY").industry == "Engineering"


def test_yfinance_etf_metadata_uses_fund_labels(monkeypatch) -> None:
    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def get_info(self) -> dict[str, object]:
            return {
                "longName": "Global X Artificial Intelligence & Technology ETF",
                "quoteType": "ETF",
                "category": "Technology",
            }

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)

    from qx.data.metadata import fetch_yfinance_metadata

    metadata = fetch_yfinance_metadata("AIQ")

    assert metadata.name == "Global X Artificial Intelligence & Technology ETF"
    assert metadata.sector == "ETF"
    assert metadata.industry == "Technology"
