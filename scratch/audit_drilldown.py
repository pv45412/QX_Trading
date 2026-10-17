"""Scratch: verify monthly/day drill-down and the options-vs-stocks split."""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import requests

for account, label in (("79425050", "MARGIN"), ("84342410", "CASH")):
    r = requests.get("http://127.0.0.1:8790/api/report",
                     params={"account": account, "days": 400}, timeout=600)
    if r.status_code != 200:
        print(f"{label}: HTTP {r.status_code} {r.text[:160]}")
        continue
    d = r.json()
    split = d.get("trade_split") or {}
    print("=" * 78)
    print(f"{label} {d['account']['masked']}  closed_trades={d['performance']['closed_trades']}")
    print(f"  OPTIONS : realized {split.get('options', {}).get('realized'):>12,.2f}  "
          f"trades {split.get('options', {}).get('trades'):>5}  "
          f"win {split.get('options', {}).get('win_rate')}  "
          f"PF {split.get('options', {}).get('profit_factor')}")
    print(f"  STOCKS  : realized {split.get('stocks', {}).get('realized'):>12,.2f}  "
          f"trades {split.get('stocks', {}).get('trades'):>5}  "
          f"win {split.get('stocks', {}).get('win_rate')}  "
          f"PF {split.get('stocks', {}).get('profit_factor')}")
    for name in ("futures", "funds"):
        item = split.get(name) or {}
        if item.get("trades"):
            print(f"  {name.upper():<8}: realized {item.get('realized'):>12,.2f}  trades {item.get('trades'):>5}")
    print(f"  TOTAL   : {split.get('total_realized'):,.2f}")
    print(f"  share of realized -> options {split.get('options',{}).get('share_of_realized')} "
          f"stocks {split.get('stocks',{}).get('share_of_realized')}")

    months = d.get("by_month") or []
    days_map = d.get("month_days") or {}
    print(f"  months={len(months)}  day-rows total={sum(len(v) for v in days_map.values())}")
    for m in months[-4:]:
        print(f"    {m['key']}: realized {m['realized']:>11,.2f}  trades {m['trades']:>4}  "
              f"W/L {m['wins']}/{m['losses']}  opt {m['options']:>10,.2f}  stk {m['equity']:>8,.2f}  "
              f"best {m['best']['symbol'] if m['best'] else '-'}")
        for day in (days_map.get(m["key"]) or [])[:3]:
            print(f"        {day['key']}: {day['realized']:>10,.2f}  trades {day['trades']:>3}  "
                  f"opt {day['options']:>9,.2f}  stk {day['equity']:>8,.2f}")

    # The split must reconcile with per-trade sums, not just look plausible.
    trades = d.get("closed_trades") or []
    opt_direct = sum(t["realized"] for t in trades if t["asset_type"] == "OPTION")
    stk_direct = sum(t["realized"] for t in trades if t["asset_type"] in ("EQUITY", "ETF"))
    print(f"  RECONCILE options: api={split.get('options',{}).get('realized'):,.2f} "
          f"direct={opt_direct:,.2f} match={abs(split.get('options',{}).get('realized',0)-opt_direct)<0.01}")
    print(f"  RECONCILE stocks : api={split.get('stocks',{}).get('realized'):,.2f} "
          f"direct={stk_direct:,.2f} match={abs(split.get('stocks',{}).get('realized',0)-stk_direct)<0.01}")
    month_sum = sum(m["realized"] for m in months)
    day_sum = sum(day["realized"] for v in days_map.values() for day in v)
    print(f"  RECONCILE month sum={month_sum:,.2f}  day sum={day_sum:,.2f}  "
          f"trades sum={sum(t['realized'] for t in trades):,.2f}")
