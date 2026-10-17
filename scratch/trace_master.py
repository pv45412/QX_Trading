"""Scratch: why does the trade latch never fire? Trace the gate conditions."""
import math
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.master_auto import evaluate_series  # noqa: E402


def bars_from(closes, noise=0.0):
    highs = [c + 0.5 + noise for c in closes]
    lows = [c - 0.5 for c in closes]
    return [{"open": closes[i - 1] if i else c, "high": highs[i], "low": lows[i],
             "close": c, "volume": 1000.0, "date": f"d{i}"}
            for i, c in enumerate(closes)]


# A wavy uptrend that repeatedly makes new highs then pulls back.
path = [100 + i * 0.25 + math.sin(i / 7) * 7 for i in range(320)]
series = evaluate_series(bars_from(path))
warm = [x for x in series if x.warmup_ok]
print("bars evaluated:", len(series), " warm:", len(warm))

counts = {}
for x in warm:
    for flag in ("bull_stack", "bear_stack", "bull_regime", "bear_regime", "bull_build",
                 "bear_build", "call_watch", "put_watch", "call_ready", "put_ready",
                 "call_active", "put_active"):
        if getattr(x, flag):
            counts[flag] = counts.get(flag, 0) + 1
print("flag true-counts:", counts)

print("\nlast warm bar:")
x = warm[-1]
for f in ("bull_stack", "bull_regime", "bull_build", "call_watch", "call_ready", "call_active",
          "put_active", "price_state", "setup_label"):
    print(f"   {f:<14} {getattr(x, f)}")
print(f"   close={path[x.index]:.2f} wave_high={x.wave_high:.2f} wave_low={x.wave_low:.2f}")
print(f"   wave_slow={x.wave_slow:.2f}  (bull_regime needs wave_slow > wave_high)")
print(f"   rvol={x.rvol_display}  volume_ok={x.volume_ok}")

# Why is bull_regime so rare? wave_slow (VWave of close over 21) vs wave_high
# (VWave of HIGH over 34). The high series sits above close, and 34 > 21, so
# wave_high is both higher AND slower -- wave_slow > wave_high is a hard test.
print("\nwave relationship diagnostics over warm bars:")
diffs = [(x.wave_slow - x.wave_high) for x in warm if x.wave_slow and x.wave_high]
print(f"   wave_slow - wave_high: min={min(diffs):.3f} max={max(diffs):.3f} "
      f"positive_in={sum(1 for d in diffs if d > 0)}/{len(diffs)}")

# Is call_active reachable? It needs call_ready AND bull_candle AND (break or cross).
bull_candles = [x for x in warm if x.bull_stack and x.call_ready]
print(f"\nbars with call_ready: {sum(1 for x in warm if x.call_ready)}")
print(f"bars with bull_regime: {sum(1 for x in warm if x.bull_regime)}")
print(f"bars with bear_regime: {sum(1 for x in warm if x.bear_regime)}")

# Try a STRONGER, smoother trend so wave_slow can exceed wave_high.
print("\n--- stronger trends ---")
for label, p in (
    ("steady +1.0/bar", [100 + i * 1.0 for i in range(320)]),
    ("accel", [100 + i * 0.5 + (i ** 1.3) * 0.01 for i in range(320)]),
    ("strong +2.0/bar", [100 + i * 2.0 for i in range(320)]),
):
    s = evaluate_series(bars_from(p))
    w = [x for x in s if x.warmup_ok]
    reg = sum(1 for x in w if x.bull_regime)
    rdy = sum(1 for x in w if x.call_ready)
    act = sum(1 for x in w if x.call_active)
    sig = sum(1 for x in w if x.call_signal)
    print(f"   {label:<18} bull_regime={reg:<4} call_ready={rdy:<4} call_active={act:<4} signals={sig}")
    if w:
        x = w[-1]
        print(f"        wave_slow={x.wave_slow:.2f} wave_high={x.wave_high:.2f} "
              f"close={p[x.index]:.2f}")
