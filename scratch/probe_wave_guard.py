"""Isolate WHICH wave-length ordering makes entries impossible."""
import glob
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical  # noqa: E402
from qx.explorer import master_auto  # noqa: E402

ENTRY_FIELDS = ("trade_direction", "call_ready", "put_ready",
                "call_candidate", "put_candidate")

symbols = historical.discover_symbols(window="2y")[:40]
series = []
for sym in symbols:
    try:
        loaded = historical.load_bars(sym)
    except Exception:
        continue
    if loaded and getattr(loaded, "bars", None):
        series.append((sym, loaded.bars))
print(f"symbols loaded: {len(series)}\n")

COMBOS = [
    ("A  base 8/13/21/34", {}),
    ("B  fast=13  (13/13/21/34)", {"fast_wave_length": 13}),
    ("C  slow=34  (8/13/34/34)", {"slow_wave_length": 34}),
    ("D  fast=13 slow=34 (13/13/34/34)",
     {"fast_wave_length": 13, "slow_wave_length": 34}),
    ("E  mid=8   (8/8/21/34)", {"mid_wave_length": 8}),
    ("F  fast=9  (9/13/21/34)", {"fast_wave_length": 9}),
    ("G  mid=34  (8/34/21/34)", {"mid_wave_length": 34}),
    ("H  wave=13 (8/13/21/13)", {"wave_length": 13}),
]

print(f"{'config':<34} {'entry bars':>10} {'snapshots':>10} {'nonzero':>8}")
print("-" * 68)
for label, override in COMBOS:
    entry_bars = 0
    snaps = 0
    for _sym, bar_list in series:
        try:
            out = master_auto.evaluate_series(bar_list, override)
        except Exception as exc:
            print(f"{label:<34} RAISED: {exc}")
            break
        snaps += len(out)
        for snap in out:
            hit = False
            for field in ENTRY_FIELDS:
                value = getattr(snap, field, None)
                if value not in (None, False, "", 0, "NONE", "WAIT"):
                    hit = True
            if hit:
                entry_bars += 1
    else:
        print(f"{label:<34} {entry_bars:>10} {snaps:>10} "
              f"{'yes' if entry_bars else 'NO':>8}")
