"""Phase B regression tests — F06, F08, F09, F11 (and F14 which F06 unblocks).

Correct behaviour only. Run: python scratch/test_phase_b.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import types
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


print("== F08: unsupported timeframe is rejected, not silently substituted ==")
from qx.explorer import service  # noqa: E402

for bad in ("7m", "weekly", "1h", "banana"):
    try:
        service.explore("SMH", timeframe=bad, view="all", limit=1)
        check(f"F08-{bad}", f"timeframe {bad!r} is rejected", False, "accepted silently")
    except ValueError:
        check(f"F08-{bad}", f"timeframe {bad!r} is rejected", True)

check("F08-1d", "1d maps to daily bars", service._normalise_interval("1d") == "1d")
check("F08-15m", "15m maps to a 15-minute interval", service._normalise_interval("15m") == "15m")

print("\n== F06: bars and quotes carry OBSERVATION time, distinct from retrieval ==")
from qx.scanner.engine import MarketData  # noqa: E402

market = MarketData()
bars, src = market.bars("SPY")
check("F06a", "every bar carries a date", all(b.get("date") for b in bars), f"src={src}")
check("F06b", "bars declare completion", all("bar_completed" in b for b in bars))
check("F06c", "bars declare their interval", all(b.get("interval") for b in bars),
      f"interval={bars[-1].get('interval')}")
check("F06d", "daily bar dates are ascending", [b["date"] for b in bars] == sorted(b["date"] for b in bars))
quote, qsrc = market.quote("SPY")
check("F06e", "quote carries an observation timestamp", bool((quote or {}).get("timestamp")),
      f"src={qsrc}")

fresh = market.freshness("SPY")
check("F06f", "freshness is classified from the quote's own time",
      fresh.get("status") in ("FRESH", "WARN_LATENCY", "STALE_BLOCKED"),
      json.dumps(fresh)[:120])
check("F06g", "freshness reports a real age in seconds",
      isinstance(fresh.get("age_seconds"), (int, float)) and fresh["age_seconds"] >= 0,
      f"age={fresh.get('age_seconds')}")
check("F06h", "freshness states the threshold it used",
      fresh.get("max_threshold_seconds") is not None,
      f"threshold={fresh.get('max_threshold_seconds')}")

print("\n== F06/F14: freshness is UNKNOWN rather than assumed when time is absent ==")
undated = service._freshness({"last": 100, "realtime": False}, [{"close": 1, "date": None}],
                             "schwab", "cache")
check("F14a", "a quote with no timestamp is UNKNOWN, not fresh", undated["overall"] == "UNKNOWN",
      f"overall={undated['overall']}")
check("F14b", "cache-backed bars are marked CACHE_UNDATED",
      undated["bars"]["status"] == "CACHE_UNDATED", undated["bars"]["status"])
check("F14c", "an UNKNOWN-freshness row is not current", undated["is_current"] is False)

undated_quote = service._freshness({"last": 100, "realtime": True}, [{"close": 1, "date": "2026-10-07"}],
                                   "schwab", "schwab")
check("F14d", "realtime=true alone does not make a quote FRESH", undated_quote["overall"] == "UNKNOWN",
      f"overall={undated_quote['overall']}")

old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=600)).isoformat()
stale_q = service._freshness({"last": 1, "realtime": True, "timestamp": old},
                             [{"close": 1, "date": "2026-10-07"}], "schwab", "schwab")
check("F14e", "a 10-minute-old quote is not FRESH", stale_q["overall"] != "FRESH",
      f"overall={stale_q['overall']} quote={stale_q['quote']['status']}")

print("\n== F14/F06 gate: eligibility requires verifiable freshness ==")
cfg = service.DEFAULT_CONFIG
from types import SimpleNamespace as S  # noqa: E402

snap = S(warmup_ok=True, trade_direction=0, trade_atr=2, call_trigger_price=105,
         put_trigger_price=95, wave_high=104, wave_low=96, active_stop=None,
         call_ready=True, put_ready=False, bull_build=True, bear_build=False,
         bull_stack=True, bear_stack=False)
stale_row = {"price": 104, "freshness": stale_q, "direction": "LONG"}
gated = service.classify_entry(stale_row, snap, cfg)
check("F14f", "a stale-data row is not promoted to current readiness",
      gated.get("eligibility") not in ("ENTRY_ELIGIBLE",) or gated.get("state") == "PULLBACK_CANDIDATE",
      f"state={gated.get('state')} elig={gated.get('eligibility')}")
undated_row = {"price": 104, "freshness": undated, "direction": "LONG"}
gated2 = service.classify_entry(undated_row, snap, cfg)
check("F14g", "an undated row is not promoted to current readiness",
      gated2.get("eligibility") != "ENTRY_ELIGIBLE",
      f"state={gated2.get('state')} elig={gated2.get('eligibility')}")
fresh_row = {"price": 104, "freshness": {"overall": "FRESH", "is_current": True,
                                         "quote": {"reason": "ok"}, "bars": {"status": "OBSERVED"}},
             "direction": "LONG"}
unlocked = service.classify_entry(fresh_row, snap, cfg)
check("F14h", "a demonstrably FRESH row can still become eligible",
      unlocked.get("eligibility") == "ENTRY_ELIGIBLE",
      f"state={unlocked.get('state')} elig={unlocked.get('eligibility')}")

print("\n== F11: breadth denominator counts missing members ==")
rows = [{"momentum": "BULLISH", "trend": "BULLISH", "history_ok": True, "weight": 0.5},
        {"momentum": None, "trend": None, "history_ok": False, "weight": 0.5}]
b = service._breadth(rows, "ETF_REPORTED_TOP_HOLDINGS")
check("F11a", "denominator is the whole universe (2), not just classified (1)",
      b["denominator"] == 2, f"denominator={b['denominator']}")
check("F11b", "the member without data is counted as missing",
      b["missing_data"] == 1, f"missing={b['missing_data']} covered={b['covered']}")
check("F11c", "weight coverage reflects the unclassified half",
      b["weight_covered_pct"] == 50.0, f"weight_covered={b['weight_covered_pct']}")
check("F11d", "the note states missing members are counted, not excluded",
      "counted as missing" in b["denominator_note"], b["denominator_note"][:80])

print("\n== F09: staleness GATES current readiness ==")
import qx.explorer.ideas as ideas  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    original = ideas.SNAPSHOT_PATH
    ideas.SNAPSHOT_PATH = str(Path(d) / "snap.json")
    cand = {"symbol": "XYZ", "direction": "LONG", "bucket": "ready_now",
            "sector_symbol": "XLK", "rs_market": 5, "entry_state": "TRIGGER_CONFIRMED"}
    ideas._write_snapshot({"generated_at": (dt.datetime.now(dt.timezone.utc)
                                            - dt.timedelta(hours=12)).isoformat(),
                           "candidates": [cand], "universe": "ETF_REPORTED_TOP_HOLDINGS"})
    stale = ideas.ideas(view="ready_now", limit=100)
    check("F09a", "a stale snapshot does not report IDEAS_AVAILABLE",
          stale["verdict"] != "IDEAS_AVAILABLE", f"verdict={stale['verdict']}")
    check("F09b", "ready_now is EMPTIED when the snapshot is stale",
          stale["shown"] == 0, f"shown={stale['shown']}")
    check("F09c", "the staleness is stated explicitly",
          "stale" in (stale["message"] or "").lower(), (stale["message"] or "")[:80])
    hist = ideas.ideas(view="all", limit=100)
    check("F09d", "stale data stays BROWSABLE as history",
          hist["shown"] == 1, f"all-view shown={hist['shown']}")

    ideas._write_snapshot({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                           "candidates": [cand], "universe": "ETF_REPORTED_TOP_HOLDINGS"})
    fresh = ideas.ideas(view="ready_now", limit=100)
    check("F09e", "a fresh snapshot still reports ideas normally",
          fresh["verdict"] == "IDEAS_AVAILABLE" and fresh["shown"] == 1,
          f"verdict={fresh['verdict']} shown={fresh['shown']}")
    ideas.SNAPSHOT_PATH = original

Path(r"C:\Project\2026\scratch\phase_b_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
print(f"\nRESULT: {passed} passed, {failed} failed")
