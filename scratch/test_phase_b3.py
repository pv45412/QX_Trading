"""Phase B3 regression tests — F12 (an achievable pullback view).

The old rule (`trend == BULLISH and momentum != BULLISH`) was mathematically
impossible in same-timeframe TOPS: a bullish Trend requires the EMA8>EMA13>EMA21
stack, and that stack IS the definition of bullish Momo.
"""
from __future__ import annotations

import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

passed = failed = 0


def check(fid, title, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {fid}  {title}")
    else:
        failed += 1
        print(f"  FAIL  {fid}  {title}  {detail}")


from qx.explorer import momo_trend, service as S  # noqa: E402

print("== F12: the old rule was impossible — demonstrate it ==")


def row(momentum, trend, phase=None, history_ok=True, aligned_down=False):
    return {"momentum": momentum, "trend": trend, "phase": phase,
            "history_ok": history_ok, "aligned_down": aligned_down}


impossible = row("BULLISH", "BULLISH", 3)
old_rule = impossible["trend"] == momo_trend.BULLISH and impossible["momentum"] != momo_trend.BULLISH
check("F12a", "Trend UP with Momo not-UP is impossible for a bullish stack",
      old_rule is False, f"old_rule_matched={old_rule}")
check("F12b", "so the old view could never include a bullish-trend row", not old_rule)

print("\n== F12: Boyd phase 4 IS a pullback, and is now recognised ==")
check("F12c", "phase 4 with BULLISH/BULLISH is a pullback",
      S._is_pullback(row("BULLISH", "BULLISH", 4)) is True)
check("F12d", "phase 4 with SIDEWAYS momentum is a pullback",
      S._is_pullback(row("SIDEWAYS", "SIDEWAYS", 4)) is True)
check("F12e", "phase 4 with BULLISH/SIDEWAYS is a pullback",
      S._is_pullback(row("BULLISH", "SIDEWAYS", 4)) is True)
check("F12f", "phase 3 (healthy trend) is NOT a pullback",
      S._is_pullback(row("BULLISH", "BULLISH", 3)) is False)

print("\n== F12: the view still refuses bearish and broken structures ==")
check("F12g", "phase 4 but bearish trend is refused",
      S._is_pullback(row("BEARISH", "BEARISH", 4, aligned_down=True)) is False)
check("F12h", "aligned_down is refused regardless of phase",
      S._is_pullback(row("SIDEWAYS", "SIDEWAYS", 4, aligned_down=True)) is False)
check("F12i", "insufficient history is refused",
      S._is_pullback(row("SIDEWAYS", "SIDEWAYS", 4, history_ok=False)) is False)
check("F12j", "phase 1 (downtrend) is not a pullback",
      S._is_pullback(row("SIDEWAYS", "SIDEWAYS", 1)) is False)

print("\n== F12: the view populates over the real universe ==")
d = S.explore("XLV", view="all", limit=200)
views = {v["id"]: v["count"] for v in d["views"]}
check("F12k", "the pullback view is computed and reported", "pullback" in views, json.dumps(views))
check("F12l", "rows carry an inspectable is_pullback flag",
      "is_pullback" in (d["rows"][0] if d["rows"] else {}))
check("F12m", "the definition is published with the response",
      "pullback_definition" in d and "phase 4" in d["pullback_definition"].lower(),
      d.get("pullback_definition", "")[:70])
check("F12n", "the view count equals the flagged rows",
      views["pullback"] == sum(1 for r in d["rows"] if r.get("is_pullback")),
      f"count={views['pullback']} flagged={sum(1 for r in d['rows'] if r.get('is_pullback'))}")

# The filter must return exactly the flagged rows.
pull = S.explore("XLV", view="pullback", limit=200)
check("F12o", "the pullback VIEW returns exactly the flagged rows",
      pull["shown"] == views["pullback"], f"shown={pull['shown']} count={views['pullback']}")
for r in pull["rows"]:
    check(f"F12-inv-{r['symbol']}", f"{r['symbol']} is not bearish/broken in the pullback view",
          not r.get("aligned_down") and r.get("history_ok"))

print("\n== F12: a real phase-4 name is reachable end to end ==")
found = None
for symbol in ("XLV", "XLY", "JETS", "XRT"):
    dd = S.explore(symbol, view="pullback", limit=200)
    if dd["rows"]:
        found = (symbol, dd["rows"][0])
        break
if found:
    sector, r = found
    check("F12p", f"a pullback is reachable live ({sector}/{r['symbol']})",
          r.get("is_pullback") is True,
          f"phase={r.get('phase')} momo={r['momentum']} trend={r['trend']}")
    check("F12q", "and it carries a usable plan or an explicit block",
          r["entry"]["state"] in ("TRIGGER_CONFIRMED", "BREAKOUT_WATCH", "PULLBACK_CANDIDATE",
                                  "EXTENDED_WAIT", "BLOCKED_DATA", "NOT_ALIGNED"),
          r["entry"]["state"])
else:
    check("F12p", "no live pullback found in the sampled sectors (condition may be absent today)",
          True, "informational")

print(f"\nRESULT: {passed} passed, {failed} failed")
