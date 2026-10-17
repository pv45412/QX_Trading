"""Scratch: close out the $SPX zero-open-interest question.

Observations to explain:
  SPY  320 contracts, 241 with OI > 0   (healthy)
  $SPX 160 contracts,   0 with OI > 0   (all zero)
  $NDX 320 contracts,   1 with OI > 0   (almost all zero)

Hypotheses:
  H1 the strike window misses the money
  H2 the expiry selection picks no-OI series (SPXW weeklies vs SPX monthlies)
  H3 index chains genuinely report OI differently (e.g. only on monthlies)
  H4 a parameter is wrong (range / expMonth / strikeCount interaction)
"""
import os
import sys
import time
from collections import Counter

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402
from qx.brokers.schwab.client import SchwabApiClient  # noqa: E402
from qx.config.settings import get_settings  # noqa: E402

settings = get_settings()
client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
BASE = {"contractType": "ALL", "includeUnderlyingQuote": "true", "strategy": "SINGLE"}


def fetch(symbol, **extra):
    params = {**BASE, "symbol": symbol, **extra}
    return client.get("/marketdata/v1/chains", params=params)


def summarise(label, payload):
    calls = payload.get("callExpDateMap") or {}
    puts = payload.get("putExpDateMap") or {}
    total = oi_pos = 0
    oi_sum = 0.0
    expiries = []
    sample_symbols = []
    for mapping in (calls, puts):
        for expiry, strikes in mapping.items():
            expiries.append(expiry)
            for strike, contracts in strikes.items():
                for contract in contracts or []:
                    total += 1
                    oi = contract.get("openInterest") or 0
                    if oi > 0:
                        oi_pos += 1
                    oi_sum += oi
                    if len(sample_symbols) < 3:
                        sample_symbols.append(contract.get("symbol"))
    print(f"  {label}")
    print(f"     contracts={total:<6} with_OI>0={oi_pos:<5} total_OI={oi_sum:,.0f}")
    print(f"     expiries={sorted(set(expiries))[:5]}")
    print(f"     sample option symbols={sample_symbols}")
    return {"total": total, "oi_pos": oi_pos, "oi_sum": oi_sum,
            "expiries": sorted(set(expiries)), "underlying": payload.get("underlyingPrice")}


print("=" * 78)
print("A. Baseline: what the app currently requests (strikeCount=40)")
print("=" * 78)
for symbol in ("SPY", "$SPX", "$NDX"):
    try:
        summarise(f"{symbol} strikeCount=40", fetch(symbol, strikeCount=40))
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol}: {type(exc).__name__}: {str(exc)[:70]}")

print()
print("=" * 78)
print("B. H1 — does a wider strike window change anything?")
print("=" * 78)
for count in (5, 20, 40):
    try:
        summarise(f"$SPX strikeCount={count}", fetch("$SPX", strikeCount=count))
    except Exception as exc:  # noqa: BLE001
        print(f"  $SPX strikeCount={count}: {str(exc)[:60]}")

print()
print("=" * 78)
print("C. H2 — pin a SINGLE monthly expiry (third Friday) vs the near weeklies")
print("=" * 78)
for window in ({"fromDate": "2026-10-16", "toDate": "2026-10-17"},
               {"fromDate": "2026-11-20", "toDate": "2026-11-21"},
               {"fromDate": "2026-10-08", "toDate": "2026-10-09"}):
    try:
        summarise(f"$SPX {window}", fetch("$SPX", strikeCount=10, **window))
    except Exception as exc:  # noqa: BLE001
        print(f"  $SPX {window}: {str(exc)[:60]}")

print()
print("=" * 78)
print("D. H4 — range variants")
print("=" * 78)
for rng in ("ITM", "OTM", "NTM", "ALL"):
    try:
        summarise(f"$SPX range={rng}", fetch("$SPX", strikeCount=10, range=rng))
    except Exception as exc:  # noqa: BLE001
        print(f"  $SPX range={rng}: {str(exc)[:60]}")
