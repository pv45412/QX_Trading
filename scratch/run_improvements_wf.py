"""Walk-forward the three improvements across MULTIPLE folds.

The deep dive found three changes that all improved the long side:
  regime filter  +0.4136 -> +0.6252 R
  top-3 ranking  +0.4136 -> +0.4831 R
  top-1 ranking  +0.4136 -> +0.7100 R

I over-claimed on a single split earlier in this project, so this runs FOUR
chronological folds and requires each improvement to hold in the MAJORITY of them.
An improvement that works in one fold is noise.
"""
import json
import os
import sys
from collections import defaultdict

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402

SAMPLE = 400


def stats(trades):
    if not trades:
        return {"n": 0, "mean_r": None, "win_rate": None, "profit_factor": None}
    r = [t.net_r for t in trades]
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gl = abs(sum(losses))
    return {"n": len(r), "mean_r": round(sum(r) / len(r), 4),
            "win_rate": round(len(wins) / len(r), 4),
            "profit_factor": round(sum(wins) / gl, 3) if gl > 0 else None}


universe, report = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
longs = [t for t in run["trades"] if t.direction == "LONG"]
print(f"{len(bars_only)} symbols, {len(longs)} LONG trades\n")

# Market proxy for the regime filter (point-in-time, from the same bars).
by_date: dict[str, list[float]] = defaultdict(list)
for symbol, bars in bars_only.items():
    for bar in bars:
        if bar.get("date"):
            by_date[bar["date"]].append(bar["close"])
dates_sorted = sorted(by_date)
level = {d: sum(by_date[d]) / len(by_date[d]) for d in dates_sorted}
ma50 = {}
for i, d in enumerate(dates_sorted):
    if i >= 50:
        ma50[d] = sum(level[dates_sorted[j]] for j in range(i - 50, i)) / 50


def market_up(date):
    return bool(level.get(date) and ma50.get(date) and level[date] > ma50[date])


# Prior 20-bar return, available at entry.
prior: dict[tuple[str, str], float] = {}
for symbol, bars in bars_only.items():
    for i, bar in enumerate(bars):
        if i >= 20 and bar.get("date"):
            base = bars[i - 20]["close"]
            if base > 0:
                prior[(symbol, bar["date"])] = bar["close"] / base - 1.0


def apply_variant(trades, *, regime=False, top_n=None):
    pool = [t for t in trades if (market_up(t.entry_date) if regime else True)]
    if top_n is None:
        return pool
    grouped: dict[str, list] = defaultdict(list)
    for trade in pool:
        grouped[trade.entry_date].append(trade)
    out = []
    for date, group in grouped.items():
        ranked = sorted(group, key=lambda t: prior.get((t.symbol, t.entry_date), -9),
                        reverse=True)
        out.extend(ranked[:top_n])
    return out


VARIANTS = {
    "LONG all": lambda t: apply_variant(t),
    "+ regime filter": lambda t: apply_variant(t, regime=True),
    "+ top 3/day": lambda t: apply_variant(t, top_n=3),
    "+ top 1/day": lambda t: apply_variant(t, top_n=1),
    "+ regime + top 3": lambda t: apply_variant(t, regime=True, top_n=3),
}

all_dates = sorted({t.entry_date for t in longs if t.entry_date})
bounds = [all_dates[int(len(all_dates) * f)] for f in (0.0, 0.25, 0.5, 0.75)] + [all_dates[-1]]

print("=" * 104)
print("WALK-FORWARD — mean R per fold. An improvement must hold in the MAJORITY of folds.")
print("=" * 104)
header = f"  {'variant':<20}" + "".join(f"{'fold ' + str(i+1):>15}" for i in range(4)) + f"{'all folds':>13}"
print(header)
print("  " + "-" * 100)

summary = {}
for name, apply_fn in VARIANTS.items():
    fold_values = []
    cells = []
    for i in range(4):
        low, high = bounds[i], bounds[i + 1]
        window = [t for t in longs if t.entry_date and low <= t.entry_date <= high]
        subset = apply_fn(window)
        s = stats(subset)
        fold_values.append(s["mean_r"])
        cells.append(f"{str(s['mean_r']):>8}({s['n']:>4})")
    overall = stats(apply_fn(longs))
    summary[name] = {"folds": fold_values, "overall": overall}
    print(f"  {name:<20}" + "".join(f"{c:>15}" for c in cells) +
          f"{str(overall['mean_r']):>9}({overall['n']:>4})")

print()
print("=" * 104)
print("VERDICT — does each improvement beat 'LONG all' consistently?")
print("=" * 104)
baseline_folds = summary["LONG all"]["folds"]
for name, data in summary.items():
    if name == "LONG all":
        continue
    wins = sum(1 for b, v in zip(baseline_folds, data["folds"])
               if v is not None and b is not None and v > b)
    positive = sum(1 for v in data["folds"] if v is not None and v > 0)
    verdict = ("ROBUST (beats baseline in 3-4 folds)" if wins >= 3 else
               "WEAK (beats baseline in 2 folds)" if wins == 2 else
               "NOT ROBUST (beats baseline in 0-1 folds)")
    print(f"  {name:<20} beats baseline in {wins}/4 folds, positive in {positive}/4  -> {verdict}")
    print(f"     folds: {data['folds']}")

with open(r"C:\Project\2026\scratch\backtest_improvements_wf.json", "w", encoding="utf-8") as handle:
    json.dump({"bounds": bounds, "summary": summary}, handle, indent=2)
print("\nwritten: scratch/backtest_improvements_wf.json")
