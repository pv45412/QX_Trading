"""QX Platform Automated Pre-Flight & Regression Verification CLI Tool.

Run before making any view ready for the user:
    python -m qx.tools.run_preflight_checks
"""

import sys
import json
import urllib.request
import urllib.error
from typing import Any

BACKEND_URL = "http://127.0.0.1:8510"
FRONTEND_URL = "http://127.0.0.1:5174"


def check_url(url: str, is_json: bool = True) -> tuple[bool, Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QX-PreFlight-Checker/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            content = resp.read().decode("utf-8")
            if is_json:
                return True, json.loads(content)
            return True, len(content)
    except Exception as exc:
        return False, str(exc)


def run_preflight() -> bool:
    print("=========================================================")
    print(" QX PLATFORM AUTOMATED PRE-FLIGHT REGRESSION CHECKER")
    print("=========================================================")

    all_passed = True
    checks = [
        ("Backend Health Check", f"{BACKEND_URL}/api/ai/status", True),
        ("XLK Market Snapshot API", f"{BACKEND_URL}/api/market/XLK/snapshot", True),
        ("VST Market Snapshot API", f"{BACKEND_URL}/api/market/VST/snapshot", True),
        ("Sector Rotation Analytics API", f"{BACKEND_URL}/api/rotation/analytics", True),
        ("Telemetry Signals Log API", f"{BACKEND_URL}/api/telemetry/signals", True),
        ("Options Scanner Ideas Hub API", f"{BACKEND_URL}/api/options-scanner/ideas", True),
        ("Day Trader Watchlist API", f"{BACKEND_URL}/api/terminal/watchlist", True),
        ("Day Trader Detail XLK API", f"{BACKEND_URL}/api/terminal/detail/XLK", True),
        ("SPX Command Dashboard API", f"{BACKEND_URL}/api/spx-dashboard", True),
        ("SPX Option Calendars API", f"{BACKEND_URL}/api/spx-calendars", True),
        ("Strategy Workspaces API", f"{BACKEND_URL}/api/strategies/workspace/spx-calendar", True),
        ("S&P 500 Market Movers API", f"{BACKEND_URL}/api/movers/sp500", True),
        ("React Frontend Server Check", f"{FRONTEND_URL}/", False),
    ]

    for name, url, is_json in checks:
        ok, res = check_url(url, is_json=is_json)
        if ok:
            status_str = "PASS"
            if is_json and isinstance(res, dict):
                extra = f" (status: {res.get('status', 'OK')})"
            else:
                extra = ""
            print(f"  [PASS] {name:<32} -> {status_str}{extra}")
        else:
            all_passed = False
            print(f"  [FAIL] {name:<32} -> FAIL: {res}")

    print("---------------------------------------------------------")
    if all_passed:
        print(" [OK] PRE-FLIGHT VERIFICATION COMPLETE: ALL SYSTEMS READY FOR VIEWING!")
        print("=========================================================")
        return True
    else:
        print(" [!] PRE-FLIGHT VERIFICATION FAILED: DO NOT PRESENT TO USER YET.")
        print("=========================================================")
        return False


if __name__ == "__main__":
    success = run_preflight()
    sys.exit(0 if success else 1)
