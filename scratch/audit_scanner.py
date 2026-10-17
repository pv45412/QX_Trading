"""Scratch: verify the shared scanner module."""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.scanner import market_context, scan_universe, sector_rankings

ctx = market_context()
print("REGIME:", ctx["regime"], "| freshness:", ctx["freshness"])
for p in ctx["proxies"]:
    print("   ", p["symbol"], p["last"], p["change_pct"], p["source"], p["quote_source"])

sectors = sector_rankings()
print(f"\nSECTORS: {sectors['ranked']}/{sectors['declared']} ranked")
for row in sectors["sectors"]:
    print(f"   #{row['rank']:<3} {row['symbol']:<5} {row['sector'][:24]:<24} {row['quadrant']:<10} "
          f"5d={row['rs_5d']} 20d={row['rs_20d']} 60d={row['rs_60d']}")

scan = scan_universe(["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA"])
print(f"\nSCAN verdict={scan['verdict']} symbols={scan['symbols']} actionable={scan['actionable']} "
      f"benchmark_source={scan['benchmark_source']} rule={scan['rule_version']}")
for row in scan["results"]:
    if row.get("error"):
        print("   ", row["symbol"], "ERROR", row["error"])
        continue
    print(f"   {row['symbol']:<6} {row['signal']:<18} score={row['score']:<6} src={row['source']:<7} "
          f"entry={row['entry']} inv={row['invalidation']} tgt={row['target']} R:R={row['risk_reward']}")
    print("        factors:", row["factors"])
print("\nJSON size:", len(json.dumps(scan)))
