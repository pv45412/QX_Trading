"""Out-of-sample validation of the filter that looked best, with significance.

The ablation showed Boyd phase 3 at +0.4268R vs base -0.0635R. But that filter was
CHOSEN by looking at the whole sample, so the improvement may be data mining. The
only honest test: split the window in time. Use H1 to decide, H2 to judge. If the
edge only exists in H1, it was noise.

Also reports a t-statistic per subset so "is this difference real" is answered with
a number rather than an impression.
"""
import json
import math
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402
from qx.explorer import market_phases, momo_trend  # noqa: E402


def stats(trades):
    if not trades:
        return {"n": 0}
    r = [t.net_r for t in trades]
    n = len(r)
    mean = sum(r) / n
    var = sum((x - mean) ** 2 for x in r) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    se = sd / math.sqrt(n) if n else 0.0
    ordered = sorted(r)
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gross_loss = abs(sum(losses))
    return {
        "n": n,
        "mean_r": round(mean, 4),
        "median_r": round(ordered[n // 2], 4),
        "sd": round(sd, 4),
        "t_stat": round(mean / se, 3) if se else None,
        "win_rate": round(len(wins) / n, 4),
        "profit_factor": round(sum(wins) / gross_loss, 3) if gross_loss else None,
        "final_r": round(sum(r), 1),
        "p05_mae": round(sorted(t.mae_r for t in trades)[max(0, int(n * 0.05) - 1)], 3),
    }


print("loading the full clean universe...")
started = time.time()
universe, report = historical.build_universe()
bars_only = {s: b.bars for s, b in universe.items()}
print(f"  {len(bars_only)} symbols ({time.time() - started:.1f}s)")

started = time.time()
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
trades = run["trades"]
print(f"  {run['trade_count']} trades, {run['error_count']} errors "
      f"({time.time() - started:.1f}s)")

# date split: the window midpoint, taken from the data itself
dates = sorted({t.entry_date for t in trades if t.entry_date})
midpoint = dates[len(dates) // 2]
print(f"  window {dates[0]} .. {dates[-1]}   split at {midpoint}")

print("building companion-study context...")
context: dict[str, dict[int, dict]] = {}
started = time.time()
for symbol, bars in bars_only.items():
    closes = [b["close"] for b in bars]
    times = [b.get("date") for b in bars]
    entry: dict[int, dict] = {}
    try:
        for snap in momo_trend.evaluate_series(
                [b["high"] for b in bars], [b["low"] for b in bars], closes,
                times, forming=True):
            entry.setdefault(snap.index, {})["aligned"] = bool(
                snap.aligned_up or snap.aligned_down)
    except Exception as exc:  # noqa: BLE001
        print(f"     momo failed {symbol}: {type(exc).__name__}: {exc}")
    try:
        for snap in market_phases.evaluate_series(closes, times, forming=True):
            entry.setdefault(snap.index, {})["phase"] = snap.phase
    except Exception as exc:  # noqa: BLE001
        print(f"     phases failed {symbol}: {type(exc).__name__}: {exc}")
    context[symbol] = entry
print(f"  context for {len(context)} symbols ({time.time() - started:.1f}s)")

buckets = {
    "ALL (base)": lambda t, c: True,
    "Momo+Trend aligned": lambda t, c: c.get("aligned"),
    "Boyd phase 3": lambda t, c: c.get("phase") == 3,
    "Boyd phase 4 (pullback)": lambda t, c: c.get("phase") == 4,
    "phase 3 OR 4": lambda t, c: c.get("phase") in (3, 4),
}
h1: dict[str, list] = {k: [] for k in buckets}
h2: dict[str, list] = {k: [] for k in buckets}
for trade in trades:
    ctx = context.get(trade.symbol, {}).get(trade.entry_index - 1, {})
    target = h1 if (trade.entry_date or "") < midpoint else h2
    for label, predicate in buckets.items():
        if predicate(trade, ctx):
            target[label].append(trade)

print()
print("=" * 100)
print("OUT-OF-SAMPLE TEST — the same filter must work in BOTH halves to be believable")
print("=" * 100)
header = (f"  {'subset':<26} {'half':<6} {'n':>6} {'mean R':>9} {'median':>9} "
          f"{'win%':>7} {'PF':>7} {'t':>7} {'final R':>9}")
print(header)
print("  " + "-" * 94)
summary = {}
for label in buckets:
    for name, half in (("H1 (in-sample)", h1[label]), ("H2 (out-of-sample)", h2[label])):
        s = stats(half)
        summary[f"{label}|{name}"] = s
        pf = s.get("profit_factor", "-")
        wr = f"{s['win_rate']*100:.1f}%" if s.get("win_rate") is not None else "-"
        t = s.get("t_stat", "-")
        print(f"  {label:<26} {name[:2]:<6} {s['n']:>6} {str(s.get('mean_r')):>9} "
              f"{str(s.get('median_r')):>9} {wr:>7} {str(pf):>7} {str(t):>7} "
              f"{str(s.get('final_r')):>9}")
    print()

print("=" * 100)
print("VERDICT — does the filter hold up out of sample?")
print("=" * 100)
for label in buckets:
    a = summary[f"{label}|H1 (in-sample)"]
    b = summary[f"{label}|H2 (out-of-sample)"]
    if not a.get("n") or not b.get("n"):
        continue
    holds = b["mean_r"] > 0 and b["profit_factor"] and b["profit_factor"] > 1.0
    print(f"  {label:<26} H1 {a['mean_r']:>8} R   H2 {b['mean_r']:>8} R   "
          f"{'HOLDS' if holds else 'DOES NOT HOLD'}")

with open(r"C:\Project\2026\scratch\backtest_oos.json", "w", encoding="utf-8") as handle:
    json.dump({"midpoint": midpoint, "trades": run["trade_count"],
               "summary": summary}, handle, indent=2)
print("\nwritten: scratch/backtest_oos.json")
