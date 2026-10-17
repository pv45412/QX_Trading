"""Scratch: verify GEX over HTTP for every symbol after the expiry fix."""
import requests

BASE = "http://127.0.0.1:8790"
for symbol in ("SPY", "$SPX", "/ES", "$NDX", "/NQ", "$VIX", "/YM", "/RTY", "/CL"):
    try:
        data = requests.get(f"{BASE}/api/context/gamma",
                            params={"symbol": symbol}, timeout=300).json()
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} EXC {type(exc).__name__}: {str(exc)[:60]}")
        continue
    if data.get("error"):
        print(f"  {symbol:<6} REFUSED: {data['error'][:74]}")
    else:
        selection = (data.get("chain") or {}).get("expiry_selection") or {}
        profile = data.get("profile") or []
        nonzero = [p for p in profile if p.get("gex")]
        print(f"  {symbol:<6} OK  strikes={len(profile):<4} nonzero={len(nonzero):<4} "
              f"dte={str(selection.get('dte_used')):<10} "
              f"skipped_no_oi={len(selection.get('no_open_interest_skipped') or [])} "
              f"net={data.get('net_gamma'):,.0f}")
