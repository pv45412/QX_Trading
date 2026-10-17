"""Scratch: verify chain-symbol mapping and GEX across asset classes."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import context as C  # noqa: E402

print("=== chain_symbol mapping (Schwab needs $ for INDEX roots) ===")
for symbol in ("SPX", "SPY", "NDX", "VIX", "RUT", "$SPX", "/ES", "/NQ", "/CL", "AAPL"):
    print(f"  {symbol:<6} -> {C.chain_symbol(symbol)}")

print("\n=== gamma across asset classes ===")
for symbol in ("SPX", "/ES", "/NQ", "SPY", "/CL", "/BTC"):
    try:
        result = C.gamma(symbol, max_expiries=2)
        if result.get("error"):
            print(f"  {symbol:<6} ERROR  {result['error'][:96]}")
        else:
            print(f"  {symbol:<6} chain={result.get('chain_symbol'):<6} "
                  f"spot={result.get('spot'):<10} net_gamma={str(result.get('net_gamma')):<14} "
                  f"flip={result.get('gamma_flip_price')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} EXC    {type(exc).__name__}: {str(exc)[:80]}")

print("\n=== levels across asset classes ===")
for symbol in ("SPX", "/ES", "/NQ", "/CL", "/BTC"):
    try:
        data = C.levels(symbol)
        price = (data.get("price") if isinstance(data, dict) else None)
        print(f"  {symbol:<6} price={price} source={data.get('quote_source') if isinstance(data, dict) else '?'}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} EXC {type(exc).__name__}: {str(exc)[:70]}")
