"""Scratch: how many rows does the holdings page REALLY contain, and with weights?"""
import re

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}


def rows_from_html(html):
    """Extract rows from the server-rendered holdings table."""
    out = []
    for tr in re.findall(r"<tr class=\"svelte-[^\"]*\">([\s\S]*?)</tr>", html):
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr)
        if len(cells) < 3:
            continue
        clean = [re.sub(r"<[^>]+>", "", c).replace("<!---->", "").strip() for c in cells]
        ticker = None
        for c in clean:
            if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,6}", c):
                ticker = c
                break
        if ticker:
            out.append(clean)
    return out


for symbol in ("XLK", "SMH", "XLE"):
    url = f"https://stockanalysis.com/etf/{symbol.lower()}/holdings/"
    html = requests.get(url, headers=HEADERS, timeout=30).text
    rows = rows_from_html(html)
    claims = sorted(set(re.findall(r"(\d+)\s*[Hh]oldings", html)))
    print(f"\n=== {symbol} ===")
    print(f"   page claims: {claims}")
    print(f"   rows parsed from table: {len(rows)}")
    print(f"   first 4 rows: {rows[:4]}")
    print(f"   last 2 rows : {rows[-2:]}")
    # Do the rows carry weights?
    weighted = [r for r in rows if any('%' in c for c in r)]
    print(f"   rows with a weight column: {len(weighted)}")
    # Total weight coverage of what we parsed.
    total = 0.0
    for r in rows:
        for c in r:
            if c.endswith('%'):
                try:
                    total += float(c.rstrip('%'))
                except ValueError:
                    pass
                break
    print(f"   summed weight of parsed rows: {total:.2f}%")
