"""Scratch audit: verify realized P&L math against raw Schwab legs."""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.brokers.schwab.auth import SchwabTokenManager
from qx.brokers.schwab.client import SchwabApiClient
from qx.config.settings import get_settings
from qx.reporting.pnl_engine import build_report, realized_pnl
from qx.reporting.schwab_activity import SchwabActivityReader

SEC = {"EQUITY", "OPTION", "FUTURE", "COLLECTIVE_INVESTMENT", "MUTUAL_FUND", "ETF", "BOND"}
settings = get_settings()
reader = SchwabActivityReader(
    SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
)

for account in ("84342410", "79425050"):
    ref = next(x for x in reader.accounts() if x.account_number == account)
    activity = reader.transactions(ref.hash_value, days=400)
    snapshot = reader.snapshot(account)
    report = build_report(activity, snapshot, account={"account_number": account, "masked": ref.masked}, days=400)
    print("=" * 78)
    print("ACCOUNT", ref.masked, ref.account_type, "| tx:", len(activity.transactions))
    print("  totals :", report["totals"])
    print("  perf   :", report["performance"])
    print("  by type:", [(x["label"], x["realized"], x["trades"]) for x in report["by_asset_type"]])

print("=" * 78)
print("RAW LEGS vs ENGINE (account 84342410, chronological)")
ref = next(x for x in reader.accounts() if x.account_number == "84342410")
activity = reader.transactions(ref.hash_value, days=400)
for row in sorted(activity.transactions, key=lambda z: str(z.get("time") or "")):
    if str(row.get("type")).upper() != "TRADE":
        continue
    for item in row.get("transferItems") or []:
        inst = item.get("instrument") or {}
        if str(inst.get("assetType") or "").upper() not in SEC:
            continue
        print(
            "  %s  %-22s amt=%8s cost=%12s eff=%s"
            % (
                str(row.get("time"))[:19],
                inst.get("symbol"),
                item.get("amount"),
                item.get("cost"),
                item.get("positionEffect"),
            )
        )
print()
print("ENGINE per-trade realized:")
for trade in realized_pnl(activity.transactions)["trades"]:
    print(
        "  %s %-20s qty=%-6s realized=%s"
        % (
            (trade["closed_at"] or "")[:19],
            trade["symbol"],
            trade["qty"],
            trade["realized"],
        )
    )
print()
print("Manual check: buy 50 @ cost -3835.5 then sell @ cost +4000 => realized +164.5")
