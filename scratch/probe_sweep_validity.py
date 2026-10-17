"""Is the config actually reaching evaluate_series, or did my sweep silently no-op?

Three rows in run_sweep.py returned EXACTLY the base result after changing a gate:
  supertrend bias OFF, bias confirm 2->3/4, RSI band, ATR stop multiplier.
If the config is being read, at least some of those MUST change the output. If none do,
the sweep harness is broken and its numbers mean nothing.
"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import qx.explorer.master_auto as master_auto  # noqa: E402
from qx.backtesting import historical  # noqa: E402

universe, _ = historical.build_universe(window="2y")
symbol = sorted(universe.keys())[0]
bars = universe[symbol].bars
print(f"probe symbol: {symbol} ({len(bars)} bars)")

BASE = dict(master_auto.DEFAULTS)
print("\nDEFAULTS signature:", sorted(BASE.items())[:3], "...")

# 1) does passing config= as an ARGUMENT work?
a = master_auto.evaluate_series(bars, minutes=1440)
b = master_auto.evaluate_series(bars, minutes=1440, config={"atr_stop_multiplier": 3.0})
print("\n[argument path] base len:", len(a), " config len:", len(b))
if a and b:
    print("  base active_stop   :", a[-1].active_stop)
    print("  config active_stop :", b[-1].active_stop)
    print("  DIFFER:", a[-1].active_stop != b[-1].active_stop)

# 2) does mutating DEFAULTS work?  (what run_sweep.py relied on)
master_auto.DEFAULTS = {**BASE, "atr_stop_multiplier": 3.0}
c = master_auto.evaluate_series(bars, minutes=1440)
print("\n[mutate DEFAULTS path] len:", len(c))
if c:
    print("  mutated active_stop:", c[-1].active_stop)
    print("  DIFFER from base   :", c[-1].active_stop != a[-1].active_stop)
master_auto.DEFAULTS = BASE

# 3) which gates actually change ANY published field?
def signature(series):
    if not series:
        return None
    snap = series[-1]
    return tuple(getattr(snap, f) for f in
                 ("trade_direction", "bias_state", "price_state", "active_stop",
                  "call_ready", "put_ready", "rvol_display", "supertrend"))

base_sig = signature(a)
print("\n[gate sensitivity] does each gate change the last-bar snapshot?")
for config, label in [
    ({"use_supertrend_bias": False}, "supertrend bias OFF"),
    ({"bias_flip_confirm_bars": 4}, "bias confirm 4"),
    ({"rsi_overbought": 80.0, "rsi_oversold": 20.0}, "RSI 80/20"),
    ({"atr_stop_multiplier": 3.0}, "ATR x3"),
    ({"min_relative_volume": 2.0}, "RVOL 2.0"),
    ({"wave_length": 55}, "wave 55"),
    ({"trigger_length": 20}, "trigger 20"),
]:
    try:
        s = master_auto.evaluate_series(bars, minutes=1440, config=config)
        changed = signature(s) != base_sig
    except Exception as exc:  # noqa: BLE001
        changed = f"ERROR {type(exc).__name__}: {exc}"
    print(f"  {label:<22} changed={changed}")
