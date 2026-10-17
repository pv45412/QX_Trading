"""Scratch: post-start health check of the running application."""
import datetime as dt
import json

import requests

BASE = "http://127.0.0.1:8790"

print("=== session ===")
ctx = requests.get(f"{BASE}/api/context", timeout=120).json()
print(f"  generated_at : {ctx.get('generated_at')}")
print(f"  freshness    : {ctx.get('freshness')}")
print(f"  regime       : {ctx.get('regime')}")
for proxy in (ctx.get("proxies") or [])[:3]:
    print(f"     {proxy.get('label'):<12} {proxy.get('last')}  src={proxy.get('quote_source')}")

print("\n=== ideas snapshot ===")
status = requests.get(f"{BASE}/api/ideas/status", timeout=60).json()
age = status.get("snapshot_age_seconds")
print(f"  candidates   : {status.get('candidates')}")
print(f"  age          : {(age/3600):.1f}h" if age else "  age          : unknown")
print(f"  stale        : {status.get('stale')}")
print(f"  building     : {(status.get('building') or {}).get('running')}")

ideas = requests.get(f"{BASE}/api/ideas", params={"view": "ready_now", "limit": 5}, timeout=120).json()
print(f"  verdict      : {ideas.get('verdict')}")
print(f"  ready_now    : {ideas.get('shown')} of {ideas.get('row_count')}")
if ideas.get("message"):
    print(f"  message      : {ideas['message'][:110]}")
for candidate in (ideas.get("ideas") or [])[:5]:
    print(f"     {candidate['symbol']:<6} {candidate['sector_symbol']:<5} "
          f"{candidate['direction']:<6} entry={candidate['entry_state']}")

print("\n=== explorer (one sector) ===")
try:
    data = requests.get(f"{BASE}/api/explorer/sector",
                        params={"symbol": "SMH", "view": "aligned_up", "limit": 5},
                        timeout=600).json()
    breadth = data.get("breadth") or {}
    print(f"  members      : {data.get('row_count')}  aligned view: {data.get('shown')}")
    print(f"  breadth      : denominator={breadth.get('denominator')} "
          f"covered={breadth.get('covered')} missing={breadth.get('missing_data')}")
    print(f"  coverage     : {(data.get('membership') or {}).get('coverage_label')}")
except Exception as exc:  # noqa: BLE001
    print(f"  explorer failed: {type(exc).__name__}: {str(exc)[:70]}")

print("\n=== context panels ===")
for symbol in ("SPY", "$SPX", "/ES"):
    try:
        g = requests.get(f"{BASE}/api/context/gamma", params={"symbol": symbol},
                         timeout=300).json()
        if g.get("error"):
            print(f"  {symbol:<6} gamma REFUSED: {g['error'][:66]}")
        else:
            print(f"  {symbol:<6} gamma OK  strikes={len(g.get('profile') or [])} "
                  f"net={g.get('net_gamma'):,.0f}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} gamma EXC {type(exc).__name__}: {str(exc)[:50]}")

print("\n=== accounts (read-only) ===")
try:
    accounts = requests.get(f"{BASE}/api/trade/accounts", timeout=120).json()
    for entry in accounts.get("accounts") or []:
        print(f"  {entry.get('label'):<8} {entry.get('masked')}  {entry.get('type')}")
    for warning in (accounts.get("warnings") or [])[:1]:
        print(f"  note: {warning[:100]}")
except Exception as exc:  # noqa: BLE001
    print(f"  accounts failed: {type(exc).__name__}: {str(exc)[:60]}")
