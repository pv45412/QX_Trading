"""Parameter sensitivity: is the edge in the gates, or simply absent?

Sweeps the three gates that most plausibly control selectivity, on the SAME cleaned
universe and the SAME study code, changing one threshold at a time. Everything here
re-uses master_auto via simulate; no rule is reimplemented.
"""
import json
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.backtesting import historical, metrics, simulate  # noqa: E402
import qx.explorer.master_auto as master_auto  # noqa: E402

universe, report = historical.build_universe(window="2y")
bars_only = {s: b.bars for s, b in universe.items()}
print(f"universe: {len(bars_only)} symbols\n")

base_cfg = dict(master_auto.CONFIG) if hasattr(master_auto, "CONFIG") else None
print("config attribute present:", base_cfg is not None)
if base_cfg is not None:
    print("keys:", sorted(base_cfg.keys()))
    print(json.dumps({k: v for k, v in base_cfg.items()
                      if isinstance(v, (int, float, bool))}, indent=2, default=str))
