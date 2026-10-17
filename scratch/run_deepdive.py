"""Deep dive: test the documented improvement patterns against our own data.

What we know (measured, not assumed):
  base rules      -0.125 R/trade, PF 0.884, 34.6% win
  LONG side       +0.4136 R over 1070 trades
  SHORT side      -0.6036 R over  945 trades     <- the edge is long-side beta
  73.1% of trades breach the displayed 1R stop

Documented patterns for equity systems that we do NOT yet use:
  A. REGIME FILTER     — only take longs when the broad market is in an uptrend
  B. CROSS-SECTIONAL   — rank signals and take the strongest N, rather than every
     RANKING             signal. This is the documented equity momentum approach
                         (Jegadeesh & Titman 1993), as opposed to per-symbol
                         time-series momentum, which is what MASTER AUTO does.
  C. EXIT VARIANT      — fixed-horizon and trailing exits, to separate entry quality
                         from exit quality
  D. VOLATILITY TARGET — size inversely to ATR so risk is comparable per trade

Each is tested on the SAME entries, so differences are attributable to the change.
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
        return {"n": 0, "mean_r": None, "median_r": None, "win_rate": None,
                "profit_factor": None, "final_r": None, "max_dd": None}
    r = sorted(t.net_r for t in trades)
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gl = abs(sum(losses))
    equity = peak = worst = 0.0
    for value in r:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return {
        "n": len(r), "mean_r": round(sum(r) / len(r), 4),
        "median_r": round(r[len(r) // 2], 4),
        "win_rate": round(len(wins) / len(r), 4),
        "profit_factor": round(sum(wins) / gl, 3) if gl > 0 else None,
        "final_r": round(sum(r), 1), "max_dd": round(worst, 1),
    }


print("loading...")
universe, report = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
trades = run["trades"]
print(f"  {len(bars_only)} symbols, {len(trades)} trades")

# ---- build a market proxy from the universe itself (equal-weight, point-in-time) ----
print("building an equal-weight market proxy from the same bars...")
by_date_close: dict[str, list[float]] = defaultdict(list)
for symbol, bars in bars_only.items():
    for bar in bars:
        if bar.get("date"):
            by_date_close[bar["date"]].append(bar["close"])
dates_sorted = sorted(by_date_close)
market_level: dict[str, float] = {}
for date in dates_sorted:
    market_level[date] = sum(by_date_close[date]) / len(by_date_close[date])
market_series = [market_level[d] for d in dates_sorted]
market_ma: dict[str, float] = {}
window = 50
for i, date in enumerate(dates_sorted):
    if i >= window:
        market_ma[date] = sum(market_series[i - window:i]) / window


def market_is_up(date):
    """Point-in-time: is the market proxy above its own 50-day mean?"""
    level = market_level.get(date)
    ma = market_ma.get(date)
    return bool(level and ma and level > ma)


print()
print("=" * 100)
print("A. REGIME FILTER — longs only when the market proxy is above its 50-day mean")
print("=" * 100)
base_longs = [t for t in trades if t.direction == "LONG"]
filtered_longs = [t for t in base_longs if t.entry_date and market_is_up(t.entry_date)]
print(f"  {'variant':<34} {'n':>6} {'mean R':>9} {'win%':>7} {'PF':>7} {'final R':>9} {'maxDD':>9}")
for label, subset in (("LONG all", base_longs), ("LONG when market up", filtered_longs)):
    s = stats(subset)
    pf = s["profit_factor"] if s["profit_factor"] is not None else "-"
    print(f"  {label:<34} {s['n']:>6} {str(s['mean_r']):>9} "
          f"{(s['win_rate'] or 0)*100:>6.1f}% {str(pf):>7} {str(s['final_r']):>9} {str(s['max_dd']):>9}")

print()
print("=" * 100)
print("B. CROSS-SECTIONAL RANKING — take only the strongest N signals per date")
print("=" * 100)
print("   (the documented equity-momentum approach, vs per-symbol timing)")
print()
# Rank by realised strength: the trade's own MFE is future information, so rank by
# something available at entry. Use the prior 20-bar return of the symbol.
prior_return: dict[tuple[str, str], float] = {}
for symbol, bars in bars_only.items():
    for i, bar in enumerate(bars):
        if i >= 20 and bar.get("date"):
            base = bars[i - 20]["close"]
            if base > 0:
                prior_return[(symbol, bar["date"])] = bar["close"] / base - 1.0

by_entry_date: dict[str, list] = defaultdict(list)
for trade in trades:
    if trade.direction == "LONG" and trade.entry_date:
        by_entry_date[trade.entry_date].append(trade)

print(f"  {'variant':<34} {'n':>6} {'mean R':>9} {'win%':>7} {'PF':>7} {'final R':>9} {'maxDD':>9}")
rows = []
for top_n in (None, 5, 3, 1):
    selected = []
    for date, group in by_entry_date.items():
        if top_n is None:
            selected.extend(group)
        else:
            ranked = sorted(group,
                            key=lambda t: prior_return.get((t.symbol, t.entry_date), -9),
                            reverse=True)
            selected.extend(ranked[:top_n])
    s = stats(selected)
    label = "LONG all signals" if top_n is None else f"LONG top {top_n} per day"
    pf = s["profit_factor"] if s["profit_factor"] is not None else "-"
    print(f"  {label:<34} {s['n']:>6} {str(s['mean_r']):>9} "
          f"{(s['win_rate'] or 0)*100:>6.1f}% {str(pf):>7} {str(s['final_r']):>9} {str(s['max_dd']):>9}")
    rows.append({"variant": label, **s})

print()
print("=" * 100)
print("C. EXIT QUALITY — is the EXIT the problem, or the ENTRY?")
print("=" * 100)
print("   Same entries, different exits. If a naive exit beats the study exit,")
print("   the exit rule is destroying value.")
print()
stopped = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STOP)
for label, result in (("study exit (signal reversal)", run),
                      ("stop enforced at 1R", stopped)):
    s = stats([t for t in result["trades"] if t.direction == "LONG"])
    pf = s["profit_factor"] if s["profit_factor"] is not None else "-"
    print(f"  {label:<34} {s['n']:>6} {str(s['mean_r']):>9} "
          f"{(s['win_rate'] or 0)*100:>6.1f}% {str(pf):>7} {str(s['final_r']):>9} {str(s['max_dd']):>9}")

# Distribution shape: does the winner tail pay for the losers?
long_r = sorted(t.net_r for t in base_longs)
print()
print("  LONG R distribution (why the mean is what it is):")
for label, fraction in (("p05", 0.05), ("p25", 0.25), ("median", 0.5),
                        ("p75", 0.75), ("p90", 0.90), ("p99", 0.99)):
    idx = min(int(fraction * len(long_r)), len(long_r) - 1)
    print(f"     {label:<8} {long_r[idx]:>9.3f}")
print(f"     {'max':<8} {long_r[-1]:>9.3f}")
gross_w = sum(x for x in long_r if x > 0)
gross_l = abs(sum(x for x in long_r if x < 0))
print(f"     gross win {gross_w:.1f}R vs gross loss {gross_l:.1f}R")

print()
print("=" * 100)
print("D. WHAT WOULD ACTUALLY HELP — summary")
print("=" * 100)
base_long = stats(base_longs)
best = None
for variant in rows:
    if variant["variant"] != "LONG all signals" and variant["mean_r"] is not None:
        if best is None or variant["mean_r"] > best["mean_r"]:
            best = variant
print(f"  LONG all signals      : {base_long['mean_r']} R/trade over {base_long['n']} trades")
if best:
    print(f"  best ranking variant  : {best['variant']} -> {best['mean_r']} R/trade "
          f"over {best['n']} trades")
regime = stats(filtered_longs)
print(f"  regime-filtered longs : {regime['mean_r']} R/trade over {regime['n']} trades")

with open(r"C:\Project\2026\scratch\backtest_deepdive.json", "w", encoding="utf-8") as handle:
    json.dump({"base_longs": base_long, "regime_filtered": regime,
               "ranking_variants": rows,
               "distribution": {"p05": long_r[int(0.05*len(long_r))],
                                "median": long_r[len(long_r)//2],
                                "p95": long_r[min(int(0.95*len(long_r)), len(long_r)-1)],
                                "max": long_r[-1]}},
              handle, indent=2)
print("\nwritten: scratch/backtest_deepdive.json")
