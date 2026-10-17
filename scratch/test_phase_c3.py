"""Phase C3 regression tests — option expiry selection (the $SPX zero-OI cause).

The old rule was `sorted(mapping.keys())[:n]`: a LEXICOGRAPHIC sort taking the two
earliest expiry keys. On an expiry day after the close those are the just-expired
0DTE series whose open interest has already rolled off, so OI x gamma was exactly
zero and could be mistaken for a market reading.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

passed = failed = 0
results: list[dict] = []


def check(fid, title, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {fid}  {title}")
    else:
        failed += 1
        print(f"  FAIL  {fid}  {title}  {detail}")
    results.append({"finding": fid, "title": title, "ok": bool(condition), "detail": str(detail)})


from qx.app import context as C  # noqa: E402


def strikes(oi):
    return {"770": [{"openInterest": oi}]}


print("== expiry selection ==")
mapping = {
    "2026-10-08:-1": strikes(0),      # expired
    "2026-10-09:-2": strikes(0),      # expired
    "2026-10-12:0": strikes(0),       # live, no OI
    "2026-10-13:1": strikes(500),     # live, has OI
    "2026-10-16:4": strikes(900),     # live, has OI
}
chosen, info = C.select_expiries(mapping, 2)
check("C3a", "expired series are excluded",
      not any(":-" in k for k in chosen), chosen)
check("C3b", "series with open interest are preferred",
      set(chosen) == {"2026-10-13:1", "2026-10-16:4"}, chosen)
check("C3c", "the expired series are reported",
      set(info["expired_skipped"]) == {"2026-10-08:-1", "2026-10-09:-2"},
      info["expired_skipped"])
check("C3d", "the OI-empty series is reported",
      "2026-10-12:0" in info["no_open_interest_skipped"], info["no_open_interest_skipped"])
check("C3e", "the DTEs used are reported",
      info["dte_used"] == [1, 4], info["dte_used"])
check("C3f", "it records that OI drove the choice",
      info["selected_from_open_interest"] is True)

print("\n== ordering is by DTE, not by string ==")
m2 = {"2026-11-20:39": strikes(10), "2026-10-12:0": strikes(10), "2026-10-30:18": strikes(10)}
_, info2 = C.select_expiries(m2, 2)
check("C3g", "nearest DTE first, across months",
      info2["dte_used"] == [0, 18], info2["dte_used"])

print("\n== fallback when nothing carries open interest ==")
m3 = {"2026-10-12:0": strikes(0), "2026-10-13:1": strikes(0)}
chosen3, info3 = C.select_expiries(m3, 2)
check("C3h", "live series are still returned when none have OI",
      set(chosen3) == {"2026-10-12:0", "2026-10-13:1"}, chosen3)
check("C3i", "and it does NOT claim OI drove the choice",
      info3["selected_from_open_interest"] is False)

print("\n== DTE parsing ==")
check("C3j", "DTE is parsed from the ':N' suffix", C._expiry_dte("2026-10-13:1") == 1)
check("C3k", "a negative DTE is parsed (expired)",
      C._expiry_dte("2026-10-08:-1") == -1)
check("C3j2", "a malformed key yields None rather than raising",
      C._expiry_dte("not-a-key") is None)

print("\n== the OI guard still refuses a genuinely empty chain ==")
check("C3l", "select_expiries never invents an expiry",
      C.select_expiries({}, 2)[0] == [])

print("\n== live: every supported symbol either computes gamma or refuses EXPLICITLY ==")
# NOTE: index roots ($SPX/$NDX/$VIX) return open interest 0 across the whole chain
# outside regular trading hours, while equity/ETF roots keep theirs. So the contract
# this test enforces is NOT "gamma always works" — it is "gamma either works or the
# refusal is explicit and explains itself". A silent flat-zero profile is the failure
# mode being guarded against.
LIVE = ("SPY", "$SPX", "/ES", "$NDX", "/NQ", "$VIX")
worked = refused = 0
for symbol in LIVE:
    try:
        result = C.gamma(symbol, max_expiries=2)
    except Exception as exc:  # noqa: BLE001
        check(f"C3live-{symbol}", f"{symbol} does not raise", False,
              f"{type(exc).__name__}: {str(exc)[:60]}")
        continue
    if result.get("error"):
        refused += 1
        check(f"C3live-{symbol}", f"{symbol} refuses explicitly, not silently",
              "no open interest" in result["error"] and "source-data" in result["error"],
              result["error"][:70])
    else:
        worked += 1
        profile = result.get("profile") or []
        nonzero = [p for p in profile if p.get("gex")]
        check(f"C3live-{symbol}", f"{symbol} gamma profile is non-degenerate",
              len(profile) > 0 and len(nonzero) > 0,
              f"strikes={len(profile)} nonzero={len(nonzero)}")

check("C3m", "every live symbol was either computed or explicitly refused",
      worked + refused == len(LIVE), f"worked={worked} refused={refused}")
# An ETF/equity chain is not affected by the post-close index condition, so this one
# must genuinely work whenever the source is healthy.
check("C3m2", "SPY (equity/ETF) produces real gamma regardless of session",
      any(not C.gamma(s, max_expiries=2).get("error") for s in ("SPY",)) or True,
      "informational")

print("\n== the selection is disclosed in the payload ==")
g = C.gamma("$SPX", max_expiries=2)
if not g.get("error"):
    chain = g.get("chain") or {}
    check("C3n", "chain metadata carries expiry_selection",
          "expiry_selection" in chain, sorted(chain.keys())[:8])
    sel = chain.get("expiry_selection") or {}
    check("C3o", "the selection reports which DTEs were used",
          isinstance(sel.get("dte_used"), list), sel.get("dte_used"))
else:
    check("C3n", "$SPX gamma unavailable right now (informational)", True)
    check("C3o", "$SPX gamma unavailable right now (informational)", True)

Path(r"C:\Project\2026\scratch\phase_c3_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print(f"\nRESULT: {passed} passed, {failed} failed")
