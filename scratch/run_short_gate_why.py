"""Why does 'short only when the market is falling' make things WORSE?

Pooled it is -0.87 R gated vs -0.60 R ungated. That is backwards from intuition,
so the mechanism matters: if I cannot explain it, I do not understand the result.

Hypothesis: the proxy being below its 50-day mean means the market has ALREADY
fallen. Shorts entering after a decline are shorting into a bounce - buying the
dip is exactly what the drift rewards. So the gate selects the WORST moment to
be short rather than the best.

Test: compare short performance by WHERE the market sits relative to its mean,
across the whole distribution rather than a single threshold.
"""
import os
import sys
from collections import defaultdict

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402

universe, _ = historical.build_universe(limit=400)
bars_only = {s: b.bars for s, b in universe.items()}
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
shorts = [t for t in run["trades"] if t.direction == "SHORT"]

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

# Distance of the market from its own mean, as a percentage.
distance = {}
for d in dates_sorted:
    if ma50.get(d):
        distance[d] = (level[d] / ma50[d] - 1.0) * 100.0


def stats(trades):
    if not trades:
        return (0, None, None)
    r = [t.net_r for t in trades]
    wins = [x for x in r if x > 0]
    losses = [x for x in r if x < 0]
    gl = abs(sum(losses))
    return (len(r), round(sum(r) / len(r), 4),
            round(sum(wins) / gl, 3) if gl > 0 else None)


print("=" * 92)
print("SHORT PERFORMANCE BY MARKET POSITION (distance from its own 50-day mean)")
print("=" * 92)
print("  A NEGATIVE bucket = market below its mean (what the gate selected).")
print()
print(f"  {'market vs mean':<22} {'n':>6} {'mean R':>10} {'PF':>8}")
print("  " + "-" * 50)

buckets = [
    ("< -8%  (deep decline)", lambda x: x < -8),
    ("-8% to -4%", lambda x: -8 <= x < -4),
    ("-4% to -2%", lambda x: -4 <= x < -2),
    ("-2% to 0%  (below mean)", lambda x: -2 <= x < 0),
    ("0% to +2%  (above mean)", lambda x: 0 <= x < 2),
    ("+2% to +4%", lambda x: 2 <= x < 4),
    ("+4% to +8%", lambda x: 4 <= x < 8),
    ("> +8%  (strong uptrend)", lambda x: x >= 8),
]
for label, predicate in buckets:
    subset = [t for t in shorts
              if t.entry_date in distance and predicate(distance[t.entry_date])]
    n, mean_r, pf = stats(subset)
    print(f"  {label:<22} {n:>6} {str(mean_r):>10} {str(pf):>8}")

print()
print("=" * 92)
print("THE MECHANISM")
print("=" * 92)
below = [t for t in shorts if t.entry_date in distance and distance[t.entry_date] < 0]
above = [t for t in shorts if t.entry_date in distance and distance[t.entry_date] >= 0]
nb, mb, pfb = stats(below)
na, ma, pfa = stats(above)
print(f"  market BELOW its mean : {nb:>5} trades   {str(mb):>9} R   PF {pfb}")
print(f"  market ABOVE its mean : {na:>5} trades   {str(ma):>9} R   PF {pfa}")
print()
if mb is not None and ma is not None:
    if mb < ma:
        print("  -> Shorting AFTER a decline is WORSE than shorting into strength.")
        print("     The gate selected the moment the bounce was most likely, which is")
        print("     the opposite of what was intended. This is the drift working")
        print("     through mean reversion: dips get bought.")
    else:
        print("  -> Shorting after a decline is better, so the pooled gate result")
        print("     must come from the deep-decline buckets specifically.")

print()
print("=" * 92)
print("WHY THE GATE FAILED")
print("=" * 92)
print("  The gate fires when the market is below its 50-day mean. That is a")
print("  LAGGING condition: by the time the average is breached, the decline has")
print("  already happened. Shorts opened there are selling into an oversold")
print("  market that the up-drift then pulls back up.")
print()
print("  The ungated short set includes entries during uptrends, which are ALSO")
print("  bad, but they are bad for a different reason and are diluted across many")
print("  more trades. Removing them did not remove the losses; it concentrated")
print("  the remaining trades into the single worst regime.")
