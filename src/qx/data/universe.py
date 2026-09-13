from pathlib import Path
from collections.abc import Callable
from datetime import datetime, timedelta
from io import StringIO
import re
import logging

import pandas as pd
import requests
from bs4 import BeautifulSoup
from qx.data.membership import membership_symbols, save_membership, validate_membership_change

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP100_URL = "https://en.wikipedia.org/wiki/S%26P_100"
DOW_JONES_URL = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
NASDAQ_100_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
RUSSELL_2000_IWM_CSV_URL = (
    "https://raw.githubusercontent.com/ikoniaris/Russell2000/master/russell_2000_components.csv"
)
RUSSELL_2000_IWM_HOLDINGS_URL = "https://stockanalysis.com/etf/iwm/holdings/"
UNIVERSE_CACHE_TTL = timedelta(hours=24)

UNIVERSE_OPTIONS = {
    "Dow Jones": "dow_jones",
    "NASDAQ 100": "nasdaq_100",
    "Russell 2000": "russell_2000",
    "S&P 100": "sp100",
    "S&P 500": "sp500",
}


class UniverseLoader:
    """Loads symbol universes with local cache fallback."""

    def __init__(self, cache_dir: Path = Path("data/cache")) -> None:
        self.cache_dir = cache_dir

    def load(self, universe: str) -> list[str]:
        normalized = _normalize_universe_name(universe)
        if normalized == "dow_jones":
            return self._load_cached("dow_jones", _fetch_dow_jones_symbols)
        if normalized == "nasdaq_100":
            return self._load_cached("nasdaq_100", _fetch_nasdaq_100_symbols)
        if normalized == "russell_2000":
            return self._load_cached("russell_2000", _fetch_russell_2000_symbols)
        if normalized == "sp100":
            return self._load_cached("sp100", _fetch_sp100_symbols)
        if normalized in {"sp500", "s&p 500", "s_and_p_500"}:
            return self._load_cached("sp500", _fetch_sp500_symbols)
        raise ValueError(f"Unsupported universe: {universe}")

    def load_sp500(self) -> list[str]:
        return self.load("sp500")

    def _load_cached(self, cache_name: str, fetcher: Callable[[], list[str]]) -> list[str]:
        cache_path = self.cache_dir / f"{cache_name}_symbols.csv"
        if cache_path.exists() and _is_fresh_cache(cache_path):
            return _read_cached_symbols(cache_path)
        try:
            symbols = fetcher()
            content = pd.DataFrame({"symbol": symbols}).to_csv(index=False).encode()
            membership_symbols(content)
            previous = _read_cached_symbols(cache_path) if cache_path.exists() else []
            validate_membership_change(cache_name, symbols, previous)
        except (requests.RequestException, ValueError) as error:
            logging.getLogger(__name__).warning("Universe %s refresh rejected (%s); retaining cache if valid",
                                              cache_name, type(error).__name__)
            if not cache_path.exists():
                raise
            return _read_cached_symbols(cache_path)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        sources = {"sp500": SP500_URL, "sp100": SP100_URL, "nasdaq_100": NASDAQ_100_URL,
                   "dow_jones": DOW_JONES_URL, "russell_2000": "Legacy mixed sources; may contain ETF proxy holdings"}
        save_membership(cache_path, content,
                        sources.get(cache_name, "unknown"))
        return symbols


def _normalize_universe_name(universe: str) -> str:
    normalized = universe.strip().lower().replace("&", "and").replace(" ", "_").replace("-", "_")
    aliases = {
        "dow_jones": "dow_jones",
        "djia": "dow_jones",
        "nasdaq_100": "nasdaq_100",
        "ndx": "nasdaq_100",
        "russell_2000": "russell_2000",
        "iwm": "russell_2000",
        "sandp_100": "sp100",
        "s_and_p_100": "sp100",
        "sp100": "sp100",
        "sandp_500": "sp500",
        "s_and_p_500": "sp500",
        "sp500": "sp500",
    }
    return aliases.get(normalized, normalized)


def _fetch_sp500_symbols() -> list[str]:
    response = _get(SP500_URL)
    return parse_sp500_symbols(response.text)


def _fetch_sp100_symbols() -> list[str]:
    response = _get(SP100_URL)
    return parse_wikipedia_symbols(
        response.text,
        table_match="wikitable",
        symbol_column=0,
        minimum_count=90,
    )


def _fetch_dow_jones_symbols() -> list[str]:
    response = _get(DOW_JONES_URL)
    return parse_wikipedia_symbols(
        response.text,
        table_match="wikitable",
        symbol_column=1,
        minimum_count=30,
    )


def _fetch_nasdaq_100_symbols() -> list[str]:
    response = _get(NASDAQ_100_URL)
    return parse_wikipedia_symbols(
        response.text,
        table_match="wikitable",
        symbol_column=0,
        minimum_count=90,
    )


def _fetch_russell_2000_symbols() -> list[str]:
    try:
        response = _get(RUSSELL_2000_IWM_HOLDINGS_URL)
        return parse_stockanalysis_holdings_symbols(response.text, minimum_count=1000)
    except (ValueError, requests.RequestException):
        pass

    response = _get(RUSSELL_2000_IWM_CSV_URL)
    frame = pd.read_csv(StringIO(response.text))
    symbol_column = _find_symbol_column(frame)
    symbols = [_normalize_symbol(symbol) for symbol in frame[symbol_column].dropna().tolist()]
    return [symbol for symbol in symbols if _is_supported_symbol(symbol)]


def parse_sp500_symbols(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise ValueError("Could not find S&P 500 constituents table")

    symbols: list[str] = []
    rows = table.find_all("tr")
    for row in rows[1:]:
        columns = row.find_all("td")
        if not columns:
            continue
        symbol = columns[0].get_text(strip=True).replace(".", "-").upper()
        if symbol:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("No S&P 500 symbols found")
    return symbols


def parse_wikipedia_symbols(
    html: str,
    table_match: str,
    symbol_column: int,
    minimum_count: int = 25,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        class_attr = table.get("class")
        classes = class_attr if isinstance(class_attr, list) else [class_attr]
        if table_match not in classes:
            continue
        symbols: list[str] = []
        rows = table.find_all("tr")
        symbol_index = symbol_column
        headers = [header.get_text(" ", strip=True).lower() for header in rows[0].find_all(["th", "td"])] if rows else []
        for index, header in enumerate(headers):
            if header in {"symbol", "ticker", "ticker symbol", "company ticker"}:
                symbol_index = index
                break
        for row in rows[1:]:
            columns = row.find_all("td")
            if len(columns) <= symbol_index:
                continue
            symbol = _normalize_symbol(columns[symbol_index].get_text(" ", strip=True))
            if _is_supported_symbol(symbol):
                symbols.append(symbol)
        if len(symbols) >= minimum_count:
            return symbols
    raise ValueError("Could not parse symbols from Wikipedia table")


def parse_stockanalysis_holdings_symbols(html: str, minimum_count: int = 25) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    symbols: list[str] = []
    seen: set[str] = set()
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            columns = row.find_all("td")
            if len(columns) < 2:
                continue
            symbol = _normalize_symbol(columns[1].get_text(strip=True))
            if _is_supported_symbol(symbol) and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
        if len(symbols) >= minimum_count:
            return symbols
    raise ValueError("Could not parse holdings symbols")


def _normalize_symbol(symbol: object) -> str:
    return str(symbol).strip().lstrip("$").replace(".", "-").replace("/", "-").upper()


def _is_supported_symbol(symbol: str) -> bool:
    if symbol in {"", "CASH"}:
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9-]{0,9}", symbol))


def _find_symbol_column(frame: pd.DataFrame) -> str:
    for candidate in ("Ticker", "ticker", "Symbol", "symbol"):
        if candidate in frame.columns:
            return candidate
    return str(frame.columns[0])


def _get(url: str) -> requests.Response:
    response = requests.get(
        url,
        headers={"User-Agent": "SCANNER/0.1 local research app"},
        timeout=30,
    )
    response.raise_for_status()
    return response


def _read_cached_symbols(path: Path) -> list[str]:
    return membership_symbols(path.read_bytes())


def _is_fresh_cache(path: Path) -> bool:
    modified = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - modified <= UNIVERSE_CACHE_TTL
