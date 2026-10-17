"""Scratch: pin the RVOL offset and the missing-latch cause."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.explorer.master_auto import evaluate_series  # noqa: E402


def bars(closes, vols):
    return [{"open": closes[i - 1] if i else c, "high": c + 0.5, "low": c - 0.5,
             "close": c, "volume": vols[i], "date": f"d{i}"} for i, c in enumerate(closes)]


print("== RVOL offset probe ==")
closes = [100 + i * 0.4 for i in range(240)]
vols = [1000.0] * 239 + [4000.0]
ser = evaluate_series(bars(closes, vols))
warm = [x for x in ser if x.warmup_ok]
print("last 5 warm bars (index, rvol_display, volume at that index):")
for x in warm[-5:]:
    print(f"   i={x.index:<4} rvol={x.rvol_display:<8} vol={vols[x.index]}  "
          f"avg(prev20)={sum(vols[x.index-20:x.index])/20:.1f}  "
          f"avg(prev20 excl i-1)={sum(vols[max(0,x.index-21):x.index-1])/20:.1f}")

print("\nDESIRED: bar 238 (the spiked completed bar) should report ~4.0")
for x in warm:
    if x.index == 238:
        print(f"   actual rvol at 238 = {x.rvol_display}")
    if x.index == 239:
        print(f"   actual rvol at 239 = {x.rvol_display} (bar 239 excluded when forming=False)")

print("\n== latch probe on a steady trend ==")
p = [100 + i * 1.0 for i in range(320)]
s = evaluate_series(bars(p, [1000.0] * 320))
w = [x for x in s if x.warmup_ok]
print(f"warm bars: {len(w)}")
for flag in ("bull_regime", "call_ready", "call_active", "call_signal", "trade_direction"):
    vals = [getattr(x, flag) for x in w]
    print(f"   {flag:<16} true={sum(1 for v in vals if v)}  distinct={sorted(set(str(v) for v in vals))[:5]}")
print("\nfirst 3 warm bars detail:")
for x in w[:3]:
    print(f"   i={x.index} bull_regime={x.bull_regime} call_ready={x.call_ready} "
          f"call_active={x.call_active} call_signal={x.call_signal} dir={x.trade_direction} "
          f"entry={x.trade_entry} stop={x.active_stop}")
print("\nbars where call_active is true (first 5):")
ca = [x for x in w if x.call_active][:5]
for x in ca:
    print(f"   i={x.index} signal={x.call_signal} dir={x.trade_direction} entry={x.trade_entry}")
print("count call_active:", sum(1 for x in w if x.call_active))
print("count trade_entry not None:", sum(1 for x in w if x.trade_entry is not None))
