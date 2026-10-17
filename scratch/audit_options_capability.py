"""Scratch: what options/futures capability actually works against live Schwab?"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.brokers.schwab.auth import SchwabTokenManager
from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.options import SchwabOptionsChainProvider
from qx.brokers.schwab.quotes import SchwabQuoteProvider
from qx.config.settings import get_settings

settings = get_settings()
client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)

print("== 1. underlying quotes (futures + index) ==")
quotes = SchwabQuoteProvider(client)
for symbol in ("SPY", "/ES", "/NQ", "$SPX", "SPX", "VIX"):
    try:
        q = quotes.get_quote(symbol)
        print(f"   {symbol:<6} last={q.last} realtime={q.realtime} type={q.asset_type} resolved={q.resolved_symbol}")
    except Exception as exc:
        print(f"   {symbol:<6} FAIL {type(exc).__name__}: {str(exc)[:110]}")

print("\n== 2. raw option chain (SPY) ==")
try:
    payload = client.get(
        "/marketdata/v1/chains",
        params={"symbol": "SPY", "contractType": "ALL", "strikeCount": 10,
                "includeUnderlyingQuote": "true", "strategy": "SINGLE"},
    )
    print("   chain status: OK")
    print("   top-level keys:", sorted(payload.keys())[:14])
    print("   status:", payload.get("status"), "| underlying last:", (payload.get("underlying") or {}).get("last"))
    for key in ("callExpDateMap", "putExpDateMap"):
        mapping = payload.get(key) or {}
        expiries = list(mapping.keys())[:3]
        print(f"   {key}: {len(mapping)} expiries, first={expiries}")
        if expiries:
            first = mapping[expiries[0]]
            strikes = list(first.keys())[:3]
            print(f"      strikes on {expiries[0]}: {strikes}")
            if strikes:
                contract = first[strikes[0]][0]
                interesting = ("symbol", "bid", "ask", "last", "mark", "totalVolume",
                               "openInterest", "volatility", "delta", "gamma", "theta", "vega", "strikePrice")
                print("      contract fields:",
                      {k: contract.get(k) for k in interesting if k in contract})
except Exception as exc:
    print("   chain FAIL:", type(exc).__name__, str(exc)[:300])

print("\n== 3. repo options provider wrapper ==")
try:
    provider = SchwabOptionsChainProvider(client)
    snapshot = provider.get_chain("SPY")
    print("   provider OK ->", type(snapshot).__name__)
    print("   rows:", len(snapshot) if hasattr(snapshot, "__len__") else "n/a")
except Exception as exc:
    print("   provider FAIL:", type(exc).__name__, str(exc)[:200])
