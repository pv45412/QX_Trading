"""Is the short side BROKEN, or merely HOSTILE?

The long/short code is line-for-line symmetric (master_auto.py L494-510), so a
sign bug is unlikely. Three explanations remain, and they have different fixes:

  H1 SYMMETRY BUG   - the mirrored conditions are not truly equivalent.
                       Fix: correct the code.
  H2 MARKET DRIFT   - shorts lose because equities drift up. Signals fire in
                       both directions, but the up-drift dominates.
                       Fix: delete the short side; it cannot be fixed.
  H3 ENTRY QUALITY  - short signals are rarer/worse-timed; the asymmetry is in
                       what triggers them, not in the arithmetic.
                       Fix: improve the short trigger.

The discriminator between H2 and H3 is the NULL TEST: take the long trades and
MIRROR their returns (R -> -R). That is what a symmetric short signal on the same
bars would have earned under a zero-drift market. If actual shorts do much worse
than mirrored longs, the loss is market drift (H2). If they match, the short
signal is simply the long signal inverted (H3).
"""
import os
import statistics
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, simulate  # noqa: E402

SAMPLE = 400


def stats(values):
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    gl = abs(sum(losses))
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values), 4),
        "median": round(ordered[len(ordered) // 2], 4),
        "win_rate": round(len(wins) / len(values), 4),
        "pf": round(sum(wins) / gl, 3) if gl > 0 else None,
    }


universe, _ = historical.build_universe(limit=SAMPLE)
bars_only = {s: b.bars for s, b in universe.items()}
run = simulate.simulate_universe(bars_only, exit_policy=simulate.EXIT_STUDY)
trades = run["trades"]
longs = [t for t in trades if t.direction == "LONG"]
shorts = [t for t in trades if t.direction == "SHORT"]
print(f"{len(trades)} trades: {len(longs)} LONG, {len(shorts)} SHORT\n")

print("=" * 88)
print("H1 — SIGNAL FREQUENCY: do shorts even fire comparably?")
print("=" * 88)
print(f"  LONG  signals : {len(longs)}")
print(f"  SHORT signals : {len(shorts)}")
ratio = len(shorts) / len(longs) if longs else 0
print(f"  ratio         : {ratio:.2f}  (1.00 would mean symmetric firing)")
print()
if ratio < 0.5:
    print("  -> shorts fire far less often. The asymmetry may be in OPPORTUNITY,")
    print("     not arithmetic: bear_stack + close < wave_low + bear candle is rare")
    print("     in a rising market.")
else:
    print("  -> shorts fire comparably often, so opportunity is not the issue.")

print()
print("=" * 88)
print("H2 vs H3 — THE NULL TEST: mirror the long returns")
print("=" * 88)
long_r = [t.net_r for t in longs]
short_r = [t.net_r for t in shorts]
mirrored = [-r for r in long_r]          # what a perfect mirror of the longs earns

s_long = stats(long_r)
s_short = stats(short_r)
s_mirror = stats(mirrored)

print(f"  {'series':<28} {'n':>6} {'mean R':>9} {'median R':>10} {'win%':>7} {'PF':>7}")
print("  " + "-" * 74)
for label, s in (("LONG actual", s_long), ("SHORT actual", s_short),
                 ("LONG mirrored (-R) = null", s_mirror)):
    print(f"  {label:<28} {s['n']:>6} {s['mean']:>9} {s['median']:>10} "
          f"{s['win_rate']*100:>6.1f}% {str(s['pf']):>7}")

print()
gap = s_short["mean"] - s_mirror["mean"]
print(f"  SHORT actual mean R      : {s_short['mean']}")
print(f"  mirrored-long mean R     : {s_mirror['mean']}")
print(f"  DIFFERENCE               : {gap:+.4f}")
print()
if gap < -0.15:
    print("  -> Actual shorts do materially WORSE than a pure mirror of the longs.")
    print("     The mirror would have been flat-ish under symmetry; shorts are")
    print("     worse, which is the signature of MARKET DRIFT (H2).")
elif gap > 0.15:
    print("  -> Actual shorts do BETTER than the mirror. The short trigger is")
    print("     adding something the long side lacks (H3).")
else:
    print("  -> Actual shorts track the mirror closely: the short signal is")
    print("     essentially the long signal inverted (H3), with no extra edge.")

print()
print("=" * 88)
print("H2 DIRECTLY — what did the market do, and what did shorts fight?")
print("=" * 88)
# Equal-weight drift over the window, and the mean return of the symbols traded.
returns = []
for symbol, bars in bars_only.items():
    if len(bars) >= 2 and bars[0]["close"] > 0:
        returns.append(bars[-1]["close"] / bars[0]["close"] - 1.0)
if returns:
    print(f"  equal-weight symbol drift : {statistics.mean(returns):+.1%} mean, "
          f"{statistics.median(returns):+.1%} median")
    print(f"  symbols positive          : "
          f"{sum(1 for r in returns if r > 0)/len(returns):.1%}")

# Do shorts lose because of drift, or because they exit badly?
short_exits: dict[str, int] = {}
for t in shorts:
    short_exits[t.exit_reason] = short_exits.get(t.exit_reason, 0) + 1
long_exits: dict[str, int] = {}
for t in longs:
    long_exits[t.exit_reason] = long_exits.get(t.exit_reason, 0) + 1
print(f"  LONG  exit reasons : {long_exits}")
print(f"  SHORT exit reasons : {short_exits}")

print()
print("=" * 88)
print("H3 — is the SHORT entry timing worse?")
print("=" * 88)
# Compare the MFE of longs vs shorts: did shorts ever go their way?
long_mfe = [t.mfe_r for t in longs if t.mfe_r is not None]
short_mfe = [t.mfe_r for t in shorts if t.mfe_r is not None]
if long_mfe and short_mfe:
    print(f"  LONG  mean MFE : {statistics.mean(long_mfe):+.3f} R")
    print(f"  SHORT mean MFE : {statistics.mean(short_mfe):+.3f} R")
    print()
    print("  MFE is how far a trade ran IN FAVOUR before exiting. If shorts have")
    print("  a healthy MFE but still lose, the ENTRY is fine and the EXIT leaks.")
    print("  If shorts have near-zero MFE, they never work at all (entry problem).")

print()
print("=" * 88)
print("CONCLUSION")
print("=" * 88)
verdicts = []
if ratio < 0.6:
    verdicts.append("shorts fire much less often (opportunity asymmetry)")
if gap < -0.15:
    verdicts.append("shorts underperform the mirrored long (market drift, H2)")
elif abs(gap) <= 0.15:
    verdicts.append("shorts track the mirrored long (H3: no independent edge)")
for v in verdicts:
    print(f"  - {v}")
