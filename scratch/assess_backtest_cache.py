"""Scratch: how usable is the local bar cache as a backtest universe?"""
import csv
import os
from collections import Counter

CACHE = r"C:\Project\2026\data\cache\bars"
WARMUP = 136          # MASTER AUTO warmup
MIN_TESTABLE = WARMUP + 60   # enough to warm up and still trade a little

files = [f for f in os.listdir(CACHE) if f.endswith(".csv")]
print(f"cache files: {len(files)}")

# Group by symbol and by window suffix, so we know what we actually hold.
by_symbol: dict[str, dict[str, int]] = {}
for name in files:
    stem = name[:-4]
    symbol, _, window = stem.rpartition("_")
    if not symbol:
        continue
    path = os.path.join(CACHE, name)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            rows = sum(1 for _ in csv.reader(handle)) - 1   # minus header
    except OSError:
        continue
    by_symbol.setdefault(symbol, {})[window] = max(0, rows)

print(f"distinct symbols: {len(by_symbol)}")
windows = Counter(w for d in by_symbol.values() for w in d)
print(f"windows present : {dict(windows)}")

# Best available history per symbol.
best: dict[str, int] = {s: max(d.values()) for s, d in by_symbol.items() if d}
lengths = sorted(best.values(), reverse=True)
if lengths:
    print(f"\nbest-history rows per symbol:")
    print(f"  max    : {lengths[0]}")
    print(f"  median : {lengths[len(lengths)//2]}")
    print(f"  min    : {lengths[-1]}")

for threshold in (500, 400, 300, 200, MIN_TESTABLE, WARMUP):
    n = sum(1 for v in best.values() if v >= threshold)
    print(f"  symbols with >= {threshold:>4} bars : {n}")

usable = [s for s, v in best.items() if v >= MIN_TESTABLE]
print(f"\nUSABLE for a MASTER AUTO backtest (>= {MIN_TESTABLE} bars): {len(usable)} symbols")
if usable:
    print("  sample:", ", ".join(sorted(usable)[:20]))

# Check the date span of a long one, to confirm dates are real and ordered.
longest = max(best.items(), key=lambda kv: kv[1])[0]
candidates = [f for f in files if f.startswith(longest + "_")]
if candidates:
    path = os.path.join(CACHE, candidates[0])
    with open(path, "r", encoding="utf-8") as handle:
        reader = list(csv.DictReader(handle))
    print(f"\n{longest}: {len(reader)} rows")
    print(f"  first: {reader[0]['date']}  close={reader[0]['close']}")
    print(f"  last : {reader[-1]['date']}  close={reader[-1]['close']}")
    dates = [r["date"] for r in reader]
    print(f"  dates ascending: {dates == sorted(dates)}")
    print(f"  unique dates   : {len(set(dates))} of {len(dates)}")
