"""RANDOM-ENTRY CONTROL — the decisive test.

The out-of-sample split showed Boyd phase 3 positive in BOTH halves (+0.408, +0.439).
But the window 2024-12 -> 2026-09 was largely a bull market (buy-and-hold +40.8%).
A filter that selects "stock is in a confirmed uptrend" will look brilliant in a
bull market without the ENTRY having any edge at all -- it is just long exposure.

The clean control: take the same symbols and the same HOLDING PERIODS, but choose
entry dates at random. If the real entries beat random entries by a meaningful
margin, the entry rule carries signal. If they are indistinguishable, the "edge"
is market beta and the study is an elaborate way to be long.
"""
import json
import os
import random
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402
from qx.explorer import market_phases  # noqa: E402

SAMPLE = 400
DRAWS = 20          # random entries per real trade
SEED = 20260101

random.seed(SEED)

universe, report = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
trades = run["trades"]
print(f"base: {len(trades)} trades on {len(bars_only)} symbols\n")

# --- companion study context, to isolate the phase-3 subset -------------------
context: dict[str, dict] = {}
for symbol, bars in bars_only.items():
    try:
        closes = [b["close"] for b in bars]
        times = [b.get("date") or "" for b in bars]
        phase_series = market_phases.evaluate_series(closes, times)
    except Exception:  # noqa: BLE001
        continue
    context[symbol] = {p.index: p for p in phase_series}

phase3 = []
for trade in trades:
    ctx = context.get(trade.symbol)
    if not ctx:
        continue
    phase = ctx.get(trade.entry_index)
    if phase is not None and getattr(phase, "phase", None) == 3:
        phase3.append(trade)
print(f"phase-3 subset: {len(phase3)} trades\n")


def r_of(bars, i, j, risk):
    """Return in R for holding bars[i..j], using the same per-side cost model."""
    if j >= len(bars) or i >= len(bars):
        return None
    entry = bars[i]["open"]
    exit_price = bars[j]["close"]
    if not entry or entry <= 0 or not risk or risk <= 0:
        return None
    cost = simulate.DEFAULT_COST_BPS / 10000.0 * 2 * entry
    return (exit_price - entry - cost) / risk


print("building random-entry control...")
started = time.time()
real_r = []
random_r = []
for trade in phase3:
    bars = bars_only[trade.symbol]
    risk = getattr(trade, "initial_risk", None)
    exit_index = getattr(trade, "exit_index", None)
    if exit_index is None:
        exit_index = trade.entry_index + getattr(trade, "bars_held", 0)
    hold = max(1, exit_index - trade.entry_index)
    real = r_of(bars, trade.entry_index, trade.entry_index + hold, risk)
    if real is not None:
        real_r.append(real)
    # Same symbol, same holding period, random start.
    for _ in range(DRAWS):
        lo = 0
        hi = len(bars) - hold - 1
        if hi <= lo:
            continue
        start = random.randint(lo, hi)
        # Random entry needs the same ATR risk definition as the real trade;
        # use the real trade's risk so only the ENTRY TIMING differs.
        val = r_of(bars, start, start + hold, risk)
        if val is not None:
            random_r.append(val)
print(f"  {len(real_r)} real vs {len(random_r)} random draws "
      f"({time.time() - started:.1f}s)\n")


def describe(values):
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values), 4),
        "median": round(ordered[len(ordered) // 2], 4),
        "p10": round(ordered[int(len(ordered) * 0.10)], 4),
        "p90": round(ordered[int(len(ordered) * 0.90)], 4),
        "pct_positive": round(sum(1 for v in values if v > 0) / len(values), 4),
    }


real_stats = describe(real_r)
random_stats = describe(random_r)
edge = round(real_stats.get("mean", 0) - random_stats.get("mean", 0), 4)

print("=" * 78)
print("RANDOM-ENTRY CONTROL — phase 3 subset vs random timing, same symbols/holds")
print("=" * 78)
print(f"  {'':<22} {'n':>7} {'mean R':>9} {'median R':>10} {'p10':>8} "
      f"{'p90':>8} {'% up':>7}")
print("  " + "-" * 74)
print(f"  {'REAL entries':<22} {real_stats['n']:>7} {real_stats['mean']:>9} "
      f"{real_stats['median']:>10} {real_stats['p10']:>8} {real_stats['p90']:>8} "
      f"{real_stats['pct_positive']*100:>6.1f}%")
print(f"  {'RANDOM entries':<22} {random_stats['n']:>7} {random_stats['mean']:>9} "
      f"{random_stats['median']:>10} {random_stats['p10']:>8} {random_stats['p90']:>8} "
      f"{random_stats['pct_positive']*100:>6.1f}%")
print()
print(f"  EDGE over random timing : {edge:+.4f} R per trade")

# The same comparison for the UNFILTERED base trades.
base_real = []
base_random = []
for trade in trades:
    bars = bars_only[trade.symbol]
    risk = getattr(trade, "initial_risk", None)
    exit_index = getattr(trade, "exit_index", None)
    if exit_index is None:
        exit_index = trade.entry_index + getattr(trade, "bars_held", 0)
    hold = max(1, exit_index - trade.entry_index)
    real = r_of(bars, trade.entry_index, trade.entry_index + hold, risk)
    if real is not None:
        base_real.append(real)
    for _ in range(2):
        hi = len(bars) - hold - 1
        if hi <= 0:
            continue
        start = random.randint(0, hi)
        val = r_of(bars, start, start + hold, risk)
        if val is not None:
            base_random.append(val)

base_real_stats = describe(base_real)
base_random_stats = describe(base_random)
base_edge = round(base_real_stats.get("mean", 0) - base_random_stats.get("mean", 0), 4)

print()
print("=" * 78)
print("SAME CONTROL — unfiltered base trades")
print("=" * 78)
print(f"  {'REAL entries':<22} {base_real_stats['n']:>7} "
      f"{base_real_stats['mean']:>9} {base_real_stats['median']:>10} "
      f"{base_real_stats['pct_positive']*100:>6.1f}%")
print(f"  {'RANDOM entries':<22} {base_random_stats['n']:>7} "
      f"{base_random_stats['mean']:>9} {base_random_stats['median']:>10} "
      f"{base_random_stats['pct_positive']*100:>6.1f}%")
print()
print(f"  EDGE over random timing : {base_edge:+.4f} R per trade")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if edge > 0.15:
    print(f"  Phase 3 entries beat random timing by {edge:+.4f}R. The entry rule")
    print("  carries signal beyond mere long exposure in this window.")
elif edge > 0.0:
    print(f"  Phase 3 entries beat random timing by only {edge:+.4f}R. That is small")
    print("  enough to be market beta rather than entry skill.")
else:
    print(f"  Phase 3 entries did NOT beat random timing ({edge:+.4f}R). The filter's")
    print("  apparent edge is long exposure in a rising window, not entry timing.")

with open(r"C:\Project\2026\scratch\backtest_control.json", "w", encoding="utf-8") as handle:
    json.dump({"phase3": {"real": real_stats, "random": random_stats, "edge": edge},
               "base": {"real": base_real_stats, "random": base_random_stats,
                        "edge": base_edge},
               "draws_per_trade": DRAWS, "seed": SEED},
              handle, indent=2)
print("\nwritten: scratch/backtest_control.json")
