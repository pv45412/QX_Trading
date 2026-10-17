"""Scratch: why does $SPX 502 while $NDX succeeds? Test payload size."""
import os
import sys
import time

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402
from qx.brokers.schwab.client import SchwabApiClient  # noqa: E402
from qx.config.settings import get_settings  # noqa: E402

settings = get_settings()
client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)

BASE = {"contractType": "ALL", "includeUnderlyingQuote": "true", "strategy": "SINGLE"}

print("=== vary strikeCount for $SPX (it has 602 contracts at count=5) ===")
for count in (1, 5, 10, 20, 40, 80):
    try:
        started = time.time()
        payload = client.get("/marketdata/v1/chains", params={**BASE, "symbol": "$SPX",
                                                             "strikeCount": count})
        n = payload.get("numberOfContracts") if isinstance(payload, dict) else None
        print(f"  strikeCount={count:<3} OK   contracts={n!s:<6} {time.time()-started:.1f}s")
    except Exception as exc:  # noqa: BLE001
        code = next((c for c in ("400", "502", "503", "504") if c in str(exc)), "ERR")
        print(f"  strikeCount={count:<3} {code:<4} {str(exc)[:60]}")

print("\n=== compare with $NDX at the same counts ===")
for count in (5, 80):
    try:
        payload = client.get("/marketdata/v1/chains", params={**BASE, "symbol": "$NDX",
                                                             "strikeCount": count})
        print(f"  strikeCount={count:<3} OK   contracts={payload.get('numberOfContracts')}")
    except Exception as exc:  # noqa: BLE001
        code = next((c for c in ("400", "502", "503", "504") if c in str(exc)), "ERR")
        print(f"  strikeCount={count:<3} {code:<4} {str(exc)[:60]}")

print("\n=== does adding an expiry window help $SPX? ===")
for params in ({"fromDate": "2026-10-09", "toDate": "2026-10-10"},
               {"expMonth": "ALL"},
               {"strikeCount": 5, "range": "ITM"}):
    merged = {**BASE, "symbol": "$SPX", **params}
    if "strikeCount" not in merged:
        merged["strikeCount"] = 10
    try:
        payload = client.get("/marketdata/v1/chains", params=merged)
        print(f"  {params} -> OK contracts={payload.get('numberOfContracts')}")
    except Exception as exc:  # noqa: BLE001
        code = next((c for c in ("400", "502", "503", "504") if c in str(exc)), "ERR")
        print(f"  {params} -> {code} {str(exc)[:50]}")
