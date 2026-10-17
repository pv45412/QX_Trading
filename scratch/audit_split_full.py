"""Scratch: reconcile the split against the FULL trade set (not the API slice)."""
import os
import sys
from collections import Counter

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import requests

from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402
from qx.brokers.schwab.client import SchwabApiClient  # noqa: E402
from qx.config.settings import get_settings  # noqa: E402
from qx.reporting.pnl_engine import _bucket, _month_days, _trade_split, realized_pnl  # noqa: E402
from qx.reporting.schwab_activity import SchwabActivityReader  # noqa: E402

settings = get_settings()
reader = SchwabActivityReader(SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url))

ok = True
for account, label in (("79425050", "MARGIN"), ("84342410", "CASH")):
    ref = next(r for r in reader.accounts() if r.account_number == account)
    activity = reader.transactions(ref.hash_value, days=400)
    trades = realized_pnl(activity.transactions)["trades"]

    split = _trade_split(trades)
    months = _bucket(trades, "month")
    days_map = _month_days(trades)
    by_day = _bucket(trades, "day")

    direct_opt = round(sum(t["realized"] for t in trades if t["asset_type"] == "OPTION"), 2)
    direct_stk = round(sum(t["realized"] for t in trades
                           if t["asset_type"] in ("EQUITY", "ETF", "BOND")), 2)
    direct_fut = round(sum(t["realized"] for t in trades if t["asset_type"] == "FUTURE"), 2)
    direct_fund = round(sum(t["realized"] for t in trades
                            if t["asset_type"] in ("COLLECTIVE_INVESTMENT", "MUTUAL_FUND")), 2)
    total = round(sum(t["realized"] for t in trades), 2)

    month_sum = round(sum(m["realized"] for m in months), 2)
    day_sum = round(sum(d["realized"] for d in by_day), 2)
    nested_day_sum = round(sum(d["realized"] for v in days_map.values() for d in v), 2)

    checks = [
        ("options split", split["options"]["realized"], direct_opt),
        ("stocks split", split["stocks"]["realized"], direct_stk),
        ("futures split", split["futures"]["realized"], direct_fut),
        ("funds split", split["funds"]["realized"], direct_fund),
        ("split total", split["total_realized"], total),
        ("month sum", month_sum, total),
        ("day sum", day_sum, total),
        ("nested day sum", nested_day_sum, total),
    ]
    print("=" * 70)
    print(f"{label} {ref.masked}: {len(trades)} closed trades, total realized {total:,.2f}")
    for name, got, want in checks:
        good = abs(got - want) < 0.01
        ok = ok and good
        print(f"   {'OK  ' if good else 'FAIL'} {name:<16} got {got:>12,.2f}  want {want:>12,.2f}")
    print(f"   options {split['options']['realized']:>12,.2f} ({split['options']['trades']} trades)"
          f"   stocks {split['stocks']['realized']:>11,.2f} ({split['stocks']['trades']} trades)")
    print(f"   months={len(months)}  days={len(by_day)}  nested day rows={nested_day_sum and sum(len(v) for v in days_map.values())}")
    print(f"   asset types: {dict(Counter(t['asset_type'] for t in trades))}")

print("\nALL RECONCILED" if ok else "\nRECONCILIATION FAILED")
