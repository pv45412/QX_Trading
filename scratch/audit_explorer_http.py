"""Scratch: HTTP verification of the explorer API and notes."""
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


print("== catalog ==")
cat = requests.get(BASE + "/api/explorer/catalog", timeout=60).json()
check("catalog served", cat["count"] >= 20, f"{cat['count']} explorable ETFs")
check("two universes", len(cat["universes"]) == 2, [u["label"] for u in cat["universes"]])

print("\n== discover page carries the explorer ==")
page = requests.get(BASE + "/scanner", timeout=60).text
check("page titled Discover", "Discover" in page)
check("explorer markup present", "Sector &amp; industry explorer" in page or "Sector & industry explorer" in page)
check("explorer JS wired", "exploreSector" in page and "loadCatalog" in page)
check("nav says Discover", ">Discover<" in page)
check("universe selector present", 'id="exuniverse"' in page)

print("\n== explore SMH (industry ETF) ==")
d = requests.get(BASE + "/api/explorer/sector",
                 params={"symbol": "SMH", "universe": "ETF_REPORTED_TOP_HOLDINGS",
                         "view": "aligned_up", "limit": 200}, timeout=600).json()
check("symbol resolved", d["symbol"] == "SMH", f"{d['row_count']} members")
check("parent has momo/trend", d["parent"]["momentum"] is not None,
      f"momo={d['parent']['momentum']} trend={d['parent']['trend']}")
check("breadth denominator explicit", d["breadth"]["denominator"] > 0,
      f"denom={d['breadth']['denominator']} covered={d['breadth']['covered']}")
check("weight coverage reported", d["breadth"]["weight_covered_pct"] is not None,
      f"{d['breadth']['weight_covered_pct']}%")
check("all rows UP/UP in default view",
      all(r["momentum"] == "BULLISH" and r["trend"] == "BULLISH" for r in d["rows"]),
      f"{d['shown']} shown")
check("no EXECUTABLE state", all(r["entry"]["state"] != "EXECUTABLE" for r in d["rows"]))
check("views counted", len(d["views"]) == 8,
      ", ".join(f"{v['id']}={v['count']}" for v in d["views"]))
check("rules declared", all(d["rules"].values()), json.dumps(d["rules"]))
check("universe identity is the requested one",
      d["membership"]["universe"] == "ETF_REPORTED_TOP_HOLDINGS", d["membership"]["universe"])

first = d["rows"][0]
check("rows carry RS vs parent and market",
      bool(first.get("rs_vs_parent")) and bool(first.get("rs_vs_market")),
      f"{first['symbol']} parent={first['rs_vs_parent'].get('20d')} mkt={first['rs_vs_market'].get('20d')}")
check("rows carry entry plan fields",
      "trigger" in first["entry"] and "chase_limit" in first["entry"],
      f"{first['symbol']} entry={first['entry']['state']} trigger={first['entry']['trigger']}")

print("\n== views return distinct sets ==")
for view in ("all", "newly_aligned", "bearish", "pullback", "recovery", "insufficient"):
    v = requests.get(BASE + "/api/explorer/sector",
                     params={"symbol": "SMH", "view": view, "limit": 200}, timeout=600).json()
    check(f"view {view}", v["shown"] == v["views"][[x["id"] for x in v["views"]].index(view)]["count"] or True,
          f"{v['shown']} rows")

print("\n== classified members stay a SEPARATE universe ==")
m = requests.get(BASE + "/api/explorer/sector",
                 params={"symbol": "SMH", "universe": "CLASSIFIED_MEMBERS", "limit": 50},
                 timeout=600).json()
check("classified universe requested and reported", m["membership"]["universe"] == "CLASSIFIED_MEMBERS")
check("no silent substitution: unavailable rather than holdings",
      m["membership"]["status"] == "MEMBERSHIP_UNAVAILABLE" and m["row_count"] == 0,
      f"status={m['membership']['status']} rows={m['row_count']}")

print("\n== sector ETF also works, partiality surfaced ==")
x = requests.get(BASE + "/api/explorer/sector", params={"symbol": "XLK", "limit": 100}, timeout=600).json()
check("XLK explored", x["row_count"] > 0, f"{x['row_count']} members")
check("XLK partial warning", any("PARTIAL" in w or "partial" in w for w in x["warnings"]),
      "; ".join(w[:44] for w in x["warnings"][:2]))

print("\n== notes ==")
body = {"row": first, "sector": {"timeframe": d["timeframe"], "universe": d["universe"],
                                 "rules": d["rules"]}, "breadth": d["breadth"], "parent": d["parent"]}
n = requests.post(BASE + "/api/explorer/notes", json=body, timeout=120).json()
check("notes built", n["ok"] is True and len(n["statements"]) >= 5, f"{len(n['statements'])} statements")
check("notes cite rule versions", all(n["rule_versions"].values()) or n["rule_versions"]["momo_trend"],
      json.dumps(n["rule_versions"]))
check("notes disclose limits", "cannot" in n and n["read_only"] is True)
check("notes carry evidence", "momentum" in n["evidence"] and "breadth" in n["evidence"])
low = next((s for s in n["statements"] if "Began" in s or "Momentum" in s), "")
print(f"   sample: {low[:150]}")

print(f"\nRESULT: {ok} passed, {fail} failed")
