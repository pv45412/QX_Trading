"""Scratch: verify the new context (levels/futures/GEX) and settings services."""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import context, settings_service  # noqa: E402

print("== LEVELS ==")
lv = context.levels("SPY")
for key in ("symbol", "price", "source", "quote_source", "realtime", "anchored_vwap", "atr_14"):
    print(f"   {key}: {lv.get(key)}")
print("   prior_day:", lv.get("prior_day"))
print("   today    :", lv.get("today"))
print("   vwap_bands:", lv.get("vwap_bands"))
print("   position_vs:", lv.get("position_vs"))

print("\n== FUTURES ==")
fut = context.futures()
print("   cash:", fut.get("cash"))
for row in fut.get("futures", []):
    print(f"   {row['symbol']:<4} {row['label']:<18} last={row['last']} resolved={row['resolved']} "
          f"basis={row['basis_vs_cash']} ({row['basis_pct']}%) rt={row['realtime']}")

print("\n== GEX ==")
gx = context.gamma("SPY")
if gx.get("error"):
    print("   ERROR:", gx["error"])
else:
    for key in ("symbol", "spot", "net_gamma", "regime", "gamma_flip_price", "call_wall", "put_wall",
                "call_put_gamma_ratio", "zero_dte_volume_ratio", "expected_move_1sigma",
                "settlement_source", "settlement_confidence"):
        print(f"   {key}: {gx.get(key)}")
    print("   chain:", gx.get("chain"))
    print("   profile points:", len(gx.get("profile") or []))
    top = sorted(gx.get("profile") or [], key=lambda r: abs(r["gex"]), reverse=True)[:5]
    for row in top:
        print(f"      strike {row['strike']}  gex {row['gex']:>16,.0f}  callOI {row['call_oi']}  putOI {row['put_oi']}")

print("\n== SETTINGS (secrets must be masked/absent) ==")
st = settings_service.status()
print("   client:", json.dumps(st.get("client"), indent=None)[:280])
print("   token :", json.dumps(st.get("token"), indent=None)[:220])
print("   health:", json.dumps(st.get("health"), indent=None)[:200])
blob = json.dumps(st)
secret = ""
try:
    from qx.config.settings import get_settings
    secret = get_settings().schwab_client_secret
except Exception:
    pass
print("   SECRET LEAKED:", bool(secret) and secret in blob)
print("   token value leaked:", "access_token" in blob)

print("\n== ACCOUNTS HEALTH ==")
print("  ", json.dumps(settings_service.accounts_health())[:260])
