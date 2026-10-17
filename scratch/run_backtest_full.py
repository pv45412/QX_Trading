"""Full-universe backtest over every cleaned symbol, both exit policies."""
import json
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, metrics, simulate  # noqa: E402

print("=" * 78)
print("UNIVERSE AUDIT — every cached symbol")
print("=" * 78)
started = time.time()
universe, report = historical.build_universe(window="2y")
audit = report.as_dict()
print(f"  scanned            : {audit['scanned']}")
print(f"  loaded (clean)     : {audit['loaded']}")
print(f"  excluded (total)   : {audit['excluded_total']}   ({time.time() - started:.1f}s)")
for reason, count in audit["excluded_by_reason"].items():
    examples = ", ".join(audit["excluded_examples"][reason][:5])
    print(f"     {count:>5}  {reason}")
    print(f"            e.g. {examples}")

bars_only = {s: b.bars for s, b in universe.items()}
print(f"\n  symbols entering the simulation: {len(bars_only)}")

print()
print("=" * 78)
print("SIMULATING — study exit")
print("=" * 78)
started = time.time()
study_run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
print(f"  {study_run['trade_count']} trades, {study_run['error_count']} errors "
      f"({time.time() - started:.1f}s)")

print()
print("=" * 78)
print("SIMULATING — stop enforced")
print("=" * 78)
started = time.time()
stopped_run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STOP)
print(f"  {stopped_run['trade_count']} trades, {stopped_run['error_count']} errors "
      f"({time.time() - started:.1f}s)")

study_stats = metrics.summarize(study_run)
stopped_stats = metrics.summarize(stopped_run)
baseline = metrics.buy_and_hold(bars_only)
comparison = metrics.compare_policies(study_stats, stopped_stats)

print()
print("=" * 78)
print("RESULT 1 — what trades ACTUALLY resolve to (study exit)")
print("=" * 78)
rr = study_stats["realized_r"]
print(f"  trades          : {study_stats['trade_count']} across "
      f"{study_stats['symbols_traded']} symbols")
print(f"  realized R mean : {rr['mean']}      <-- app displays a constant 2.00")
print(f"  realized R med  : {rr['median']}")
print(f"  p10 / p90       : {rr['p10']} / {rr['p90']}")
print(f"  best / worst    : {rr['best']} / {rr['worst']}")
print(f"  win rate        : {study_stats['win_rate']}")
print(f"  expectancy      : {study_stats['expectancy_r']} R per trade")
print(f"  profit factor   : {study_stats['profit_factor']}")

print()
print("=" * 78)
print("RESULT 2 — MAE: would the DISPLAYED stop have been hit?")
print("=" * 78)
mae = study_stats["mae"]
print(f"  median adverse excursion : {mae['median']} R")
print(f"  p05 (tail)               : {mae['p05']} R")
print(f"  worst                    : {mae['worst']} R")
print(f"  trades beyond -1R        : {mae['pct_beyond_1r']:.1%}   "
      f"<-- the displayed stop sits at exactly 1R")
print(f"  trades beyond -2R        : {mae['pct_beyond_2r']:.1%}")

print()
print("=" * 78)
print("RESULT 3 — study exit vs stop enforced (the F23 decision)")
print("=" * 78)
print(f"  study exit  net mean R : {comparison['study_exit_net_mean_r']}")
print(f"  stop enforced net mean : {comparison['stop_enforced_net_mean_r']}")
print(f"  study p05 MAE          : {comparison['study_exit_p05_mae']}")
print(f"  stop  p05 MAE          : {comparison['stop_enforced_p05_mae']}")
print(f"  VERDICT                : {comparison['verdict']}")

print()
print("=" * 78)
print("RESULT 4 — baseline and risk")
print("=" * 78)
print(f"  buy & hold mean   : {baseline['mean_return']:.1%} over the window")
print(f"  buy & hold median : {baseline['median_return']:.1%}")
print(f"  buy & hold % up   : {baseline['pct_positive']:.1%}")
print(f"  strategy max DD   : {study_stats['drawdown']['max_drawdown_r']} R")
print(f"  strategy final    : {study_stats['drawdown']['final_r']} R")
print(f"  median bars held  : {study_stats['bars_held']['median']}")
print(f"  exit reasons      : {study_stats['exit_reasons']}")

with open(r"C:\Project\2026\scratch\backtest_full.json", "w", encoding="utf-8") as handle:
    json.dump({"universe": audit, "study": study_stats, "stopped": stopped_stats,
               "comparison": comparison, "baseline": baseline},
              handle, indent=2, default=str)
print("\nwritten: scratch/backtest_full.json")
