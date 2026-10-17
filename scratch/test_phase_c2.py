"""Phase C2 regression tests — F18 (membership relations) and F21 (coverage honesty)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
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


import qx.explorer.ideas as ideas  # noqa: E402
from qx.explorer import membership as M  # noqa: E402

print("== F21: completeness is reported per dimension ==")
smh = M.fetch_top_holdings("SMH", force=False)
xlk = M.fetch_top_holdings("XLK", force=False)

check("F21a", "a weighted universe reports member_completeness",
      smh.member_completeness in ("COMPLETE", "PARTIAL", "UNKNOWN"), smh.member_completeness)
check("F21b", "a weighted universe reports weight_completeness",
      smh.weight_completeness in ("COMPLETE", "PARTIAL"), smh.weight_completeness)
check("F21c", "SMH (99.9% of weight) is NOT partial",
      smh.is_partial is False, f"weight={smh.weight_covered_pct} partial={smh.is_partial}")
check("F21d", "XLK (84.6% of weight) IS partial",
      xlk.is_partial is True, f"weight={xlk.weight_covered_pct} partial={xlk.is_partial}")
check("F21e", "the coverage label names the sampling honestly",
      "sampled" in smh.coverage_label.lower(), smh.coverage_label)
check("F21f", "a partial universe says so in its label",
      "SAMPLED" in xlk.coverage_label or "sampled" in xlk.coverage_label.lower(),
      xlk.coverage_label)
check("F21g", "the completeness note explains which dimension was used",
      "weight coverage" in smh.completeness_note, smh.completeness_note)

# A classified universe must NOT be auto-partial merely for lacking weights.
classified = M.MembershipResult(
    symbol="TEST", universe=M.UNIVERSE_MEMBERS,
    rows=[M.HoldingRow(symbol="AAA"), M.HoldingRow(symbol="BBB")],
    status="OK", reported_total=2, has_weights=False, weight_covered_pct=None)
check("F21h", "a complete classified universe is NOT partial",
      classified.is_partial is False, f"partial={classified.is_partial}")
check("F21i", "its weight dimension is NOT_APPLICABLE, not PARTIAL",
      classified.weight_completeness == "NOT_APPLICABLE", classified.weight_completeness)
check("F21j", "its member dimension is COMPLETE",
      classified.member_completeness == "COMPLETE", classified.member_completeness)
check("F21k", "the note says weights do not apply",
      "no weights" in classified.completeness_note.lower(), classified.completeness_note)

partial_classified = M.MembershipResult(
    symbol="TEST2", universe=M.UNIVERSE_MEMBERS,
    rows=[M.HoldingRow(symbol="AAA")], status="OK", reported_total=5,
    has_weights=False, weight_covered_pct=None)
check("F21l", "a genuinely short classified universe IS partial",
      partial_classified.is_partial is True, f"partial={partial_classified.is_partial}")

unknown_classified = M.MembershipResult(
    symbol="TEST3", universe=M.UNIVERSE_MEMBERS,
    rows=[M.HoldingRow(symbol="AAA")], status="OK", reported_total=None,
    has_weights=False, weight_covered_pct=None)
check("F21m", "an unknown total reports UNKNOWN rather than pretending",
      unknown_classified.member_completeness == "UNKNOWN"
      and unknown_classified.is_partial is True,
      f"member={unknown_classified.member_completeness} partial={unknown_classified.is_partial}")

check("F21n", "as_dict exposes both dimensions",
      "member_completeness" in smh.as_dict() and "weight_completeness" in smh.as_dict()
      and "coverage_label" in smh.as_dict())


print("\n== F18: membership is a relation, not a single field ==")


def make_candidate(symbol, memberships):
    cand = {"symbol": symbol, "sector_symbol": None, "sector_name": None,
            "weight": None, "rank": None, "rs_vs_parent": None,
            "memberships": memberships}
    ideas._resolve_primary_parent(cand)
    return cand


# A name held by both XLK (small weight) and SMH (large weight).
multi = make_candidate("NVDA", [
    {"sector_symbol": "XLK", "sector_name": "Technology", "weight": 0.15, "rank": 1,
     "rs_vs_parent": 2.0},
    {"sector_symbol": "SMH", "sector_name": "Semiconductors", "weight": 0.19, "rank": 1,
     "rs_vs_parent": 5.0},
])
check("F18a", "every membership is retained",
      len(multi["memberships"]) == 2, f"memberships={len(multi['memberships'])}")
check("F18b", "sector_symbols lists all parents",
      multi["sector_symbols"] == ["SMH", "XLK"], multi["sector_symbols"])
check("F18c", "primary parent is the HIGHEST-WEIGHT membership (SMH 19% > XLK 15%)",
      multi["sector_symbol"] == "SMH", f"primary={multi['sector_symbol']}")
check("F18d", "exactly one membership is marked primary",
      sum(1 for m in multi["memberships"] if m.get("is_primary")) == 1)
check("F18e", "the filter matches the NON-primary parent too (XLK)",
      ideas._matches_sector(multi, "XLK") is True)
check("F18f", "the filter matches the primary parent (SMH)",
      ideas._matches_sector(multi, "SMH") is True)
check("F18g", "the filter rejects an unrelated sector",
      ideas._matches_sector(multi, "XLE") is False)
check("F18h", "also_in lists the other parents",
      multi["also_in"] == ["XLK"], multi["also_in"])
check("F18i", "the policy is declared on the candidate",
      "deterministic" in (multi.get("primary_parent_policy") or "").lower(),
      (multi.get("primary_parent_policy") or "")[:60])

# Determinism: same input, same primary, regardless of order.
reordered = make_candidate("NVDA", [
    {"sector_symbol": "SMH", "sector_name": "Semiconductors", "weight": 0.19, "rank": 1,
     "rs_vs_parent": 5.0},
    {"sector_symbol": "XLK", "sector_name": "Technology", "weight": 0.15, "rank": 1,
     "rs_vs_parent": 2.0},
])
check("F18j", "primary parent does not depend on scan order",
      reordered["sector_symbol"] == multi["sector_symbol"],
      f"{reordered['sector_symbol']} vs {multi['sector_symbol']}")

# Weight tie -> strongest parent-relative RS wins.
tie = make_candidate("TIE", [
    {"sector_symbol": "AAA", "sector_name": "A", "weight": 0.10, "rank": 1, "rs_vs_parent": 1.0},
    {"sector_symbol": "BBB", "sector_name": "B", "weight": 0.10, "rank": 2, "rs_vs_parent": 9.0},
])
check("F18k", "a weight tie breaks on stronger parent-relative RS",
      tie["sector_symbol"] == "BBB", f"primary={tie['sector_symbol']}")

# No weights at all -> still deterministic.
noweight = make_candidate("NW", [
    {"sector_symbol": "ZZZ", "sector_name": "Z", "weight": None, "rank": None, "rs_vs_parent": None},
    {"sector_symbol": "AAA", "sector_name": "A", "weight": None, "rank": None, "rs_vs_parent": None},
])
check("F18l", "with no weights the tie-break is alphabetical and stable",
      noweight["sector_symbol"] == "AAA", f"primary={noweight['sector_symbol']}")

single = make_candidate("SOLO", [
    {"sector_symbol": "XLF", "sector_name": "Financials", "weight": 0.05, "rank": 3,
     "rs_vs_parent": 0.5}])
check("F18m", "a single-membership name is handled",
      single["sector_symbol"] == "XLF" and single["also_in"] == []
      and single["membership_count"] == 1, json.dumps(single["also_in"]))

print("\n== F18: end to end over the live snapshot ==")
data = ideas.ideas(view="all", limit=500)
if data.get("has_snapshot"):
    multi_rows = [c for c in data["ideas"] if (c.get("membership_count") or 1) > 1]
    print(f"   snapshot has {len(multi_rows)} multi-membership names")
    check("F18n", "the response declares the primary-parent policy",
          "deterministic" in (data.get("primary_parent_policy") or "").lower(),
          (data.get("primary_parent_policy") or "")[:60])
    if multi_rows:
        sample = multi_rows[0]
        other = [s for s in sample["sector_symbols"] if s != sample["sector_symbol"]][0]
        filtered = ideas.ideas(view="all", sector=other, limit=500)
        found = any(c["symbol"] == sample["symbol"] for c in filtered["ideas"])
        check("F18o", f"filtering the NON-primary parent ({other}) finds {sample['symbol']}",
              found, f"symbols={[c['symbol'] for c in filtered['ideas']][:6]}")
    else:
        check("F18o", "no multi-membership names to verify (informational)", True)
else:
    check("F18n", "no snapshot available (informational)", True)
    check("F18o", "no snapshot available (informational)", True)

Path(r"C:\Project\2026\scratch\phase_c2_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print(f"\nRESULT: {passed} passed, {failed} failed")
