"""Scratch: does the APP now get OI for $SPX, and what drives the expiry choice?"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import context as C  # noqa: E402

print("=== the app's own gamma() across symbols, right now ===")
for symbol in ("SPY", "$SPX", "/ES", "$NDX", "/NQ", "$VIX"):
    try:
        result = C.gamma(symbol, max_expiries=2)
        if result.get("error"):
            print(f"  {symbol:<6} ERROR  {result['error'][:88]}")
        else:
            profile = result.get("profile") or []
            nonzero = [p for p in profile if p.get("gex")]
            print(f"  {symbol:<6} OK  chain={result.get('chain_symbol'):<6} "
                  f"spot={result.get('spot'):<10} strikes={len(profile):<4} "
                  f"nonzero={len(nonzero):<4} net={result.get('net_gamma')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} EXC {type(exc).__name__}: {str(exc)[:70]}")

print()
print("=== which expiries does the app actually select? ===")
frame, spot, meta = C._chain_frame("$SPX", max_expiries=2)
print(f"  chain_symbol={C.chain_symbol('$SPX')} spot={spot}")
print(f"  expiries used = {meta.get('expiries')}")
print(f"  contracts     = {meta.get('contracts')}")
print(f"  truncated     = {meta.get('is_truncated')}")
if not frame.empty:
    total_oi = frame["open_interest"].fillna(0).sum()
    print(f"  total OI in frame = {total_oi:,.0f}")
    print(f"  rows with OI > 0  = {(frame['open_interest'] > 0).sum()} / {len(frame)}")
    print()
    print("  per-expiry OI:")
    for expiry, group in frame.groupby("expiry"):
        print(f"    {expiry:<22} rows={len(group):<5} "
              f"OI>0={(group['open_interest'] > 0).sum():<5} "
              f"total_OI={group['open_interest'].fillna(0).sum():,.0f}")
