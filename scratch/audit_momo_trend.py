"""Scratch: verify the TOPS-MultiTrend port against hand-computed cases."""
import math
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.momo_trend import (  # noqa: E402
    BEARISH, BULLISH, SIDEWAYS, evaluate_series, latest, transition_track, warmup_bars,
)

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


def series_from(closes, highs=None, lows=None):
    highs = highs or [c + 1 for c in closes]
    lows = lows or [c - 1 for c in closes]
    return highs, lows, closes


def synth(n, fn):
    return [fn(i) for i in range(n)]


WARM = warmup_bars()
print(f"warmup requirement: {WARM} bars")

print("\n== 1. insufficient warmup -> None (never a guessed label) ==")
h, l, c = series_from(synth(20, lambda i: 100 + i))
short = evaluate_series(h, l, c)
check("short series returns no definite state",
      all(s.momentum is None and s.trend is None for s in short),
      f"{len(short)} snapshots, all None")

print("\n== 2. monotonic uptrend -> BULLISH / BULLISH ==")
h, l, c = series_from(synth(300, lambda i: 100 + i * 0.5))
snap = latest([{"high": x, "low": y, "close": z} for x, y, z in zip(h, l, c)])
check("momentum BULLISH", snap.momentum == BULLISH, snap.momentum)
check("trend BULLISH", snap.trend == BULLISH, snap.trend)
check("aligned_up True", snap.aligned_up is True)
check("EMA stack is 8>13>21", snap.bullish_stack is True and snap.bearish_stack is False,
      f"e8={snap.ema8} e13={snap.ema13} e21={snap.ema21}")
check("EMA21 above EMA34High", snap.ema21 > snap.ema34_high,
      f"e21={snap.ema21:.3f} e34h={snap.ema34_high:.3f}")

print("\n== 3. monotonic downtrend -> BEARISH / BEARISH ==")
h, l, c = series_from(synth(300, lambda i: 400 - i * 0.5))
snap = latest([{"high": x, "low": y, "close": z} for x, y, z in zip(h, l, c)])
check("momentum BEARISH", snap.momentum == BEARISH, snap.momentum)
check("trend BEARISH", snap.trend == BEARISH, snap.trend)
check("EMA21 below EMA34Low", snap.ema21 < snap.ema34_low,
      f"e21={snap.ema21:.3f} e34l={snap.ema34_low:.3f}")

print("\n== 4. flat series -> SIDEWAYS momentum (stack cannot order) ==")
h, l, c = series_from(synth(300, lambda i: 100.0))
snap = latest([{"high": x, "low": y, "close": z} for x, y, z in zip(h, l, c)])
check("momentum SIDEWAYS", snap.momentum == SIDEWAYS, snap.momentum)
check("trend SIDEWAYS", snap.trend == SIDEWAYS, snap.trend)
check("not aligned either way", not snap.aligned_up and not snap.aligned_down)

print("\n== 5. THE CRITICAL CASE: Momentum and Trend DISAGREE ==")
# Empirically located (scratch/find_divergence.py): a flat 200-bar plateau
# followed by a very mild 40-bar drift. The short stack (8:13:21) turns
# immediately, but EMA34High -- an EMA of the HIGH series, still anchored on the
# plateau -- has not been cleared by EMA21. ThinkScript therefore yields
# Momo=Bullish with Trend=Sideways. This is the case that must NOT be reported
# as an aligned setup, and it is the whole reason the two labels are separate.
path_up = [100.0] * 200 + [100 + i * 0.05 for i in range(1, 40)]
h, l, c = series_from(path_up)
snap = latest([{"high": x, "low": y, "close": z} for x, y, z in zip(h, l, c)])
print(f"   e8={snap.ema8:.3f} e13={snap.ema13:.3f} e21={snap.ema21:.3f} "
      f"e34h={snap.ema34_high:.3f} e34l={snap.ema34_low:.3f}")
check("bullish stack detected (Momo turns first)", snap.bullish_stack is True)
check("EMA21 still BELOW EMA34High", snap.ema21 < snap.ema34_high,
      f"{snap.ema21:.3f} < {snap.ema34_high:.3f}")
check("momentum BULLISH but trend SIDEWAYS",
      snap.momentum == BULLISH and snap.trend == SIDEWAYS,
      f"momo={snap.momentum} trend={snap.trend}")
check("NOT aligned_up (Momo alone never confers alignment)",
      snap.aligned_up is False)

# Mirror: mild drift down -> Momentum BEARISH, Trend SIDEWAYS.
path_down = [100.0] * 200 + [100 - i * 0.05 for i in range(1, 40)]
h, l, c = series_from(path_down)
snap2 = latest([{"high": x, "low": y, "close": z} for x, y, z in zip(h, l, c)])
print(f"   e8={snap2.ema8:.3f} e13={snap2.ema13:.3f} e21={snap2.ema21:.3f} "
      f"e34h={snap2.ema34_high:.3f} e34l={snap2.ema34_low:.3f}")
check("mirror: bearish stack, EMA21 ABOVE EMA34Low",
      snap2.bearish_stack is True and snap2.ema21 > snap2.ema34_low,
      f"e21={snap2.ema21:.3f} e34l={snap2.ema34_low:.3f}")
check("mirror: momentum BEARISH but trend SIDEWAYS",
      snap2.momentum == BEARISH and snap2.trend == SIDEWAYS,
      f"momo={snap2.momentum} trend={snap2.trend}")
check("mirror: NOT aligned_down", snap2.aligned_down is False)

# And a decisive move DOES align both, proving the threshold is real not vestigial.
path_strong = [100.0] * 200 + [100 + i * 0.4 for i in range(1, 40)]
h, l, c = series_from(path_strong)
snap3 = latest([{"high": x, "low": y, "close": z} for x, y, z in zip(h, l, c)])
check("a decisive ramp DOES align (Momo+Trend both BULLISH)",
      snap3.aligned_up is True, f"e21={snap3.ema21:.2f} e34h={snap3.ema34_high:.2f}")

print("\n== 6. forming vs completed bar ==")
h, l, c = series_from(synth(300, lambda i: 100 + i * 0.5))
bars = [{"high": x, "low": y, "close": z, "date": f"2026-01-{i%28+1:02d}"} for i, (x, y, z) in enumerate(zip(h, l, c))]
completed = latest(bars, forming=False)
forming = latest(bars, forming=True)
check("completed excludes the final bar", completed.index == len(c) - 2, f"index={completed.index}")
check("forming includes the final bar", forming.index == len(c) - 1, f"index={forming.index}")
check("completed flag correct", completed.completed is True and forming.completed is False)

print("\n== 7. transition tracking ==")
h, l, c = series_from(synth(300, lambda i: 100 + i * 0.5))
ser = evaluate_series(h, l, c)
track = transition_track(ser)
check("bars_since_alignment counts the run", track["bars_since_alignment"] > 1,
      f"{track['bars_since_alignment']} bars")
check("previous_state present", track["previous_state"] is not None)
check("not newly aligned mid-trend", track["newly_aligned"] is False)
check("no lost alignment", track["lost_alignment"] is False)

print("\n== 8. nobody is aligned without warmup ==")
h, l, c = series_from(synth(30, lambda i: 100 + i))
ser = evaluate_series(h, l, c)
check("no aligned states pre-warmup",
      not any(s.aligned_up or s.aligned_down for s in ser))

print("\n== 9. rule identity is carried on every snapshot ==")
check("rule version stamped", snap.rule_version == "tops_multitrend_v4", snap.rule_version)

print(f"\nRESULT: {ok} passed, {fail} failed")
