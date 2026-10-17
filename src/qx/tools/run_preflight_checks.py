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


def check_url(url: str, is_json: bool = True, method: str = "GET") -> tuple[bool, Any]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "QX-PreFlight-Checker/1.0"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
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

    canonical_checks = [("DAY", "5m"), ("SWING", "1h"), ("INVEST", "1d")]
    for horizon, timeframe in canonical_checks:
        ok, result = check_url(
            f"{BACKEND_URL}/api/v2/qx/evaluate/SPY?timeframe={timeframe}",
            method="POST",
        )
        bars = result.get("data_dependencies", {}).get("bars", {}) if ok else {}
        passed = bool(
            ok
            and bars.get("available") is True
            and bars.get("quality_status") in {"PASS", "PARTIAL"}
            and result.get("publication_state") != "BLOCKED"
        )
        if passed:
            print(
                f"  [PASS] Canonical {horizon:<22} -> PASS "
                f"(bars: {bars.get('data_as_of')})"
            )
        else:
            all_passed = False
            reason = bars.get("quality_reason_codes") or result
            print(f"  [FAIL] Canonical {horizon:<22} -> FAIL: {reason}")

    ok, research = check_url(f"{BACKEND_URL}/api/market/SPY/snapshot")
    research_passed = bool(
        ok
        and research.get("status") == "SOURCE_BACKED"
        and research.get("last_price") is not None
        and research.get("data_as_of")
    )
    if research_passed:
        print(
            "  [PASS] Research Daily Freshness         -> PASS "
            f"(bars: {research.get('data_as_of')})"
        )
    else:
        all_passed = False
        print(f"  [FAIL] Research Daily Freshness         -> FAIL: {research}")

    ok, portfolio = check_url(f"{BACKEND_URL}/api/v2/qx/portfolio")
    portfolio_passed = bool(
        ok
        and portfolio.get("status") in {"COMPLETE", "PARTIAL"}
        and portfolio.get("read_only") is True
        and isinstance(portfolio.get("positions"), list)
    )
    if portfolio_passed:
        print(
            "  [PASS] Read-Only Portfolio             -> PASS "
            f"(positions: {len(portfolio.get('positions', []))})"
        )
    else:
        all_passed = False
        print(f"  [FAIL] Read-Only Portfolio             -> FAIL: {portfolio}")

    ok, overview = check_url(f"{BACKEND_URL}/api/system/overview")
    memory = next(
        (item for item in overview.get("components", []) if item.get("name") == "process_memory"),
        {},
    ) if ok else {}
    memory_passed = bool(ok and memory.get("status") == "OK")
    if memory_passed:
        print(f"  [PASS] Process Memory Verification      -> PASS ({memory.get('detail')})")
    else:
        all_passed = False
        print(f"  [FAIL] Process Memory Verification      -> FAIL: {memory or overview}")

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
