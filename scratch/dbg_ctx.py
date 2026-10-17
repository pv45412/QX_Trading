import os, sys, traceback
os.chdir(r"C:\Project\2026"); sys.path.insert(0, r"C:\Project\2026\src")
from qx.backtesting import historical
from qx.explorer import market_phases, master_auto, momo_trend
u, _ = historical.build_universe(limit=3)
sym = list(u)[0]
bars = u[sym].bars
print("symbol", sym, "bars", len(bars))
for name, fn in (("master_auto", master_auto.evaluate_series),
                 ("market_phases", market_phases.evaluate_series),
                 ("momo_trend", momo_trend.evaluate_series)):
    try:
        r = fn(bars)
        print(f"  {name}: OK type={type(r).__name__} len={len(r)} first={r[0] if r else None}")
    except Exception:
        print(f"  {name}: FAILED")
        traceback.print_exc()
