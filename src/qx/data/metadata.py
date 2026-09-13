from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from qx.data.universe import SP500_URL, _get


@dataclass(frozen=True)
class SymbolMetadata:
    symbol: str
    name: str = "Unknown"
    sector: str = "Unknown"
    industry: str = "Unknown"


class SymbolMetadataStore:
    """Cache-first lookup for symbol sector and industry metadata."""

    def __init__(self, cache_path: Path = Path("data/cache/symbol_metadata.csv")) -> None:
        self.cache_path = cache_path
        self._metadata: dict[str, SymbolMetadata] | None = None

    def get(self, symbol: str) -> SymbolMetadata:
        metadata = self._load()
        normalized = symbol.strip().upper()
        return metadata.get(normalized, SymbolMetadata(symbol=normalized))

    def enrich_yfinance(self, symbols: list[str], *, max_symbols: int = 25) -> int:
        missing: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized = symbol.strip().upper()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            if _metadata_incomplete(self.get(normalized)):
                missing.append(normalized)

        if not missing:
            return 0

        enriched: list[SymbolMetadata] = []
        for symbol in missing[:max_symbols]:
            profile = fetch_yfinance_metadata(symbol)
            if profile.name != "Unknown" or profile.sector != "Unknown" or profile.industry != "Unknown":
                enriched.append(profile)

        if not enriched:
            return 0

        current = self._load().copy()
        for item in enriched:
            current[item.symbol] = item
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([item.__dict__ for item in sorted(current.values(), key=lambda value: value.symbol)]).to_csv(
            self.cache_path,
            index=False,
        )
        self._metadata = current
        return len(enriched)

    def refresh_sp500(self) -> int:
        metadata = fetch_sp500_metadata()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([item.__dict__ for item in metadata]).to_csv(self.cache_path, index=False)
        self._metadata = {item.symbol: item for item in metadata}
        return len(metadata)

    def _load(self) -> dict[str, SymbolMetadata]:
        if self._metadata is not None:
            return self._metadata
        if not self.cache_path.exists():
            self._metadata = {}
            return self._metadata

        frame = pd.read_csv(self.cache_path).fillna("Unknown")
        metadata: dict[str, SymbolMetadata] = {}
        for row in frame.to_dict(orient="records"):
            symbol = str(row.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            metadata[symbol] = SymbolMetadata(
                symbol=symbol,
                name=str(row.get("name", "Unknown")),
                sector=str(row.get("sector", "Unknown")),
                industry=str(row.get("industry", "Unknown")),
            )
        self._metadata = metadata
        return metadata


def fetch_sp500_metadata() -> list[SymbolMetadata]:
    response = _get(SP500_URL)
    return parse_sp500_metadata(response.text)


def _metadata_incomplete(metadata: SymbolMetadata) -> bool:
    return any(
        value.strip().lower() in {"", "unknown", "nan"}
        for value in (metadata.name, metadata.sector, metadata.industry)
    )


def fetch_yfinance_metadata(symbol: str) -> SymbolMetadata:
    import yfinance as yf  # type: ignore[import-untyped]

    normalized = symbol.strip().upper()
    try:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            info = dict(yf.Ticker(normalized).get_info() or {})
    except Exception:
        return SymbolMetadata(symbol=normalized)

    quote_type = str(info.get("quoteType") or "").upper()
    sector = str(info.get("sector") or "Unknown")
    industry = str(info.get("industry") or "Unknown")
    if quote_type in {"ETF", "MUTUALFUND"}:
        sector = "ETF"
        industry = str(info.get("category") or info.get("fundFamily") or "Fund")

    return SymbolMetadata(
        symbol=normalized,
        name=str(info.get("longName") or info.get("shortName") or "Unknown"),
        sector=sector,
        industry=industry,
    )


def parse_sp500_metadata(html: str) -> list[SymbolMetadata]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise ValueError("Could not find S&P 500 constituents table")

    rows = table.find_all("tr")
    metadata: list[SymbolMetadata] = []
    for row in rows[1:]:
        columns = row.find_all("td")
        if len(columns) < 4:
            continue
        symbol = columns[0].get_text(strip=True).replace(".", "-").upper()
        name = columns[1].get_text(strip=True)
        sector = columns[2].get_text(strip=True)
        industry = columns[3].get_text(strip=True)
        if symbol:
            metadata.append(
                SymbolMetadata(
                    symbol=symbol,
                    name=name or "Unknown",
                    sector=sector or "Unknown",
                    industry=industry or "Unknown",
                )
            )
    if not metadata:
        raise ValueError("No S&P 500 metadata found")
    return metadata


def safe_refresh_sp500_metadata(store: SymbolMetadataStore) -> tuple[int, str | None]:
    try:
        return store.refresh_sp500(), None
    except requests.RequestException as exc:
        return 0, str(exc)
