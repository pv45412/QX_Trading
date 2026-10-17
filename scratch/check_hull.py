"""Scratch: is the Hull MA port correct? ThinkScript rounds sqrt(n) and n/2."""
import math
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.market_phases import hull, _wma  # noqa: E402


def hma_reference(values, period):
    """Textbook HMA, computed only where all windows are full."""
    half = period // 2
    root = int(math.sqrt(period))
    if half < 1 or root < 1:
        return None
    w_half = _wma(values, half)
    w_full = _wma(values, period)
    raw = [None if (a is None or b is None) else 2 * a - b for a, b in zip(w_half, w_full)]
    first = next((i for i, v in enumerate(raw) if v is not None), None)
    if first is None:
        return None
    tail = raw[first:]
    smoothed = _wma([float(v) for v in tail], root)
    for value in reversed(smoothed):
        if value is not None:
            return value
    return None


line = [100.0 + i for i in range(60)]
print("straight line, period=10")
print("   last value      :", line[-1])
print("   ported hull[-1] :", hull(line, 10)[-1])
print("   reference       :", hma_reference(line, 10))

# A straight line has WMA(n/2) lagging less than WMA(n); 2*a-b overshoots slightly
# then the final WMA(root) smooths it. Exact equality is NOT expected for HMA on a
# line unless the line is flat. Check the correct invariant instead.
flat = [100.0] * 60
print("\nflat series (HMA must equal the constant exactly)")
print("   ported hull[-1] :", hull(flat, 10)[-1])
print("   expected        : 100.0")

# Monotone increasing line: HMA should sit ABOVE the line (leading), not equal it.
print("\nline invariant: HMA leads a rising line")
print("   hull[-1] > line[-1] ?", hull(line, 10)[-1] > line[-1])

# Compare against a hand-computed HMA for a known small case.
small = [1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
print("\nsmall case n=20, period=4 (half=2, root=2)")
print("   ported  :", hull(small, 4)[-1])
print("   ref     :", hma_reference(small, 4))
w2 = _wma(small, 2)[-1]
w4 = _wma(small, 4)[-1]
print(f"   wma2={w2} wma4={w4} 2*w2-w4={2*w2-w4}")
