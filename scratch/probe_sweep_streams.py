"""Does a config change alter the TRADE STREAM? The last-bar test was too narrow.

A gate can be inert on the final bar of one symbol yet active on thousands of bars
across 1,196 symbols. This counts how many bars differ per gate, across many symbols.
"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import qx.explorer.master_auto as master_auto  # noqa: E402
from qx.backtesting import historical  # noqa: E402

universe, _ = historical.build_universe(window="2y")
symbols = sorted(universe.keys())[:40]
print(f"checking {len(symbols)} symbols\n")

FIELDS = ("trade_direction", "bias_state", "call_ready", "put_ready",
          "call_candidate", "put_candidate", "active_stop")

gates = [
    ({"use_supertrend_bias": False}, "supertrend bias OFF"),
    ({"bias_flip_confirm_bars": 4}, "bias confirm 4"),
    ({"rsi_overbought": 80.0, "rsi_oversold": 20.0}, "RSI 80/20"),
    ({"atr_stop_multiplier": 3.0}, "ATR x3"),
    ({"min_relative_volume": 2.0}, "RVOL 2.0"),
    ({"wave_length": 55}, "wave 55"),
    ({"trigger_length": 20}, "trigger 20"),
    ({"use_vwap_filter": False}, "VWAP filter OFF"),
    ({"use_volume_filter": False}, "volume filter OFF"),
]

base = {}
for sym in symbols:
    bars = universe[sym].bars
    base[sym] = master_auto.evaluate_series(bars, minutes=1440)

print(f"{'gate':<22} {'bars changed':>12}  {'first differing field':<24}")
print("-" * 62)
for config, label in gates:
    total = 0
    example = "-"
    for sym in symbols:
        bars = universe[sym].bars
        try:
            series = master_auto.evaluate_series(bars, minutes=1440, config=config)
        except Exception:  # noqa: BLE001
            continue
        for old, new in zip(base[sym], series):
            for field in FIELDS:
                if getattr(old, field, None) != getattr(new, field, None):
                    total += 1
                    if example == "-":
                        example = field
                    break
    print(f"{label:<22} {total:>12}  {example:<24}")
