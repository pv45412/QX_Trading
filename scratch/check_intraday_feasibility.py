"""Can the intraday VWAP gate be tested, and does it change anything?

The daily backtest tests a REDUCED rule set: master_auto's VWAP filter is gated
by `is_intraday`, so on daily bars it never activates. That leaves one open
question: does the shipped system behave differently on 5-minute bars?

Answering it needs intraday history. This measures exactly how much exists, and
what the VWAP gate would actually add, rather than assuming.
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(r"C:\Project\2026")
INTRADAY = ROOT / "data" / "cache" / "bars" / "intraday"

print("=" * 88)
print("A. HOW MUCH INTRADAY HISTORY EXISTS?")
print("=" * 88)
files = sorted(INTRADAY.glob("*.csv"))
print(f"  files: {len(files)}")
total_rows = 0
spans = []
for path in files:
    with path.open(encoding="utf-8", errors="ignore") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        continue
    total_rows += len(rows)
    first_key = "date" if "date" in rows[0] else "Datetime"
    spans.append((path.name, len(rows), rows[0][first_key], rows[-1][first_key]))

print(f"  total rows: {total_rows:,}")
print()
print(f"  {'file':<22} {'rows':>6}  {'from':<22} {'to':<22}")
print("  " + "-" * 76)
for name, count, start, end in spans[:20]:
    print(f"  {name:<22} {count:>6}  {str(start)[:20]:<22} {str(end)[:20]:<22}")

# How many distinct TRADING DAYS does the 5m data cover?
print()
print("=" * 88)
print("B. HOW MANY DISTINCT TRADING DAYS?")
print("=" * 88)
day_counts = {}
for path in files:
    if "5m" not in path.name:
        continue
    with path.open(encoding="utf-8", errors="ignore") as handle:
        rows = list(csv.DictReader(handle))
    key = "date" if rows and "date" in rows[0] else "Datetime"
    days = set()
    for row in rows:
        stamp = str(row.get(key) or "")
        days.add(stamp[:10])
    day_counts[path.stem] = len(days)

for name, count in sorted(day_counts.items()):
    print(f"  {name:<24} {count:>3} distinct day(s)")

if day_counts:
    typical = max(day_counts.values())
    print()
    print(f"  deepest 5m history: {typical} trading days")

print()
print("=" * 88)
print("C. THE BAR THE STUDY NEEDS vs WHAT EXISTS")
print("=" * 88)
sys.path.insert(0, str(ROOT / "src"))
from qx.explorer.master_auto import DEFAULT_CONFIG  # noqa: E402

# The study needs a warm-up before its first valid snapshot.
min_bars = None
for key in ("min_history_bars", "warmup_bars", "min_bars"):
    if key in DEFAULT_CONFIG:
        min_bars = DEFAULT_CONFIG[key]
        break
print(f"  study warm-up requirement : {min_bars} bars")
print(f"  daily data available      : ~500 bars per symbol  -> testable")
print(f"  5m data available         : ~{typical * 78 if day_counts else 0} bars per symbol "
      f"({typical} days x 78 bars/day)")
print()
if day_counts and typical * 78 >= (min_bars or 200):
    print("  -> Bar count is sufficient in principle.")
else:
    print("  -> Bar count is marginal.")

print()
print("=" * 88)
print("D. THE REAL LIMIT — INDEPENDENT SAMPLES")
print("=" * 88)
if day_counts:
    days = typical
    print(f"  The 5m cache covers {days} trading days.")
    print(f"  Those days are NOT {days} independent samples: they overlap the same")
    print(f"  market regime, and the same handful of news events drive all of them.")
    print()
    print(f"  Compare: the daily backtest used ~500 days x 400 symbols = 6,044 trades")
    print(f"  and STILL could not establish a robust edge across folds.")
    print(f"  A {days}-day intraday window is roughly {days/500:.1%} of that span.")
    print()
    print("  -> CONCLUSION: the intraday variant CANNOT be validated on this data.")
    print("     It can show that the VWAP gate activates and changes signals, which")
    print("     is a correctness check. It cannot show whether the result is an edge.")

print()
print("=" * 88)
print("E. WHAT THE VWAP GATE WOULD ACTUALLY DO")
print("=" * 88)
print("  From master_auto.py:")
print("    call_exit_base = close < wc or (use_vwap_filter and is_intraday and close < vwap) or bear_stack")
print("    call_ready     = bull_regime and close > wh and vwap_call_ok and volume_ok")
print()
print("  On daily bars `is_intraday` is False, so the VWAP term is skipped entirely.")
print("  On 5m bars it becomes live and can BOTH admit and veto entries and exits.")
print()
print("  So the daily backtest is not wrong, it is NARROWER than the shipped system:")
print("  it measures the study minus its intraday filter. Whether adding that filter")
print("  helps or hurts is unknown, and this data cannot settle it.")
