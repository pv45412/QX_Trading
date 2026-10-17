"""Scratch: why do the split and the per-trade sum disagree?"""
import os
import sys
from collections import Counter

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import requests

d = requests.get("http://127.0.0.1:8790/api/report",
                 params={"account": "79425050", "days": 400}, timeout=600).json()
trades = d.get("closed_trades") or []
print("trades returned:", len(trades), "| performance.closed_trades:", d["performance"]["closed_trades"])
print("asset_type counts:", dict(Counter(t.get("asset_type") for t in trades)))

opt = [t for t in trades if t["asset_type"] == "OPTION"]
print("\noption trades:", len(opt), "sum:", round(sum(t["realized"] for t in opt), 2))
print("first 8 option trades:")
for t in opt[:8]:
    print("   ", t["closed_at"][:10], t["symbol"], "qty", t["qty"], "realized", t["realized"])

# What do the symbols look like for options vs the asset types we expect?
syms = Counter(t["symbol"] for t in trades)
print("\ntop symbols:", syms.most_common(12))

# Compare against the full (untruncated) trade list from the engine.
sys.path.insert(0, r"C:\Project\2026\src")
from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402
from qx.brokers.schwab.client import SchwabApiClient  # noqa: E402
from qx.config.settings import get_settings  # noqa: E402
from qx.reporting.pnl_engine import realized_pnl  # noqa: E402
from qx.reporting.schwab_activity import SchwabActivityReader  # noqa: E402

settings = get_settings()
reader = SchwabActivityReader(SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url))
ref = next(r for r in reader.accounts() if r.account_number == "79425050")
activity = reader.transactions(ref.hash_value, days=400)
full = realized_pnl(activity.transactions)["trades"]
print("\nengine full trades:", len(full))
print("engine asset counts:", dict(Counter(t["asset_type"] for t in full)))
full_opt = [t for t in full if t["asset_type"] == "OPTION"]
print("engine OPTION sum:", round(sum(t["realized"] for t in full_opt), 2))
print("engine OPTION count:", len(full_opt))

# The API returned only the first N trades; check the truncation.
print("\nAPI slice length:", len(trades), "-> engine total:", len(full))
