"""Scratch: $SPX failed again. Is my expiry fix incomplete?

Hypothesis: Schwab reports DTE 0 (not negative) for a SAME-DAY expiry even after the
session has closed, so an economically-expired 0DTE series still passes the DTE >= 0
filter and contributes zero open interest.
"""
import datetime as dt
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import context as C  # noqa: E402
from qx.app import timefmt as T  # noqa: E402

now = dt.datetime.now(dt.timezone.utc)
print(f"now: {T.stamp(now)}  session={T.market_session_state(now)['state']}")
print()

from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402
from qx.brokers.schwab.client import SchwabApiClient  # noqa: E402
from qx.config.settings import get_settings  # noqa: E402

settings = get_settings()
client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)

for symbol in ("$SPX", "SPY"):
    payload = client.get("/marketdata/v1/chains", params={
        "symbol": symbol, "contractType": "ALL", "strikeCount": 40,
        "includeUnderlyingQuote": "true", "strategy": "SINGLE"})
    calls = payload.get("callExpDateMap") or {}
    print(f"=== {symbol} — every expiry the chain returned ===")
    rows = []
    for key, strikes in calls.items():
        oi = 0.0
        n = 0
        for contracts in (strikes or {}).values():
            for contract in contracts or []:
                oi += contract.get("openInterest") or 0
                n += 1
        rows.append((key, n, oi))
    for key, n, oi in rows:
        print(f"    {key:<22} contracts={n:<5} total_OI={oi:,.0f}")
    print(f"    -> {len(rows)} expiries available")
    chosen, info = C.select_expiries(calls, 2)
    print(f"    app would choose : {chosen}")
    print(f"    dte_used         : {info['dte_used']}")
    print(f"    skipped (no OI)  : {info['no_open_interest_skipped']}")
    print()
