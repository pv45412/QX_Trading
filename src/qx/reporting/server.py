"""Read-only local HTTP server for the QX account / P&L report dashboard.

Run:  python -m qx.reporting.server [--port 8788] [--host 127.0.0.1]

Security posture:
  * Read-only. It only issues Schwab GET requests through the existing
    authenticated client; it never places, cancels or modifies an order.
  * The browser never receives an access token, a client secret, or the
    encrypted account hash. The browser asks for an account *number*; the
    server resolves the hash internally and returns only masked identifiers.
  * Binds to loopback only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):  # direct `python server.py` execution
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from qx.reporting.dashboard import DASHBOARD_HTML
from qx.reporting.pnl_engine import build_report

_CACHE: dict[tuple[str, int], tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 60
_LOCK = threading.Lock()


def _reader():
    from qx.brokers.schwab.auth import SchwabTokenManager
    from qx.brokers.schwab.client import SchwabApiClient
    from qx.config.settings import get_settings
    from qx.reporting.schwab_activity import SchwabActivityReader

    settings = get_settings()
    client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
    return SchwabActivityReader(client)


def _account_index() -> tuple[list[dict], list[str]]:
    """Accounts plus non-fatal warnings (e.g. multi-account note)."""
    reader = _reader()
    refs = reader.accounts()
    warnings: list[str] = []
    if len(refs) > 1:
        warnings.append(
            f"{len(refs)} accounts are readable and are reported separately by design — "
            "balances, lots and P&L are never combined or netted across accounts. "
            "Note: the legacy portfolio snapshot path refuses multi-account logins."
        )
    return (
        [
            {
                "account_number": r.account_number,
                "masked": r.masked,
                "type": r.account_type,
                "label": (r.account_type or "Account").title(),
            }
            for r in refs
        ],
        warnings,
    )


def _report(account_number: str, days: int, nocache: bool) -> dict:
    key = (account_number, days)
    if not nocache:
        with _LOCK:
            hit = _CACHE.get(key)
        if hit and (time.time() - hit[0]) < _CACHE_TTL_SECONDS:
            return hit[1]

    reader = _reader()
    refs = {r.account_number: r for r in reader.accounts()}
    ref = refs.get(account_number)
    if ref is None:
        raise KeyError(f"account {account_number!r} is not readable by this token")

    activity = reader.transactions(ref.hash_value, days=days)
    snapshot = reader.snapshot(ref.account_number)
    report = build_report(
        activity,
        snapshot,
        account={"account_number": ref.account_number, "masked": ref.masked,
                 "type": ref.account_type, "label": (ref.account_type or "Account").title()},
        days=days,
    )

    with _LOCK:
        _CACHE[key] = (time.time(), report)
    return report


class Handler(BaseHTTPRequestHandler):
    server_version = "QXReport/1.0"

    def log_message(self, fmt, *args):  # noqa: A003 - quieter, no query strings in logs
        return

    def _send(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, "application/json", json.dumps(payload).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path in ("/", "/index.html"):
                return self._send(200, "text/html; charset=utf-8", DASHBOARD_HTML.encode("utf-8"))
            if parsed.path == "/api/accounts":
                accounts, warnings = _account_index()
                return self._json(200, {"accounts": accounts, "warnings": warnings})
            if parsed.path == "/api/report":
                account = (query.get("account") or [""])[0].strip()
                days = int((query.get("days") or ["400"])[0])
                days = max(30, min(days, 400))
                nocache = (query.get("nocache") or ["0"])[0] == "1"
                if not account:
                    return self._json(400, {"error": "account is required"})
                return self._json(200, _report(account, days, nocache))
            if parsed.path == "/health":
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "not found"})
        except KeyError as exc:
            return self._json(404, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - surface, never crash the thread
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"[:500]})


def main() -> int:
    parser = argparse.ArgumentParser(description="QX read-only account report server")
    parser.add_argument("--host", default=os.environ.get("QX_REPORT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("QX_REPORT_PORT", "8788")))
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"QX account reports (read-only) on http://{args.host}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
