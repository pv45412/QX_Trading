"""Scratch: end-to-end verification of the explorer service on live data."""
import json
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer import UNIVERSE_HOLDINGS, UNIVERSE_MEMBERS, catalog, explore  # noqa: E402
from qx.explorer import membership as M  # noqa: E402

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print("== 1. holdings parsing (offline fixture, no network) ==")
FIXTURE = """
<table><thead><tr><th>#</th><th>Symbol</th><th>Name</th><th>Weight</th><th>Shares</th></tr></thead><tbody>
<tr class="svelte-77tdkt"><td>1</td><td><a href="/stocks/nvda/">NVDA</a></td><td>NVIDIA Corporation</td><td>15.67%</td><td>87,053,599</td></tr>
<tr class="svelte-77tdkt"><td>2</td><td><a href="/stocks/tsm/">TSM</a></td><td>Taiwan Semiconductor</td><td>9.45%</td><td>15,066,890</td></tr>
<tr class="svelte-77tdkt"><td>3</td><td><a href="/stocks/brk-b/">BRK.B</a></td><td>Berkshire Hathaway</td><td>1.10%</td><td>1,000</td></tr>
<tr class="svelte-77tdkt"><td>24</td><td>IXPZ6</td><td>XAE ENERGY DEC26</td><td>-0.00%</td><td>62,300</td></tr>
</tbody></table><div>78 holdings</div><div>25 Holdings</div>
"""
rows, reported = M.parse_holdings_table(FIXTURE)
check("parsed 4 data rows", len(rows) == 4, f"{len(rows)}")
check("ticker parsed", rows[0].symbol == "NVDA", rows[0].symbol)
check("company parsed", rows[0].name == "NVIDIA Corporation", rows[0].name)
check("weight parsed as fraction", abs(rows[0].weight - 0.1567) < 1e-9, rows[0].weight)
check("shares parsed", rows[0].shares == 87053599.0, rows[0].shares)
check("reported total takes the LARGER claim (78 not 25)", reported == 78, reported)
kept, dropped = M.filter_equity_rows(rows)
check("futures line excluded", dropped == 1 and len(kept) == 3, f"kept={len(kept)} dropped={dropped}")
check("ADR preserved (TSM)", any(r.symbol == "TSM" for r in kept))
check("share-class dot preserved (BRK.B)", any(r.symbol == "BRK.B" for r in kept))

print("\n== 2. catalog ==")
cat = catalog()
check("11 sectors + industries", len(cat["sectors"]) == 11 and len(cat["industries"]) >= 10,
      f"{len(cat['sectors'])} sectors, {len(cat['industries'])} industries")
check("SMH present as an industry", any(i["symbol"] == "SMH" for i in cat["industries"]))
check("two universe choices offered", len(cat["universes"]) == 2,
      [u["label"] for u in cat["universes"]])

print("\n== 3. live membership (SMH) ==")
result = M.fetch_top_holdings("SMH", force=True)
check("SMH holdings fetched", result.status == "OK" and result.count >= 20,
      f"status={result.status} count={result.count}")
check("weights present", result.has_weights is True)
check("weight coverage reported", result.weight_covered_pct is not None,
      f"{result.weight_covered_pct}%")
check("SMH is representative (coverage >= 95%)", result.is_partial is False,
      f"{result.weight_covered_pct}%")
check("holdings date is NOT faked", result.holdings_as_of is None,
      "retrieval time is not a holdings date")

print("\n== 4. broad-fund partiality is surfaced (XLK) ==")
xlk = M.fetch_top_holdings("XLK", force=True)
check("XLK flagged partial", xlk.is_partial is True,
      f"coverage={xlk.weight_covered_pct}% total={xlk.reported_total}")
check("XLK warning mentions partial", bool(xlk.warning) and "partial" in xlk.warning.lower(),
      (xlk.warning or "")[:70])

print("\n== 5. classified members are a SEPARATE universe (never substituted) ==")
members = M.classified_members("SMH")
check("missing classified file -> explicit unavailable, not a fake list",
      members.status == "MEMBERSHIP_UNAVAILABLE" and members.count == 0,
      members.status)
check("universe identity is distinct", members.universe == UNIVERSE_MEMBERS)
try:
    M.resolve_universe("SMH", "NOT_A_UNIVERSE")
    check("unknown universe rejected", False)
except ValueError:
    check("unknown universe rejected", True)

print("\n== 6. live explore: SMH ==")
started = time.time()
data = explore("SMH", UNIVERSE_HOLDINGS, limit=60)
elapsed = time.time() - started
check("explore returned", data["symbol"] == "SMH" and data["row_count"] > 0,
      f"{data['row_count']} members in {elapsed:.1f}s")
check("parent carries momo/trend state", data["parent"]["momentum"] is not None,
      f"parent momo={data['parent']['momentum']} trend={data['parent']['trend']}")
check("breadth has an explicit denominator", data["breadth"]["denominator"] > 0,
      json.dumps(data["breadth"])[:150])
check("breadth reports weight coverage", data["breadth"]["weight_covered_pct"] is not None,
      f"{data['breadth']['weight_covered_pct']}%")
check("rule versions declared", all(data["rules"].values()),
      json.dumps(data["rules"]))
check("all eight views counted", len(data["views"]) == 8,
      ", ".join(f"{v['id']}={v['count']}" for v in data["views"][:4]))

aligned = [r for r in data["rows"] if r.get("momentum_up_and_trend_up")]
print(f"   aligned members in the default view: {len(aligned)}")
for r in aligned[:6]:
    print(f"      {r['symbol']:<6} momo={r['momentum']:<8} trend={r['trend']:<8} "
          f"phase={r.get('phase')} entry={r['entry']['state']:<18} "
          f"RS20 parent={r['rs_vs_parent'].get('20d')} mkt={r['rs_vs_market'].get('20d')}")
check("every default-view row is UP/UP",
      all(r["momentum"] == "BULLISH" and r["trend"] == "BULLISH" for r in data["rows"]),
      f"{len(data['rows'])} rows")

print("\n== 7. alignment must NEVER produce EXECUTABLE ==")
from qx.explorer.service import ENTRY_TRIGGER  # noqa: E402
states = {r["entry"]["state"] for r in data["rows"]}
check("no row is labelled EXECUTABLE", "EXECUTABLE" not in states, sorted(states))
check("alignment alone caps at TRIGGER_CONFIRMED",
      not any(s in ("EXECUTABLE", "SUBMITTED", "FILLED") for s in states), sorted(states))

print("\n== 8. views partition correctly ==")
newly = explore("SMH", UNIVERSE_HOLDINGS, view="newly_aligned", limit=60)
check("newly-aligned view returns only newly aligned",
      all(r["newly_aligned"] for r in newly["rows"]), f"{newly['shown']} rows")
bearish = explore("SMH", UNIVERSE_HOLDINGS, view="bearish", limit=60)
check("bearish view returns only DOWN/DOWN",
      all(r["momentum"] == "BEARISH" and r["trend"] == "BEARISH" for r in bearish["rows"]),
      f"{bearish['shown']} rows")
allv = explore("SMH", UNIVERSE_HOLDINGS, view="all", limit=200)
check("all view >= aligned view", allv["shown"] >= data["shown"],
      f"all={allv['shown']} aligned={data['shown']}")
check("view counts reported before filtering",
      all(isinstance(v["count"], int) for v in allv["views"]))

print("\n== 9. breadth arithmetic reconciles ==")
b = allv["breadth"]
covered = [r for r in allv["rows"] if r.get("history_ok") and r.get("momentum")]
check("denominator >= covered", b["denominator"] >= b["covered"],
      f"denom={b['denominator']} covered={b['covered']}")
expected = round(sum(1 for r in allv["rows"] if r.get("history_ok") and r.get("aligned_up")) / b["covered"], 4) if b["covered"] else None
check("aligned_pct matches the covered universe", expected is None or abs(b["aligned_pct"] - expected) < 1e-6,
      f"reported={b['aligned_pct']} recomputed={expected}")

print("\n== 10. a sector ETF also works ==")
xlkdata = explore("XLK", UNIVERSE_HOLDINGS, limit=40)
check("XLK explored", xlkdata["row_count"] > 0, f"{xlkdata['row_count']} members")
check("XLK partial warning surfaced",
      any("PARTIAL" in w for w in xlkdata["warnings"]),
      "; ".join(w[:48] for w in xlkdata["warnings"][:2]))

print(f"\nRESULT: {ok} passed, {fail} failed  ({elapsed:.1f}s for the last explore)")
