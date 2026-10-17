"""Matched random-entry control.

The ablation showed "Boyd phase 3" trades at +0.425R vs +(-0.064)R for all trades.
But phase 3 is literally "close above the 10 and 30 MA" - an uptrend filter. Long
trades taken in uptrends beating the average long trade is not an edge; it is
arithmetic. The only question that matters is whether the study's ENTRY TIMING
beats a coin flip WITHIN the same regime and held for the same duration.

So: for every real trade, sample a random bar that satisfies the SAME regime
condition, enter long at the next open, hold exactly the same number of bars,
and close at the same next-open basis. Reuse the simulator's own _close and
_update_excursions so costs, risk definition and excursion maths are identical.
"""
import json
import os
import random
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402
from qx.backtesting.simulate import Trade, _close, _update_excursions  # noqa: E402
from qx.explorer import market_phases, master_auto, momo_trend  # noqa: E402

SAMPLE = 400
DRAWS = 5
SEED = 20260214
STOP_MULT = 1.10
COST_BPS = simulate.DEFAULT_COST_BPS
QTY = 100.0

random.seed(SEED)

print(f"loading up to {SAMPLE} clean symbols...")
universe, _ = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
print(f"  {len(bars_only)} symbols\n")

started = time.time()
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
print(f"base: {run['trade_count']} trades ({time.time() - started:.1f}s)")

# ---- build per-symbol context: atr + regime conditions, indexed by bar -------
print("building per-symbol context...")
ctx: dict[str, dict] = {}
for symbol, bars in bars_only.items():
    try:
        snaps = master_auto.evaluate_series(bars)
        phases = {p.index: p.phase for p in market_phases.evaluate_series(bars)}
        momos = {m.index: bool(m.aligned_up) for m in momo_trend.evaluate_series(bars)}
    except Exception:  # noqa: BLE001
        continue
    atr = {}
    for s in snaps:
        if s.trade_atr and s.trade_atr > 0:
            atr[s.index] = float(s.trade_atr)
    ctx[symbol] = {"atr": atr, "phase": phases, "aligned": momos, "n": len(bars)}
print(f"  context for {len(ctx)} symbols\n")

CONDITIONS = {
    "ALL": lambda c, i: True,
    "Momo+Trend aligned": lambda c, i: c["aligned"].get(i) is True,
    "Boyd phase 3": lambda c, i: c["phase"].get(i) == 3,
    "Aligned AND phase 3": lambda c, i: (c["aligned"].get(i) is True
                                         and c["phase"].get(i) == 3),
}


def eligible_indices(c, condition):
    return [i for i in c["atr"] if condition(c, i)]


def control_for(trades, condition, draws=DRAWS):
    """Random entries in the SAME regime, SAME holding period."""
    out = []
    cache: dict[str, list[int]] = {}
    for t in trades:
        c = ctx.get(t.symbol)
        if not c:
            continue
        held = t.bars_held
        if held <= 0:
            continue
        pool = cache.get(t.symbol)
        if pool is None:
            pool = eligible_indices(c, condition)
            cache[t.symbol] = pool
        # entry index of a control must leave room for the same holding period
        usable = [j for j in pool if j + 1 + held < c["n"]]
        if not usable:
            continue
        for _ in range(draws):
            j = random.choice(usable)
            entry_index = j + 1
            entry_price = bars_only[t.symbol][entry_index]["open"]
            risk = c["atr"][j] * STOP_MULT
            if risk <= 0:
                continue
            position = {
                "direction": "LONG", "entry_index": entry_index,
                "entry_date": bars_only[t.symbol][entry_index].get("date"),
                "entry_price": entry_price, "stop": entry_price - risk,
                "risk": risk, "mae": 0.0, "mfe": 0.0,
            }
            for k in range(entry_index, entry_index + held):
                _update_excursions(position, bars_only[t.symbol][k])
            exit_index = entry_index + held
            trade = _close(position, exit_index, bars_only[t.symbol],
                           bars_only[t.symbol][exit_index]["open"],
                           "CONTROL", QTY, COST_BPS)
            trade.symbol = t.symbol
            out.append(trade)
    return out


def summary(trades):
    if not trades:
        return {"n": 0}
    r = sorted(t.net_r for t in trades)
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gl = abs(sum(losses))
    return {
        "n": len(r),
        "mean_r": round(sum(r) / len(r), 4),
        "median_r": round(r[len(r) // 2], 4),
        "win_rate": round(len(wins) / len(r), 4),
        "profit_factor": round(sum(wins) / gl, 3) if gl else None,
        "final_r": round(sum(r), 1),
    }


print("=" * 96)
print("MATCHED CONTROL — same regime, same holding period, random entry timing")
print("=" * 96)
print(f"  {'regime':<22} {'real n':>7} {'real mean':>10} | {'ctrl n':>7} "
      f"{'ctrl mean':>10} {'ctrl med':>9} | {'EDGE':>9}")
print("  " + "-" * 92)

results = {}
for label, condition in CONDITIONS.items():
    real = [t for t in run["trades"] if condition(ctx.get(t.symbol), t.entry_index)
            if ctx.get(t.symbol)] if False else []
    # real trades must satisfy the condition on their OWN entry index
    real = []
    for t in run["trades"]:
        c = ctx.get(t.symbol)
        if not c:
            continue
        if condition(c, t.entry_index):
            real.append(t)
    if not real:
        print(f"  {label:<22} {0:>7}")
        continue
    control = control_for(real, condition)
    rs, cs = summary(real), summary(control)
    edge = round(rs["mean_r"] - cs["mean_r"], 4)
    results[label] = {"real": rs, "control": cs, "edge_r": edge}
    print(f"  {label:<22} {rs['n']:>7} {rs['mean_r']:>10} | {cs['n']:>7} "
          f"{cs['mean_r']:>10} {cs['median_r']:>9} | {edge:>+9}")

print()
print("=" * 96)
print("READING")
print("=" * 96)
for label, row in results.items():
    edge = row["edge_r"]
    real = row["real"]["mean_r"]
    ctrl = row["control"]["mean_r"]
    if real > 0 and ctrl <= 0:
        verdict = "entry timing carries the result"
    elif edge > 0.05:
        verdict = "timing adds a little"
    elif edge < -0.05:
        verdict = "timing SUBTRACTS"
    else:
        verdict = "no timing edge - regime alone explains it"
    print(f"  {label:<22} real {real:>+7}  control {ctrl:>+7}  edge {edge:>+7}   {verdict}")

with open(r"C:\Project\2026\scratch\backtest_control.json", "w", encoding="utf-8") as handle:
    json.dump({"draws": DRAWS, "seed": SEED, "results": results}, handle, indent=2)
print("\nwritten: scratch/backtest_control.json")
