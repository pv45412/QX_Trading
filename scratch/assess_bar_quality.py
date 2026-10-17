"""Scratch: are the cached bars usable? Headers, ordering, and SPLIT adjustment."""
import csv
import os
from collections import Counter

CACHE = r"C:\Project\2026\data\cache\bars"
files = [f for f in os.listdir(CACHE) if f.endswith(".csv")]

print("=== header variants across the cache ===")
headers = Counter()
for name in files[:400]:
    try:
        with open(os.path.join(CACHE, name), "r", encoding="utf-8", errors="ignore") as handle:
            headers[",".join(next(csv.reader(handle)))] += 1
    except (OSError, StopIteration):
        continue
for header, count in headers.most_common(6):
    print(f"  {count:>4}x  {header}")


def load(symbol, window="2y"):
    path = os.path.join(CACHE, f"{symbol}_{window}.csv")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    out = []
    for row in rows:
        try:
            out.append({
                "date": row.get("date") or row.get("Date") or "",
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row.get("volume") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


print("\n=== ordering and uniqueness ===")
for symbol in ("AAPL", "NVDA", "AMD", "SPY"):
    bars = load(symbol)
    if not bars:
        print(f"  {symbol}: not cached")
        continue
    dates = [b["date"] for b in bars]
    print(f"  {symbol:<5} {len(bars):>4} bars  {dates[0]} -> {dates[-1]}  "
          f"ascending={dates == sorted(dates)}  unique={len(set(dates)) == len(dates)}")

print("\n=== SPLIT ADJUSTMENT: look for single-bar gaps that indicate an unadjusted split ===")
# An unadjusted split shows as one enormous overnight gap that never reverts.
suspects = []
checked = 0
for name in sorted(files):
    if not name.endswith("_2y.csv"):
        continue
    symbol = name[:-7]
    bars = load(symbol)
    if not bars or len(bars) < 60:
        continue
    checked += 1
    worst = 0.0
    worst_date = ""
    for i in range(1, len(bars)):
        prev, cur = bars[i - 1]["close"], bars[i]["close"]
        if prev <= 0:
            continue
        move = abs(cur / prev - 1.0)
        if move > worst:
            worst, worst_date = move, bars[i]["date"]
    if worst > 0.45:                     # a >45% single-day move is almost always a split
        suspects.append((symbol, worst, worst_date))
    if checked >= 300:
        break

print(f"  scanned {checked} symbols with >=60 bars")
print(f"  with a >45% single-bar move: {len(suspects)}")
for symbol, move, date in suspects[:12]:
    print(f"     {symbol:<6} {move*100:>6.1f}%  on {date}")

print("\n=== cross-check a known split ===")
# NVDA split 10:1 in June 2024; AVGO 10:1 in July 2024. Both predate this window,
# so a clean series here does NOT prove adjustment. Look for ANY large gap instead.
for symbol in ("NVDA", "AVGO", "AAPL"):
    bars = load(symbol)
    if not bars:
        continue
    gaps = []
    for i in range(1, len(bars)):
        prev, cur = bars[i - 1]["close"], bars[i]["close"]
        if prev > 0 and abs(cur / prev - 1.0) > 0.25:
            gaps.append((bars[i]["date"], round((cur / prev - 1) * 100, 1)))
    print(f"  {symbol:<5} gaps >25%: {gaps if gaps else 'none'}")
