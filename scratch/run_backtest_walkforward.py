"""Walk-forward validation: does the filter edge survive OUT OF SAMPLE?

The ablation found the base rules lose (-0.064R) while subsets look good:
  Momo+Trend aligned  +0.285R
  Boyd phase 3        +0.425R

That is exactly where backtests lie. I tested seven subsets; finding three that look
good is partly luck, and I fitted on the whole period. The only honest test is a
CHRONOLOGICAL holdout: decide the filters on the early window, then check them on a
later window the decision never saw.

Split is by DATE, not by trade, so no future information leaks backwards.
"""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402
from qx.explorer import market_phases, momo_trend  # noqa: E402

SAMPLE = 400
SPLIT_FRACTION = 0.60          # first 60% of the DATE RANGE is in-sample


def stats(trades):
    if not trades:
        return {"n": 0, "mean_r": None, "median_r": None, "win_rate": None,
                "profit_factor": None, "final_r": None}
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


print("loading clean sample...")
universe, report = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
print(f"  {len(bars_only)} symbols")

run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
trades = run["trades"]
print(f"  {len(trades)} trades")

# Evaluate companion studies once per symbol.
context: dict[str, dict] = {}
for symbol, bars in bars_only.items():
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    times = [b.get("date") or "" for b in bars]
    try:
        momo_series = momo_trend.evaluate_series(highs, lows, closes, times)
        phase_series = market_phases.evaluate_series(closes, times)
    except Exception:  # noqa: BLE001
        continue
    context[symbol] = {
        "momo": {m.index: m for m in momo_series},
        "phase": {p.index: p for p in phase_series},
    }

# Chronological split by DATE.
dates = sorted({t.entry_date for t in trades if t.entry_date})
if not dates:
    raise SystemExit("no dated trades")
split_date = dates[int(len(dates) * SPLIT_FRACTION)]
print(f"\n  date range : {dates[0]} -> {dates[-1]}")
print(f"  split date : {split_date}  (in-sample = before, out-of-sample = on/after)")


def label(trade):
    ctx = context.get(trade.symbol)
    if not ctx:
        return {"aligned": None, "phase": None}
    momo = ctx["momo"].get(trade.entry_index)
    phase = ctx["phase"].get(trade.entry_index)
    return {
        "aligned": bool(momo and getattr(momo, "aligned_up", False)),
        "phase": getattr(phase, "phase", None) if phase else None,
    }


in_sample = [t for t in trades if t.entry_date and t.entry_date < split_date]
out_sample = [t for t in trades if t.entry_date and t.entry_date >= split_date]

FILTERS = {
    "ALL (base)": lambda f: True,
    "Momo+Trend aligned": lambda f: f["aligned"] is True,
    "Boyd phase 3": lambda f: f["phase"] == 3,
    "Boyd phase 3 OR aligned": lambda f: f["phase"] == 3 or f["aligned"] is True,
}

print()
print("=" * 96)
print("WALK-FORWARD: the same filter must work in BOTH windows to count")
print("=" * 96)
print(f"  {'filter':<26} | {'IN-SAMPLE':^28} | {'OUT-OF-SAMPLE':^28}")
print(f"  {'':<26} | {'n':>6} {'meanR':>8} {'PF':>6} {'finalR':>7} | "
      f"{'n':>6} {'meanR':>8} {'PF':>6} {'finalR':>7}")
print("  " + "-" * 92)

rows = {}
for name, predicate in FILTERS.items():
    ins = [t for t in in_sample if predicate(label(t))]
    outs = [t for t in out_sample if predicate(label(t))]
    si, so = stats(ins), stats(outs)
    rows[name] = {"in_sample": si, "out_of_sample": so}
    pf_i = si["profit_factor"] if si["profit_factor"] is not None else "-"
    pf_o = so["profit_factor"] if so["profit_factor"] is not None else "-"
    print(f"  {name:<26} | {si['n']:>6} {str(si['mean_r']):>8} {str(pf_i):>6} "
          f"{str(si['final_r']):>7} | {so['n']:>6} {str(so['mean_r']):>8} "
          f"{str(pf_o):>6} {str(so['final_r']):>7}")

print()
print("=" * 96)
print("VERDICT PER FILTER")
print("=" * 96)
for name, data in rows.items():
    si, so = data["in_sample"], data["out_of_sample"]
    if not si["n"] or not so["n"]:
        verdict = "INSUFFICIENT DATA"
    elif si["mean_r"] is not None and so["mean_r"] is not None:
        if si["mean_r"] > 0 and so["mean_r"] > 0:
            verdict = "HOLDS OUT OF SAMPLE"
        elif si["mean_r"] > 0 > so["mean_r"]:
            verdict = "FAILS OUT OF SAMPLE (in-sample edge was not real)"
        elif si["mean_r"] < 0 and so["mean_r"] < 0:
            verdict = "LOSES IN BOTH"
        else:
            verdict = "MIXED"
    else:
        verdict = "INSUFFICIENT DATA"
    print(f"  {name:<26} in={str(si['mean_r']):>8}  out={str(so['mean_r']):>8}  -> {verdict}")

with open(r"C:\Project\2026\scratch\backtest_walkforward.json", "w", encoding="utf-8") as handle:
    json.dump({"split_date": split_date, "date_range": [dates[0], dates[-1]],
               "in_sample_trades": len(in_sample), "out_sample_trades": len(out_sample),
               "filters": rows}, handle, indent=2)
print("\nwritten: scratch/backtest_walkforward.json")
