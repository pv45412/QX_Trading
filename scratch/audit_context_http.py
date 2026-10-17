"""Scratch: verify the new Context and Settings endpoints over HTTP."""
import json

import requests

BASE = "http://127.0.0.1:8790"
ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print("== pages ==")
for path, marker in (("/context", "Context"), ("/settings", "Settings")):
    r = requests.get(BASE + path, timeout=60)
    check(f"GET {path}", r.status_code == 200 and marker in r.text, f"HTTP {r.status_code} len={len(r.text)}")

print("== nav includes all five pages ==")
home = requests.get(BASE + "/scanner", timeout=60).text
for item in ("Scanner", "Trade Workspace", "Context", "Reports", "Settings"):
    check(f"nav has {item}", f">{item}</a>" in home or item in home)

print("== levels ==")
lv = requests.get(BASE + "/api/context/levels", params={"symbol": "SPY"}, timeout=120).json()
check("levels ok", "price" in lv and "prior_day" in lv, f"price={lv.get('price')} src={lv.get('source')}")
check("ATR is sane (<5% of price)", lv.get("atr_14") is not None and lv["atr_14"] < lv["price"] * 0.05,
      f"atr={lv.get('atr_14')} price={lv.get('price')}")
bands = lv.get("vwap_bands_20d") or {}
check("vwap bands ordered", bands.get("upper_2", 0) > bands.get("upper_1", 0) > bands.get("vwap", 0) > bands.get("lower_1", 0) > bands.get("lower_2", 0),
      json.dumps(bands))
check("prior day levels present", all(lv["prior_day"].get(k) for k in ("high", "low", "close")),
      json.dumps(lv["prior_day"]))

print("== futures (basis must be vs its OWN index) ==")
fut = requests.get(BASE + "/api/context/futures", timeout=180).json()
rows = fut.get("futures") or []
check("two futures returned", len(rows) == 2, ", ".join(r["symbol"] for r in rows))
for row in rows:
    check(f"{row['symbol']} basis sane (<5%)",
          row.get("basis_pct") is not None and abs(row["basis_pct"]) < 5.0,
          f"cash={row.get('cash_symbol')} {row.get('cash_last')} fut={row.get('last')} basis%={row.get('basis_pct')}")

print("== GEX ==")
gx = requests.get(BASE + "/api/context/gamma", params={"symbol": "SPY"}, timeout=300).json()
if gx.get("error"):
    check("gex computed", False, gx["error"])
else:
    check("gex computed", True, f"spot={gx['spot']} net={gx['net_gamma']:,.0f} regime={gx['regime'][:28]}")
    check("flip/walls present", all(gx.get(k) for k in ("gamma_flip_price", "call_wall", "put_wall")),
          f"flip={gx['gamma_flip_price']} call={gx['call_wall']} put={gx['put_wall']}")
    check("settlement provenance declared", bool(gx.get("settlement_source")),
          f"{gx.get('settlement_source')}/{gx.get('settlement_confidence')}")
    prof = gx.get("profile") or []
    check("strike profile returned", len(prof) > 10, f"{len(prof)} strikes")
    check("profile carries OI", any(r["call_oi"] or r["put_oi"] for r in prof))
    check("method disclosed", "calculate_gamma_exposure" in (gx.get("method") or ""))

print("== settings (secret hygiene) ==")
st = requests.get(BASE + "/api/settings/schwab", timeout=180).json()
blob = json.dumps(st)
check("status returned", "client" in st and "token" in st)
check("client secret never returned", "client_secret" not in blob or "client_secret_present" in blob)
try:
    from qx.config.settings import get_settings
    import os
    os.chdir(r"C:\Project\2026")
    secret = get_settings().schwab_client_secret
except Exception:
    secret = ""
check("secret VALUE absent from payload", (not secret) or (secret not in blob))
check("no raw access token in payload", "access_token" not in blob.replace("access_token_valid", ""))
check("client id masked", "*" in (st.get("client", {}).get("client_id_masked") or ""),
      st.get("client", {}).get("client_id_masked"))
check("health probe ok", (st.get("health") or {}).get("ok") is True, json.dumps(st.get("health"))[:120])

acc = requests.get(BASE + "/api/settings/schwab/accounts", timeout=180).json()
check("accounts probe ok", acc.get("ok") is True, f"{acc.get('count')} accounts")

print("== health page list ==")
health = requests.get(BASE + "/api/health", timeout=30).json()
check("health lists five pages", len(health.get("pages") or []) == 5, json.dumps(health.get("pages")))

print(f"\nRESULT: {ok} passed, {fail} failed")
