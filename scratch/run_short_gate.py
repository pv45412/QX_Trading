"""Does a MARKET REGIME GATE rescue the short side?

Shorts lose -0.6036 R because equities drift up (+38% over the window). The
hypothesis: only take shorts when the BROAD MARKET is itself falling. Then the
drift is no longer against the position.

Gate definition (point-in-time, no lookahead):
  short allowed when the equal-weight market proxy is BELOW its own 50-day mean.

Tested across FOUR chronological folds. The earlier regime test on the LONG side
was only WEAK (2/4 folds), so this must clear a higher bar: the gate has to
improve the short side in a MAJORITY of folds, not just on the pooled number.
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
        return {"n": 0, "mean_r": None, "win_rate": None, "pf": None, "final_r": None}
    r = [t.net_r for t in trades]
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gl = abs(sum(losses))
    return {"n": len(r), "mean_r": round(sum(r) / len(r), 4),
            "win_rate": round(len(wins) / len(r), 4),
            "pf": round(sum(wins) / gl, 3) if gl > 0 else None,
            "final_r": round(sum(r), 1)}


universe, _ = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
shorts = [t for t in run["trades"] if t.direction == "SHORT"]
print(f"{len(bars_only)} symbols, {len(shorts)} SHORT trades\n")

# ---- point-in-time market proxy ----
by_date: dict[str, list[float]] = defaultdict(list)
for symbol, bars in bars_only.items():
    for bar in bars:
        if bar.get("date"):
            by_date[bar["date"]].append(bar["close"])
dates_sorted = sorted(by_date)
level = {d: sum(by_date[d]) / len(by_date[d]) for d in dates_sorted}
ma50: dict[str, float] = {}
for i, d in enumerate(dates_sorted):
    if i >= 50:
        ma50[d] = sum(level[dates_sorted[j]] for j in range(i - 50, i)) / 50


def market_below(date):
    """True when the proxy is under its 50-day mean: a falling market."""
    return bool(level.get(date) and ma50.get(date) and level[date] < ma50[date])


gated = [t for t in shorts if t.entry_date and market_below(t.entry_date)]

print("=" * 92)
print("A. THE GATE, POOLED")
print("=" * 92)
print(f"  {'variant':<34} {'n':>6} {'mean R':>9} {'win%':>7} {'PF':>7} {'final R':>9}")
print("  " + "-" * 78)
for label, subset in (("SHORT all (ungated)", shorts), ("SHORT only when market down", gated)):
    s = stats(subset)
    print(f"  {label:<34} {s['n']:>6} {str(s['mean_r']):>9} "
          f"{(s['win_rate'] or 0)*100:>6.1f}% {str(s['pf']):>7} {str(s['final_r']):>9}")

pooled = stats(gated)
ungated = stats(shorts)
print()
if pooled["mean_r"] is not None and ungated["mean_r"] is not None:
    delta = pooled["mean_r"] - ungated["mean_r"]
    print(f"  improvement from gating: {delta:+.4f} R/trade")
    print(f"  trades removed         : {len(shorts) - len(gated)} "
          f"({(1 - len(gated)/len(shorts))*100:.1f}% of shorts)")

print()
print("=" * 92)
print("B. FOUR CHRONOLOGICAL FOLDS — the gate must help in a MAJORITY")
print("=" * 92)
all_dates = sorted({t.entry_date for t in shorts if t.entry_date})
bounds = [all_dates[int(len(all_dates) * f)] for f in (0.0, 0.25, 0.5, 0.75)] + [all_dates[-1]]

print(f"  {'fold':<6} {'window':<26} {'ungated n':>10} {'ungated R':>10} "
      f"{'gated n':>9} {'gated R':>9} {'better?':>9}")
print("  " + "-" * 84)
wins = 0
folds = []
for i in range(4):
    low, high = bounds[i], bounds[i + 1]
    window = [t for t in shorts if t.entry_date and low <= t.entry_date <= high]
    wgated = [t for t in window if market_below(t.entry_date)]
    a, b = stats(window), stats(wgated)
    better = "-"
    if a["mean_r"] is not None and b["mean_r"] is not None:
        if b["mean_r"] > a["mean_r"]:
            better = "YES"
            wins += 1
        else:
            better = "no"
    folds.append({"window": [low, high], "ungated": a, "gated": b})
    print(f"  {i+1:<6} {low} -> {high} {a['n']:>10} {str(a['mean_r']):>10} "
          f"{b['n']:>9} {str(b['mean_r']):>9} {better:>9}")

print()
print("=" * 92)
print("C. VERDICT")
print("=" * 92)
print(f"  gate improves the short side in {wins}/4 folds")
if wins >= 3:
    print("  -> ROBUST. The regime gate is worth building.")
elif wins == 2:
    print("  -> WEAK. Improves half the folds; not reliable enough to ship as a fix.")
else:
    print("  -> NOT ROBUST. The pooled improvement is concentrated in one period.")

# Also report: does the gate ever make shorts PROFITABLE?
positive_folds = sum(1 for f in folds if f["gated"]["mean_r"] is not None
                     and f["gated"]["mean_r"] > 0)
print(f"  gated shorts are PROFITABLE in {positive_folds}/4 folds")
print()
print("  For reference, the pooled gated figure is what a user would see:")
if pooled["mean_r"] is not None:
    print(f"     gated shorts: {pooled['mean_r']} R over {pooled['n']} trades "
          f"(vs {ungated['mean_r']} ungated)")

with open(r"C:\Project\2026\scratch\backtest_short_gate.json", "w", encoding="utf-8") as handle:
    json.dump({"pooled_ungated": ungated, "pooled_gated": pooled,
               "folds": folds, "folds_improved": wins}, handle, indent=2)
print("\nwritten: scratch/backtest_short_gate.json")
