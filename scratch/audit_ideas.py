"""Scratch: verify Trade Ideas aggregation, views, sorting and ranking."""
import json
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import qx.explorer.ideas as I  # noqa: E402

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print("== 1. no snapshot yet -> honest empty, not fabricated ideas ==")
I.SNAPSHOT_PATH = os.path.join(r"C:\Project\2026\data\cache\trade_ideas", "_absent.json")
empty = I.ideas()
check("no snapshot reported", empty["has_snapshot"] is False)
check("verdict is NO_SNAPSHOT", empty["verdict"] == "NO_SNAPSHOT", empty["verdict"])
check("zero ideas", empty["shown"] == 0)
check("all five views present with zero counts",
      len(empty["views"]) == 5 and all(v["count"] == 0 for v in empty["views"]),
      [v["id"] for v in empty["views"]])

print("\n== 2. build a real snapshot (industries only, to keep it quick) ==")
I.SNAPSHOT_PATH = os.path.join(r"C:\Project\2026\data\cache\trade_ideas", "snapshot.json")
started = time.time()
result = I.build(force=True, sectors=["SMH", "IGV", "XBI"])
print(f"   build took {time.time() - started:.1f}s -> {json.dumps(result)}")
check("build succeeded", result.get("ok") is True, json.dumps(result))
check("candidates found", result.get("candidates", 0) > 0, f"{result.get('candidates')} candidates")

print("\n== 3. snapshot metadata is honest ==")
st = I.status()
check("snapshot exists", st["has_snapshot"] is True)
check("age reported", st["snapshot_age_seconds"] is not None, f"{st['snapshot_age_seconds']}s")
check("fresh snapshot not marked stale", st["stale"] is False)

print("\n== 4. views are filters over ONE candidate set ==")
data = I.ideas(view="all", limit=500)
candidates = data["ideas"]
check("all view returns candidates", data["shown"] > 0, f"{data['shown']}")
check("five views with counts", len(data["views"]) == 5,
      {v["id"]: v["count"] for v in data["views"]})
# Every view must be a SUBSET of the same records (no parallel scanners).
total = data["row_count"]
for v in data["views"]:
    sub = I.ideas(view=v["id"], limit=500)
    check(f"view {v['id']} is a subset of the shared set",
          sub["row_count"] == total, f"shown={sub['shown']} of {total} records")

print("\n== 5. bucket semantics match entry state ==")
from qx.explorer import service as S  # noqa: E402
buckets = {}
for c in candidates:
    buckets.setdefault(c["bucket"], []).append(c)
print("   buckets:", {k: len(v) for k, v in buckets.items()})
ready = I.ideas(view="ready_now", limit=500)["ideas"]
check("ready_now contains only the live-plan state",
      all(c["entry_state"] == S.ENTRY_TRIGGER for c in ready), f"{len(ready)} rows")
near = I.ideas(view="near_trigger", limit=500)["ideas"]
check("near_trigger contains only breakout-watch",
      all(c["entry_state"] == S.ENTRY_BREAKOUT for c in near), f"{len(near)} rows")
pull = I.ideas(view="pullback_watch", limit=500)["ideas"]
check("pullback_watch contains only flagged pullbacks (F12 definition)",
      all(c.get("is_pullback") for c in pull), f"{len(pull)} rows")
bear = I.ideas(view="bearish", limit=500)["ideas"]
check("bearish contains only SHORT direction",
      all(c["direction"] == "SHORT" for c in bear), f"{len(bear)} rows")
newly = I.ideas(view="newly_aligned", limit=500)["ideas"]
check("newly_aligned contains only newly aligned",
      all(c["newly_aligned"] for c in newly), f"{len(newly)} rows")

print("\n== 6. alignment alone never yields EXECUTABLE ==")
check("no candidate is EXECUTABLE",
      not any("EXECUTABLE" in str(c.get("entry_state")) for c in candidates))
check("every candidate is UNDERLYING_ONLY",
      all(c["instrument_evaluation"] == "UNDERLYING_ONLY" for c in candidates))
check("every candidate carries a horizon",
      all(c["horizon"] == "SWING" for c in candidates))

print("\n== 7. sorting changes order without changing membership ==")
base = I.ideas(view="all", sort="entry_readiness", limit=500)
for sort_id, _, _ in I.SORTS:
    s = I.ideas(view="all", sort=sort_id, limit=500)
    same_members = {c["symbol"] for c in s["ideas"]} == {c["symbol"] for c in base["ideas"]}
    check(f"sort {sort_id} keeps the same members", same_members, f"{s['shown']} rows")
    if sort_id == "rs_market":
        vals = [c["rs_vs_market"] for c in s["ideas"] if c["rs_vs_market"] is not None]
        check("  rs_market descending", vals == sorted(vals, reverse=True), f"{vals[:4]}")
    if sort_id == "entry_readiness":
        order = [{"ready_now": 0, "near_trigger": 1, "pullback_watch": 2,
                  "extended_wait": 3, "blocked": 4, "insufficient": 5}[c["bucket"]] for c in s["ideas"]]
        check("  readiness ascending", order == sorted(order), f"{order[:6]}")

print("\n== 8. dedupe by instrument identity ==")
symbols = [c["symbol"] for c in candidates]
check("no duplicate symbol across sectors", len(symbols) == len(set(symbols)),
      f"{len(symbols)} rows, {len(set(symbols))} unique")
multi = [c for c in candidates if c.get("also_in")]
check("names held by several ETFs record the others",
      all(isinstance(c["also_in"], list) for c in multi),
      f"{len(multi)} multi-sector names")

print("\n== 9. 'why ranked here' is deterministic evidence ==")
if candidates:
    target = candidates[0]["symbol"]
    why = I.why_ranked(target, view="all")
    check("why_ranked explains position", why["ok"] and why["position"] >= 1,
          f"{target} at {why.get('position')} of {why.get('of')}")
    check("reasons are evidence strings", len(why["reasons"]) >= 2,
          why["reasons"][0][:70])
    check("no universal score claimed", "no single universal score" in why["note"])
    missing = I.why_ranked("NOTAREALSYM")
    check("unknown symbol refused", missing["ok"] is False)

print("\n== 10. sector filter narrows without rebuilding ==")
one = I.ideas(view="all", sector="SMH", limit=500)
# F18: the filter matches the membership RELATION, so a row may have a different
# PRIMARY parent while still being a member of SMH. Assert membership, not primacy.
check("sector filter applied",
      all("SMH" in (c.get("sector_symbols") or [c.get("sector_symbol")]) for c in one["ideas"]),
      f"{one['shown']} in SMH")
check("sector filter does not change the snapshot", one["has_snapshot"] is True)

print(f"\nRESULT: {ok} passed, {fail} failed")
