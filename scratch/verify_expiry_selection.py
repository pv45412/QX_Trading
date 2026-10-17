"""Scratch: verify the DTE-aware, OI-aware expiry selection."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import context as C  # noqa: E402

print("=== unit: select_expiries skips expired and OI-empty series ===")


def strikes(oi):
    return {"770": [{"openInterest": oi}]}


mapping = {
    "2026-10-08:-1": strikes(0),      # already expired
    "2026-10-09:-2": strikes(0),      # already expired
    "2026-10-12:0": strikes(0),       # live but no OI
    "2026-10-13:1": strikes(500),     # live WITH OI  <- should win
    "2026-10-16:4": strikes(900),     # live WITH OI
}
chosen, info = C.select_expiries(mapping, 2)
print(f"  chosen                : {chosen}")
print(f"  expired_skipped       : {info['expired_skipped']}")
print(f"  no_open_interest_skip : {info['no_open_interest_skipped']}")
print(f"  dte_used              : {info['dte_used']}")
print(f"  from_open_interest    : {info['selected_from_open_interest']}")
assert chosen == ["2026-10-13:1", "2026-10-16:4"], chosen
# expired_skipped is ordered by DTE (-2 before -1), so compare as a set.
assert set(info["expired_skipped"]) == {"2026-10-08:-1", "2026-10-09:-2"}, info["expired_skipped"]
assert "2026-10-12:0" in info["no_open_interest_skipped"]
print("  OK")

print()
print("=== unit: ordering is by DTE, not by string ===")
# Lexicographic sort would put '2026-10-9' style or day-10 before day-2 incorrectly
# across months; DTE ordering keeps nearest-first.
m2 = {"2026-11-20:39": strikes(10), "2026-10-12:0": strikes(10), "2026-10-30:18": strikes(10)}
chosen2, info2 = C.select_expiries(m2, 2)
print(f"  chosen: {chosen2}  dte={info2['dte_used']}")
assert info2["dte_used"] == [0, 18], info2["dte_used"]
print("  OK")

print()
print("=== unit: falls back to live series when NONE carry OI ===")
m3 = {"2026-10-12:0": strikes(0), "2026-10-13:1": strikes(0)}
chosen3, info3 = C.select_expiries(m3, 2)
print(f"  chosen={chosen3} from_open_interest={info3['selected_from_open_interest']}")
assert chosen3 == ["2026-10-12:0", "2026-10-13:1"]
assert info3["selected_from_open_interest"] is False
print("  OK")

print()
print("=== live: every symbol still computes GEX ===")
for symbol in ("SPY", "$SPX", "/ES", "$NDX", "/NQ", "$VIX", "/YM", "/RTY"):
    try:
        g = C.gamma(symbol, max_expiries=2)
        if g.get("error"):
            print(f"  {symbol:<6} ERROR {g['error'][:70]}")
        else:
            sel = (g.get("chain") or {}).get("expiry_selection") or {}
            print(f"  {symbol:<6} OK  strikes={len(g.get('profile') or []):<4} "
                  f"dte={sel.get('dte_used')} net={g.get('net_gamma'):,.0f}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {symbol:<6} EXC {type(exc).__name__}: {str(exc)[:60]}")

print()
print("=== live: the selection is disclosed in the payload ===")
g = C.gamma("$SPX", max_expiries=2)
chain = g.get("chain") or {}
print(f"  expiries used    : {chain.get('expiries')}")
print(f"  selection detail : {chain.get('expiry_selection')}")
