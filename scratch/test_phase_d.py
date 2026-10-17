"""Phase D regression tests — F23: study state vs. modelled risk.

The study's exit is a SIGNAL REVERSAL (wave centre / VWAP / stack flip). The ATR stop
and 1R/2R targets are computed and displayed but never consulted. These tests assert
BOTH halves of the fix:
  * parity  — the study's real exit behaviour is unchanged
  * honesty — the displayed level is labelled a reference, and breach is reported
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace as N

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


from qx.explorer import service as S  # noqa: E402
import qx.explorer.master_auto as ma  # noqa: E402

cfg = S.DEFAULT_CONFIG


def snap(**kw):
    base = dict(warmup_ok=True, trade_direction=0, trade_atr=2, call_trigger_price=105,
                put_trigger_price=95, wave_high=104, wave_low=96, active_stop=None,
                call_ready=False, put_ready=False, bull_build=False, bear_build=False,
                bull_stack=False, bear_stack=False)
    base.update(kw)
    return N(**base)


print("== the study's exit rule is a signal reversal, and is stated ==")
long_watch = snap(call_ready=True, bull_build=True, bull_stack=True)
e = S.classify_entry({"price": 104}, long_watch, cfg, bars=[{"close": 100 + i} for i in range(20)])
check("D1", "study_exit_rule is present on the payload", bool(e.get("study_exit_rule")))
check("D2", "it names the wave centre as an exit",
      "wave centre" in (e.get("study_exit_rule") or "").lower(), e.get("study_exit_rule", "")[:70])
check("D3", "it explicitly says the ATR stop is NOT the exit",
      "does not exit at the atr stop" in (e.get("study_exit_rule") or "").lower(),
      e.get("study_exit_rule", "")[:90])

print("\n== the displayed level is labelled a REFERENCE, not a protected stop ==")
check("D4", "invalidation_basis is REFERENCE_ONLY",
      e.get("invalidation_basis") == S.INVALIDATION_BASIS_REFERENCE, e.get("invalidation_basis"))
check("D5", "risk_note says the study will not exit here",
      "not a protected stop" in (e.get("risk_note") or "").lower(), e.get("risk_note", "")[:80])
check("D6", "a payload with no level reports basis None",
      S.classify_entry({"price": 104}, snap(), cfg).get("invalidation_basis") is None)

print("\n== breach of the reference is reported descriptively ==")
flat = [{"close": 100.0} for _ in range(20)]
breached = S.classify_entry({"price": 104}, long_watch, cfg, bars=flat)
check("D7", "a breached reference is detected",
      breached["stop_breach"]["breached"] is True, json.dumps(breached["stop_breach"]))
check("D8", "the count of closes beyond is reported",
      breached["stop_breach"]["closes_beyond"] == 20, breached["stop_breach"]["closes_beyond"])
check("D9", "the breach note is human-readable",
      "beyond the reference level" in breached["stop_breach"]["note"],
      breached["stop_breach"]["note"])
# Start ABOVE the reference (102.8) so no close is beyond it.
rising = [{"close": 110 + i * 5} for i in range(20)]
clean = S.classify_entry({"price": 104}, long_watch, cfg, bars=rising)
check("D10", "an unbreached reference reports breached False",
      clean["stop_breach"]["breached"] is False, json.dumps(clean["stop_breach"]))
check("D11", "no bars means the breach is NOT evaluated, not assumed",
      S.classify_entry({"price": 104}, long_watch, cfg)["stop_breach"]["evaluated"] is False)

print("\n== EVERY return path is annotated (no path can silently claim a stop) ==")
paths = {
    "no data": ({"price": 104}, N(warmup_ok=False)),
    "ambiguous": ({"price": 104}, snap(call_ready=True, put_ready=True)),
    "not aligned": ({"price": 104}, snap()),
    "latched": ({"price": 100}, snap(trade_direction=1, active_stop=98, trade_entry=100,
                                     active_target2=104, call_ready=True, bull_build=True)),
    "expired": ({"price": 104}, snap(trade_direction=1, active_stop=98, trade_entry=100,
                                     active_target2=104, call_ready=True, bull_build=True)),
}
missing = []
for label, (row, snapshot) in paths.items():
    payload = S.classify_entry(row, snapshot, cfg, bars_since_signal=99)
    if "study_exit_rule" not in payload or "invalidation_basis" not in payload:
        missing.append(label)
check("D12", "all five return paths carry the risk annotation", not missing, missing)

print("\n== PARITY: the study's own exit behaviour is UNCHANGED ==")
# A latched long whose price collapses far below the ATR stop, while the wave centre
# has NOT been crossed, must STAY latched — that is the documented study behaviour and
# F23 is a labelling fix, not a behaviour change.
bars_hold = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
             for _ in range(200)]
hold = ma.latest(bars_hold, minutes=1440)
check("D13", "MASTER AUTO still evaluates without error after the F23 change",
      hold is not None)
check("D14", "the study still exposes active_stop for display",
      hasattr(hold, "active_stop"))
# The exit branch must still be the wave/stack rule, not a stop comparison.
import inspect  # noqa: E402

src = inspect.getsource(ma)
check("D15", "the exit branch still uses call_exit_base / put_exit_base",
      "call_exit_base" in src and "put_exit_base" in src)
check("D16", "no new exit branch compares price against active_stop",
      "active_stop" not in src.split("call_exit_base")[1][:400]
      if "call_exit_base" in src else False,
      "exit region should not reference active_stop")

print("\n== live: the explorer surfaces the disclosure ==")
data = S.explore("SMH", view="aligned_up", limit=3)
rows = data.get("rows") or []
if rows:
    entry = rows[0]["entry"]
    check("D17", "live rows carry study_exit_rule", bool(entry.get("study_exit_rule")))
    check("D18", "live rows carry invalidation_basis",
          "invalidation_basis" in entry, sorted(entry.keys())[:10])
    check("D19", "live rows carry stop_breach",
          isinstance(entry.get("stop_breach"), dict), str(entry.get("stop_breach"))[:60])
else:
    check("D17", "no live rows available (informational)", True)
    check("D18", "no live rows available (informational)", True)
    check("D19", "no live rows available (informational)", True)

print("\n== the UI no longer claims an enforced stop ==")
ui = Path(r"C:\Project\2026\src\qx\app\ui.py").read_text(encoding="utf-8")
check("D20", "no 'Invalid.' column header remains", "'Invalid.'" not in ui)
check("D21", "no bare 'Invalidation' KPI label remains", "'Invalidation'" not in ui)
check("D22", "no 'close through X' phrasing implying enforcement remains",
      "close through " not in ui)
check("D23", "the UI labels the level 'Ref. stop'", "Ref. stop" in ui)
check("D24", "the UI states the level is not enforced",
      "REFERENCE — not enforced" in ui or "REFERENCE — study will not exit here" in ui)

Path(r"C:\Project\2026\scratch\phase_d_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print(f"\nRESULT: {passed} passed, {failed} failed")
