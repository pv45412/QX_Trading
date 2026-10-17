"""Scratch: can stockanalysis.com actually give us full ETF constituents?"""
import re
import sys

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

sys.path.insert(0, r"C:\Project\2026\src")
from qx.data.universe import parse_stockanalysis_holdings_symbols  # noqa: E402

for symbol in ("SMH", "XLK", "XLE", "XLV", "XLF"):
    url = f"https://stockanalysis.com/etf/{symbol.lower()}/holdings/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        html = response.text
        print(f"\n=== {symbol} === HTTP {response.status_code} bytes={len(html)}")

        # The repo's existing parser is the first thing to try.
        try:
            symbols = parse_stockanalysis_holdings_symbols(html, minimum_count=5)
            print(f"   repo parser OK -> {len(symbols)} symbols: {symbols[:12]}")
        except Exception as exc:
            print(f"   repo parser FAILED: {type(exc).__name__}: {str(exc)[:140]}")

        # Raw inspection: how are holdings embedded?
        tables = re.findall(r"<table[\s\S]{0,4000}?</table>", html)
        print(f"   <table> blocks: {len(tables)}")
        for match in re.finditer(r'"symbol":"([A-Z][A-Z0-9.\-]{0,6})"', html):
            pass
        json_syms = re.findall(r'"symbol"\s*:\s*"([A-Z][A-Z0-9.\-]{0,6})"', html)
        print(f"   JSON-embedded symbols: {len(set(json_syms))} {sorted(set(json_syms))[:12]}")

        # Look for a weight column and a holdings-count indicator.
        for pattern in (r"(\d+)\s*holdings", r"Number of Holdings[^0-9]{0,40}(\d+)",
                        r'"weight"\s*:\s*([\d.]+)', r"assetsUnderManagement"):
            found = re.search(pattern, html, re.IGNORECASE)
            if found:
                print(f"   matched {pattern!r}: {found.group(0)[:60]!r}")
    except Exception as exc:
        print(f"\n=== {symbol} === FAILED {type(exc).__name__}: {exc}")
