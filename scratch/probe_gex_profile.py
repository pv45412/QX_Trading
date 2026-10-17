"""Scratch: is the GEX strike profile genuinely empty, or is the UI failing?"""
import os
import sys

import requests

os.chdir(r"C:\Project\2026")

BASE = "http://127.0.0.1:8790"
for symbol in ("SPY", "$SPX", "/ES", "/NQ"):
    try:
        data = requests.get(f"{BASE}/api/context/gamma",
                            params={"symbol": symbol}, timeout=300).json()
        profile = data.get("profile") or []
        print(f"  {symbol:<6} error={bool(data.get('error'))!s:<6} "
              f"strikes={len(profile):<5} net_gamma={data.get('net_gamma')} "
              f"chain={data.get('chain_symbol')}")
        if data.get("error"):
            print(f"        {data['error'][:110]}")
        elif profile:
            top = sorted(profile, key=lambda p: abs(p.get("gex") or 0), reverse=True)[:3]
            print(f"        top strikes: "
                  + ", ".join(f"{p['strike']}({p['gex']:.0f})" for p in top))
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} EXC {type(exc).__name__}: {str(exc)[:80]}")
