"""Is the filter edge ALPHA, or just BETA in a bull market?

Boyd phase 3 literally means "strong uptrend". Buy-and-hold returned ~+40% over the
same window. So "filter to phase 3" may simply be "buy strength while everything
rises" — which is beta, not skill, and would invert in a downtrend.

The discriminator: examine the SHORT side. If the edge is market direction, LONG
trades win and SHORT trades lose. If the edge is real signal, SHORT trades in a
downtrend should also work.
"""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402
from qx.explorer import market_phases, momo_trend  # noqa: E402

SAMPLE = 400


def stats(trades):
    if not trades:
        return {"n": 0, "mean_r": None, "median_r": None, "win_rate": None,
                "profit_factor": None, "final_r": None}
    r = [t.net_r for t in trades]
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    ordered = sorted(r)
    gl = abs(sum(losses))
    return {"n": len(r), "mean_r": round(sum(r) / len(r), 4),
            "median_r": round(ordered[len(ordered) // 2], 4),
            "win_rate": round(len(wins) / len(r), 4),
            "profit_factor": round(sum(wins) / gl, 3) if gl > 0 else None,
            "final_r": round(sum(r), 1)}


universe, report = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
trades = run["trades"]
print(f"{len(trades)} trades across {len(bars_only)} symbols\n")

context: dict[str, dict] = {}
for symbol, bars in bars_only.items():
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    times = [b.get("date") or "" for b in bars]
    try:
        context[symbol] = {
            "momo": {m.index: m for m in momo_trend.evaluate_series(highs, lows, closes, times)},
            "phase": {p.index: p for p in market_phases.evaluate_series(closes, times)},
        }
    except Exception:  # noqa: BLE001
        continue


def phase_of(trade):
    ctx = context.get(trade.symbol)
    if not ctx:
        return None
    p = ctx["phase"].get(trade.entry_index)
    return getattr(p, "phase", None) if p else None


print("=" * 90)
print("ALPHA OR BETA?  Long vs short, by Boyd phase")
print("=" * 90)
print(f"  {'group':<34} {'n':>6} {'mean R':>9} {'median R':>10} {'win%':>7} {'PF':>7} {'final R':>9}")
print("  " + "-" * 86)

groups = [
    ("LONG  all", lambda t: t.direction == "LONG"),
    ("LONG  phase 3", lambda t: t.direction == "LONG" and phase_of(t) == 3),
    ("LONG  phase 1 (downtrend)", lambda t: t.direction == "LONG" and phase_of(t) == 1),
    ("SHORT all", lambda t: t.direction == "SHORT"),
    ("SHORT phase 3", lambda t: t.direction == "SHORT" and phase_of(t) == 3),
    ("SHORT phase 1 (downtrend)", lambda t: t.direction == "SHORT" and phase_of(t) == 1),
]
for name, predicate in groups:
    subset = [t for t in trades if predicate(t)]
    s = stats(subset)
    if not s["n"]:
        print(f"  {name:<34} {0:>6}")
        continue
    pf = s["profit_factor"] if s["profit_factor"] is not None else "-"
    print(f"  {name:<34} {s['n']:>6} {s['mean_r']:>9} {s['median_r']:>10} "
          f"{s['win_rate']*100:>6.1f}% {str(pf):>7} {s['final_r']:>9}")

print()
print("=" * 90)
print("READING")
print("=" * 90)
long_p3 = stats([t for t in trades if t.direction == "LONG" and phase_of(t) == 3])
short_p3 = stats([t for t in trades if t.direction == "SHORT" and phase_of(t) == 3])
long_p1 = stats([t for t in trades if t.direction == "LONG" and phase_of(t) == 1])
short_p1 = stats([t for t in trades if t.direction == "SHORT" and phase_of(t) == 1])

if short_p3["n"] >= 20 and short_p3["mean_r"] is not None:
    if short_p3["mean_r"] > 0:
        print(f"  SHORTs in phase 3 are ALSO positive ({short_p3['mean_r']}R over "
              f"{short_p3['n']} trades) -> the edge is not purely market direction.")
    else:
        print(f"  SHORTs in phase 3 LOSE ({short_p3['mean_r']}R over {short_p3['n']} "
              f"trades) -> consistent with BETA: the edge is the market rising.")
else:
    print(f"  too few SHORT phase-3 trades ({short_p3['n']}) to separate alpha from beta.")

print(f"  LONG phase 3 : {long_p3['mean_r']}R over {long_p3['n']} trades")
print(f"  LONG phase 1 : {long_p1['mean_r']}R over {long_p1['n']} trades")
print(f"  SHORT phase 1: {short_p1['mean_r']}R over {short_p1['n']} trades")

# Multiple chronological folds, rather than a single split.
print()
print("=" * 90)
print("MULTIPLE FOLDS — a single split is one test; three is a pattern")
print("=" * 90)
dated = sorted({t.entry_date for t in trades if t.entry_date})
if len(dated) >= 8:
    bounds = [dated[int(len(dated) * f)] for f in (0.0, 0.25, 0.5, 0.75)]
    bounds.append(dated[-1])
    print(f"  {'fold':<8} {'window':<26} {'base meanR':>12} {'phase3 n':>9} {'phase3 meanR':>13}")
    print("  " + "-" * 74)
    for i in range(len(bounds) - 1):
        low, high = bounds[i], bounds[i + 1]
        window = [t for t in trades if t.entry_date and low <= t.entry_date <= high]
        base = stats(window)
        p3 = stats([t for t in window if phase_of(t) == 3])
        print(f"  {i+1:<8} {low} -> {high} {str(base['mean_r']):>12} "
              f"{p3['n']:>9} {str(p3['mean_r']):>13}")

with open(r"C:\Project\2026\scratch\backtest_alpha_beta.json", "w", encoding="utf-8") as handle:
    json.dump({"long_p3": long_p3, "short_p3": short_p3, "long_p1": long_p1,
               "short_p1": short_p1}, handle, indent=2)
print("\nwritten: scratch/backtest_alpha_beta.json")
