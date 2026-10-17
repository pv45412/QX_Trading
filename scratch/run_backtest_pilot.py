"""Pilot: prove the machinery, then measure. 20 symbols first."""
import json
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, metrics, simulate  # noqa: E402

PILOT = ["AAPL", "MSFT", "NVDA", "AMD", "AVGO", "META", "AMZN", "GOOGL", "TSLA", "NFLX",
         "JPM", "BAC", "XOM", "CVX", "UNH", "LLY", "COST", "WMT", "HD", "CAT"]

print("=" * 78)
print("STEP 1 — universe audit (20-symbol pilot)")
print("=" * 78)
started = time.time()
universe, report = historical.build_universe(symbols=PILOT)
print(f"  scanned {report.scanned}, loaded {report.loaded_count} "
      f"({time.time() - started:.1f}s)")
if report.excluded:
    for reason, symbols in report.excluded.items():
        print(f"  excluded ({reason}): {symbols}")
print(f"  loaded: {', '.join(sorted(universe))}")

print()
print("=" * 78)
print("STEP 2 — CAUSALITY (the gate: no lookahead)")
print("=" * 78)
causal_ok = 0
for symbol, barset in list(universe.items())[:4]:
    check = simulate.verify_causality(barset.bars, samples=5)
    status = "CAUSAL" if check["ok"] else "*** NON-CAUSAL ***"
    print(f"  {symbol:<6} {status}  indices={check['checked_indices']}")
    if not check["ok"]:
        for mismatch in check["mismatches"][:3]:
            print(f"        {mismatch}")
    causal_ok += 1 if check["ok"] else 0
print(f"  -> {causal_ok}/4 causal")

print()
print("=" * 78)
print("STEP 3 — simulate both exit policies")
print("=" * 78)
bars_only = {s: b.bars for s, b in universe.items()}
started = time.time()
study_run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
stopped_run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STOP)
print(f"  study-exit : {study_run['trade_count']} trades, "
      f"{study_run['error_count']} errors  ({time.time() - started:.1f}s)")
print(f"  stop-enforced: {stopped_run['trade_count']} trades, "
      f"{stopped_run['error_count']} errors")

study_stats = metrics.summarize(study_run)
stopped_stats = metrics.summarize(stopped_run)

print()
print("=" * 78)
print("STEP 4 — what the trades ACTUALLY resolved to")
print("=" * 78)
rr = study_stats.get("realized_r") or {}
if rr:
    print(f"  realized R  mean={rr['mean']}  median={rr['median']}  "
          f"p10={rr['p10']}  p90={rr['p90']}")
    print(f"              best={rr['best']}  worst={rr['worst']}")
print(f"  win rate    : {study_stats.get('win_rate')}")
print(f"  expectancy  : {study_stats.get('expectancy_r')} R per trade")
print(f"  profit factor: {study_stats.get('profit_factor')}")

print()
print("=" * 78)
print("STEP 5 — MAE: is the displayed ATR stop survivable?")
print("=" * 78)
mae = study_stats.get("mae") or {}
if mae:
    print(f"  MAE mean={mae['mean']}  median={mae['median']}  p05={mae['p05']}  "
          f"worst={mae['worst']}")
    print(f"  share of trades that went beyond -1R: {mae['pct_beyond_1r']}")
    print(f"  share of trades that went beyond -2R: {mae['pct_beyond_2r']}")

print()
print("=" * 78)
print("STEP 6 — exit policy comparison (the F23 question)")
print("=" * 78)
comparison = metrics.compare_policies(study_stats, stopped_stats)
for key in ("study_exit_net_mean_r", "stop_enforced_net_mean_r",
            "study_exit_p05_mae", "stop_enforced_p05_mae", "verdict"):
    print(f"  {key:<28} {comparison[key]}")

print()
print("=" * 78)
print("STEP 7 — baseline: buy and hold the same 20 symbols")
print("=" * 78)
baseline = metrics.buy_and_hold(bars_only)
print(f"  symbols={baseline['symbols']}  mean={baseline['mean_return']}  "
      f"median={baseline['median_return']}  positive={baseline['pct_positive']}")

print()
print("=" * 78)
print("STEP 8 — exit reason breakdown + drawdown")
print("=" * 78)
print(f"  study exit reasons : {study_stats.get('exit_reasons')}")
print(f"  stop exit reasons  : {stopped_stats.get('exit_reasons')}")
print(f"  study drawdown     : {study_stats.get('drawdown')}")
print(f"  bars held (median) : {(study_stats.get('bars_held') or {}).get('median')}")

with open(r"C:\Project\2026\scratch\backtest_pilot.json", "w", encoding="utf-8") as handle:
    json.dump({"universe": report.as_dict(), "study": study_stats,
               "stopped": stopped_stats, "comparison": comparison,
               "baseline": baseline,
               "sample_trades": [t.as_dict() for t in study_run["trades"][:15]]},
              handle, indent=2, default=str)
print("\nwritten: scratch/backtest_pilot.json")
