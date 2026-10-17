"""Scratch: is the FULL constituent list reachable, or only the top 25?"""
import re

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

html = requests.get("https://stockanalysis.com/etf/xlk/holdings/", headers=HEADERS, timeout=30).text

print("== what does the page claim? ==")
for pattern in (r"(\d+)\s*Holdings", r"Number of Holdings[^0-9]{0,40}(\d+)",
                r"Total Holdings[^0-9]{0,40}(\d+)", r'"holdingsCount"\s*:\s*(\d+)'):
    for m in re.finditer(pattern, html, re.IGNORECASE):
        print(f"   {pattern!r} -> {m.group(0)[:70]!r}")

print("\n== is there a data payload / API endpoint? ==")
for pattern in (r'/api/[a-zA-Z0-9/_.\-]*', r'__sveltekit', r'data-sveltekit',
                r'\.json', r'svelte-\w+'):
    found = sorted(set(re.findall(pattern, html)))[:8]
    if found:
        print(f"   {pattern!r} -> {found}")

print("\n== how are rows encoded? first 700 chars of a holding-shaped region ==")
idx = html.find("NVDA")
print(repr(html[max(0, idx - 400):idx + 300])[:900])

print("\n== do other pages show more rows (pagination)? ==")
for path in ("https://stockanalysis.com/etf/xlk/holdings/?p=2",
             "https://stockanalysis.com/etf/xlk/holdings/2/",
             "https://stockanalysis.com/etf/xlk/"):
    try:
        r = requests.get(path, headers=HEADERS, timeout=25)
        count = len(re.findall(r'"(?:symbol|ticker)"\s*:\s*"([A-Z][A-Z0-9.\-]{0,6})"', r.text))
        claim = re.search(r"(\d+)\s*Holdings", r.text, re.IGNORECASE)
        print(f"   HTTP {r.status_code} {path}  json_syms={count}  claim={claim.group(0) if claim else '-'}")
    except Exception as exc:
        print(f"   FAIL {path} {exc}")
