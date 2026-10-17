"""Does the layered system help? Filter the SAME trades by the companion studies.

Base result over the full universe was negative (-0.138R expectancy). The app
layers Momo/Trend, Boyd phases and relative strength on top. If those layers carry
signal, trades taken while they agree should be materially better than the base.

Corrected against the real module APIs:
  momo_trend.evaluate_series(highs, lows, closes) -> MultiTrendSnapshot
      fields: momentum, trend, bullish_stack, bearish_stack, warmup_ok
  market_phases.evaluate_series(closes) -> PhaseSnapshot
      fields: phase, hull_falling, ma10_gt_ma30, warmup_ok
"""
import json
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402
from qx.explorer import market_phases, momo_trend  # noqa: E402

SAMPLE = None  # full cleaned universe


def stats(trades):
    if not trades:
        return {"n": 0}
    r = [t.net_r for t in trades]
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    ordered = sorted(r)
    gross_loss = abs(sum(losses))
    return {
        "n": len(r),
        "mean_r": round(sum(r) / len(r), 4),
        "median_r": round(ordered[len(ordered) // 2], 4),
        "win_rate": round(len(wins) / len(r), 4),
        "profit_factor": (round(sum(wins) / gross_loss, 3) if gross_loss > 0 else None),
        "final_r": round(sum(r), 1),
    }


print("loading the full cleaned universe...")
universe, _report = historical.build_universe()
bars_only = {s: b.bars for s, b in universe.items()}
print(f"  {len(bars_only)} symbols loaded\n")

started = time.time()
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
print(f"base simulation: {run['trade_count']} trades ({time.time() - started:.1f}s)")

print("evaluating companion studies per symbol...")
context: dict[str, dict] = {}
errors: list[str] = []
for symbol, bars in bars_only.items():
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    times = [b.get("date") or b.get("time") for b in bars]
    try:
        momo = momo_trend.evaluate_series(highs, lows, closes, times)
        phases = market_phases.evaluate_series(closes, times)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
        continue
    context[symbol] = {
        "momo": {m.index: m for m in momo},
        "phase": {p.index: p for p in phases},
    }
print(f"  context built for {len(context)} symbols, {len(errors)} errors")
for line in errors[:5]:
    print(f"     {line}")
if errors:
    print()

buckets: dict[str, list] = {
    "ALL (base)": [],
    "Momo bullish stack": [],
    "Momo momentum bull": [],
    "Boyd phase 3": [],
    "Boyd phase 4": [],
    "Phase3 & MA10>MA30": [],
    "Bullish stack AND phase 3": [],
    "Bullish stack AND phase 4": [],
}
no_ctx = 0
warmup_blocked = 0

for trade in run["trades"]:
    buckets["ALL (base)"].append(trade)
    ctx = context.get(trade.symbol)
    if not ctx:
        no_ctx += 1
        continue
    momo = ctx["momo"].get(trade.entry_index)
    phase = ctx["phase"].get(trade.entry_index)
    if momo is None or phase is None:
        no_ctx += 1
        continue
    if not (momo.warmup_ok and phase.warmup_ok):
        warmup_blocked += 1
        continue

    bull = bool(momo.bullish_stack)
    momo_bull = str(momo.momentum or "").lower().startswith("bull")
    pno = phase.phase

    if bull:
        buckets["Momo bullish stack"].append(trade)
    if momo_bull:
        buckets["Momo momentum bull"].append(trade)
    if pno == 3:
        buckets["Boyd phase 3"].append(trade)
    if pno == 4:
        buckets["Boyd phase 4"].append(trade)
    if pno == 3 and phase.ma10_gt_ma30:
        buckets["Phase3 & MA10>MA30"].append(trade)
    if bull and pno == 3:
        buckets["Bullish stack AND phase 3"].append(trade)
    if bull and pno == 4:
        buckets["Bullish stack AND phase 4"].append(trade)

print("=" * 92)
print("DOES THE LAYERED SYSTEM HELP?  (identical entries, filtered by companion studies)")
print("=" * 92)
print(f"  {'subset':<28} {'n':>6} {'mean R':>9} {'median R':>10} {'win%':>7} "
      f"{'PF':>7} {'final R':>10}")
print("  " + "-" * 86)
for label, trades in buckets.items():
    s = stats(trades)
    if not s["n"]:
        print(f"  {label:<28} {0:>6}      (no trades)")
        continue
    pf = s["profit_factor"] if s["profit_factor"] is not None else "-"
    print(f"  {label:<28} {s['n']:>6} {s['mean_r']:>9} {s['median_r']:>10} "
          f"{s['win_rate']*100:>6.1f}% {str(pf):>7} {s['final_r']:>10}")

print(f"\n  trades lacking study context : {no_ctx}")
print(f"  trades dropped in warmup     : {warmup_blocked}")

with open(r"C:\Project\2026\scratch\backtest_ablation.json", "w", encoding="utf-8") as handle:
    json.dump({label: stats(t) for label, t in buckets.items()}, handle, indent=2)
print("written: scratch/backtest_ablation.json")
