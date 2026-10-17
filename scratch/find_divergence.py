"""Scratch: find a real series where Momo and Trend disagree, then assert on it."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.momo_trend import BEARISH, BULLISH, SIDEWAYS, evaluate_series, warmup_bars  # noqa: E402

WARM = warmup_bars()


def build(path):
    highs = [c + 1.0 for c in path]
    lows = [c - 1.0 for c in path]
    return highs, lows, path


def probe(label, path):
    h, l, c = build(path)
    series = evaluate_series(h, l, c)
    s = series[-1]
    print(f"{label:<34} momo={str(s.momentum):<8} trend={str(s.trend):<8} "
          f"e21={s.ema21:>8.2f} e34h={s.ema34_high:>8.2f} e34l={s.ema34_low:>8.2f} "
          f"stackBull={s.bullish_stack} stackBear={s.bearish_stack}")
    return s


print(f"warmup={WARM}\n")
# THE insight: EMA34High is an EMA of the HIGH series. To keep it ABOVE EMA21 of
# close while the short stack turns bullish, price must rally only slightly and the
# high series must be dominated by the earlier, higher plateau.
cases = {
    "flat 200 then tiny 10% ramp": [100.0] * 200 + [100 + i * 1.0 for i in range(1, 40)],
    "flat 200 then flat 40": [100.0] * 240,
    "slow bleed then mild bounce": [200 - i * 0.2 for i in range(200)] + [160 + i * 0.15 for i in range(40)],
    "high plateau then dip then mild recovery":
        [150.0] * 120 + [120 + i * 0.05 for i in range(80)] + [124 + i * 0.1 for i in range(40)],
    "rise then small pullback": [100 + i * 0.8 for i in range(200)] + [260 - i * 0.5 for i in range(40)],
    "rise then deep pullback": [100 + i * 0.8 for i in range(200)] + [260 - i * 2.0 for i in range(40)],
}
results = {}
for label, path in cases.items():
    results[label] = probe(label, path)

print("\n-- searching for a genuine Momo/Trend divergence --")
found_bull = found_bear = None
for amp in [0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 3.0]:
    path = [100.0] * 200 + [100 + i * amp for i in range(1, 40)]
    s = probe(f"flat200 + ramp amp={amp}", path)
    if s.momentum == BULLISH and s.trend == SIDEWAYS and found_bull is None:
        found_bull = (amp, path)
for amp in [-0.05, -0.1, -0.2, -0.4, -0.8, -1.5, -3.0]:
    path = [100.0] * 200 + [100 + i * amp for i in range(1, 40)]
    s = probe(f"flat200 + drop amp={amp}", path)
    if s.momentum == BEARISH and s.trend == SIDEWAYS and found_bear is None:
        found_bear = (amp, path)

print("\nDIVERGENCE (bullish stack, sideways trend):", "FOUND" if found_bull else "not found",
      f"amp={found_bull[0]}" if found_bull else "")
print("DIVERGENCE (bearish stack, sideways trend):", "FOUND" if found_bear else "not found",
      f"amp={found_bear[0]}" if found_bear else "")
