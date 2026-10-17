"""Scratch: which symbols does Schwab's option-chain endpoint accept?"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402
from qx.brokers.schwab.client import SchwabApiClient  # noqa: E402
from qx.config.settings import get_settings  # noqa: E402

settings = get_settings()
client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)

# NOTE: dollar-prefixed forms matter for INDEX symbols.
SYMBOLS = ["SPX", "$SPX", "SPY", "QQQ", "NDX", "$NDX", "VIX", "$VIX",
           "RUT", "$RUT", "/ES", "/NQ", "/CL", "/BTC", "ES", "NQ",
           "IWM", "AAPL", "TSLA", "GLD"]

print("Testing Schwab /marketdata/v1/chains symbol forms:")
accepted, rejected = [], []
for symbol in SYMBOLS:
    try:
        result = client.get("/marketdata/v1/chains", params={
            "symbol": symbol, "contractType": "ALL", "strikeCount": 5, "strategy": "SINGLE"})
        if isinstance(result, dict):
            contracts = result.get("numberOfContracts")
            underlying = result.get("underlyingPrice")
            expiries = result.get("callExpDateMap") or {}
            accepted.append(symbol)
            print(f"  {symbol:<7} OK   contracts={contracts!s:<6} "
                  f"underlying={underlying!s:<12} expiries={len(expiries)}")
        else:
            rejected.append(symbol)
            print(f"  {symbol:<7} no dict payload")
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        code = next((c for c in ("400", "403", "404", "500") if c in text), "ERR")
        rejected.append(symbol)
        print(f"  {symbol:<7} {code:<4} {text[:78]}")

print(f"\naccepted: {accepted}")
print(f"rejected: {rejected}")
