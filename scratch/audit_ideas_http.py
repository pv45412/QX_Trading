"""Scratch: HTTP verification of the Trade Ideas API."""
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


print("== page renders with the shared nav ==")
text = requests.get(BASE + "/ideas", timeout=60).text
check("Trade Ideas page", "Trade Ideas" in text, f"{len(text)} bytes")
check("nav includes Trade Ideas", 'href="/ideas"' in text and ">Trade Ideas<" in text)
check("nav includes Discover", ">Discover<" in text)
check("page explains the shared-set rule", "these are filters, not separate scanners" in text)
check("page offers rebuild", "Rebuild snapshot" in text)

print("\n== status ==")
st = requests.get(BASE + "/api/ideas/status", timeout=60).json()
check("status reports a snapshot", st["has_snapshot"] is True, f"{st['candidates']} candidates")
check("age reported", st["snapshot_age_seconds"] is not None, f"{st['snapshot_age_seconds']}s")
check("staleness flagged", "stale" in st, f"stale={st['stale']}")

print("\n== ideas views ==")
allv = requests.get(BASE + "/api/ideas", params={"view": "all", "limit": 500}, timeout=120).json()
check("ideas returned", allv["row_count"] > 0, f"{allv['row_count']} candidates")
check("five views with counts", len(allv["views"]) == 5,
      {v["id"]: v["count"] for v in allv["views"]})
check("five sorts offered", len(allv["sorts"]) == 5, [s["id"] for s in allv["sorts"]])
check("snapshot metadata exposed", allv["sectors_scanned"] and allv["universe"],
      f"{allv['sectors_scanned']} ETFs")
check("rule versions exposed", all(allv["rules"].values()), json.dumps(allv["rules"]))

total = allv["row_count"]
for view in ("ready_now", "near_trigger", "pullback_watch", "newly_aligned", "bearish"):
    v = requests.get(BASE + "/api/ideas", params={"view": view, "limit": 500}, timeout=120).json()
    check(f"view {view} is a filter over the same set", v["row_count"] == total,
          f"{v['shown']} of {total}")

print("\n== candidate contract ==")
first = allv["ideas"][0]
required = ["symbol", "sector_symbol", "direction", "entry_state", "playbook", "trigger",
            "invalidation", "target", "reward_risk", "horizon", "instrument_evaluation",
            "as_of", "rule_version"]
missing = [k for k in required if k not in first]
check("every required field present", not missing, f"missing={missing}")
check("horizon is declared", first["horizon"] == "SWING", first["horizon"])
check("instrument evaluation declared", first["instrument_evaluation"] == "UNDERLYING_ONLY")
check("no EXECUTABLE anywhere",
      not any("EXECUTABLE" in str(c.get("entry_state")) for c in allv["ideas"]))

print("\n== sorting ==")
for sort_id in ("entry_readiness", "newly_aligned", "rs_parent", "rs_market", "distance_to_trigger"):
    s = requests.get(BASE + "/api/ideas", params={"view": "all", "sort": sort_id, "limit": 500},
                     timeout=120).json()
    same = {c["symbol"] for c in s["ideas"]} == {c["symbol"] for c in allv["ideas"]}
    check(f"sort {sort_id} keeps membership", same, f"{s['shown']} rows")

print("\n== sector filter ==")
smh = requests.get(BASE + "/api/ideas", params={"view": "all", "sector": "SMH", "limit": 500},
                   timeout=120).json()
check("sector filter narrows", smh["row_count"] <= total, f"{smh['row_count']} in SMH")
# F18: the filter matches the membership RELATION, so a row's PRIMARY parent may
# differ while it is still a member of SMH. Assert membership, not primacy.
check("filtered rows are members of that sector",
      all("SMH" in (c.get("sector_symbols") or [c.get("sector_symbol")]) for c in smh["ideas"]),
      f"{smh['shown']}")

print("\n== why ranked ==")
why = requests.get(BASE + "/api/ideas/why",
                   params={"symbol": first["symbol"], "view": "all"}, timeout=120).json()
check("why_ranked answers", why["ok"] is True and why["position"] >= 1,
      f"{first['symbol']} at {why['position']} of {why['of']}")
check("reasons cite evidence", len(why["reasons"]) >= 2, why["reasons"][0][:64])
why_missing = requests.get(BASE + "/api/ideas/why", params={"symbol": "NOPE"}, timeout=60).json()
check("unknown symbol refused", why_missing["ok"] is False)

print("\n== build endpoint: guard behaviour WITHOUT starting a 12-minute job ==")
# NOTE: POSTing /api/ideas/build with force=false STARTS a build when none is
# running, so this test must not call it blindly — that would mutate production
# state and occupy the worker for ~12 minutes. Assert the exposed contract instead.
st = requests.get(BASE + "/api/ideas/status", timeout=60).json()
check("status exposes build progress", "building" in st and "running" in st["building"],
      json.dumps(st["building"])[:80])
check("status exposes the snapshot identity", "has_snapshot" in st and "candidates" in st,
      f"candidates={st.get('candidates')}")

print(f"\nRESULT: {ok} passed, {fail} failed")
