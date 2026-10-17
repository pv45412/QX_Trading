"""QX application server: Scanner + Trade Workspace + Reports (read-only + simulated).

Run:  python -m qx.app.server [--port 8790]

Safety posture:
  * Every Schwab call is a GET. No order is ever sent to the broker.
  * Live submission is disabled in code and labelled in the UI.
  * Simulated orders are application-level and clearly marked.
  * The browser never receives a token, secret, or account hash.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):  # direct execution
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from qx.app import trade, ui

# The reporting engine owns the account/P&L contract; reuse it rather than
# duplicating. (Private helpers are imported deliberately to keep one owner.)
from qx.reporting.server import _account_index, _report

MAX_BODY = 1_000_000


def _chart(symbol: str, timeframe: str) -> dict:
    from qx.scanner.engine import MarketData

    interval = "15m" if str(timeframe).lower() in {"15m", "15", "intraday"} else "1d"
    bars, source = MarketData().bars(symbol, interval=interval)
    if not bars:
        return {"symbol": symbol.upper(), "closes": [], "source": source, "error": "no bars"}
    window = bars[-120:]
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "source": source,
        "bars": len(window),
        "closes": [round(bar["close"], 4) for bar in window],
        "highs": [round(bar["high"], 4) for bar in window],
        "lows": [round(bar["low"], 4) for bar in window],
    }


def _scan(query: dict) -> dict:
    from qx.scanner.engine import scan_universe

    raw = (query.get("symbols") or [""])[0].strip()
    symbols = [s.strip().upper() for s in raw.replace(",", " ").split() if s.strip()] or None
    timeframe = (query.get("timeframe") or ["1d"])[0]
    return scan_universe(symbols, timeframe=timeframe)


def _outcome(body: dict, symbol: str):
    """Closed trades for one symbol, only when the caller opts in."""
    if not body.get("include_outcome"):
        return None
    account = str(body.get("account") or "").strip()
    if not account or not symbol:
        return None
    try:
        report = _report(account, 400, False)
        return [t for t in (report.get("closed_trades") or [])
                if str(t.get("symbol") or "").upper() == symbol.upper()]
    except Exception:  # noqa: BLE001 - outcome is optional context
        return None


def _fresh_row(setup: dict):
    """Re-scan one symbol so a plan update can be drafted from current data."""
    from qx.scanner.engine import scan_universe

    symbol = str(setup.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    try:
        scan = scan_universe([symbol], timeframe=str(setup.get("timeframe") or "1d"))
        rows = scan.get("results") or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        return None


def _notes(body: dict) -> dict:
    from qx.notes import engine as notes_engine

    setup = body.get("setup") or {}
    symbol = str(setup.get("symbol") or "").strip().upper()
    notes = notes_engine.build_notes(
        setup,
        context=body.get("context"),
        sector=body.get("sector"),
        peers=body.get("peers"),
        prior=notes_engine.prior_for(setup),
        closed_trades=_outcome(body, symbol),
    )
    return {"ok": True, "notes": notes, "staleness": notes_engine.record(setup, notes)}


def _notes_command(body: dict, command: str) -> dict:
    from qx.notes import engine as notes_engine

    setup = body.get("setup") or {}
    symbol = str(setup.get("symbol") or "").strip().upper()
    fresh = _fresh_row(setup) if command == "update-plan" else None
    return notes_engine.run_command(
        command,
        setup,
        context=body.get("context"),
        sector=body.get("sector"),
        peers=body.get("peers"),
        fresh=fresh,
        ticket_validation=body.get("ticket_validation"),
        closed_trades=_outcome(body, symbol),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "QXApp/1.0"

    def log_message(self, fmt, *args):  # noqa: A003 - no query strings in logs
        return

    def handle_one_request(self) -> None:
        """Swallow client disconnects instead of printing a stack trace."""
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    # -- transport helpers -------------------------------------------------
    def _send(self, code: int, content_type: str, body: bytes) -> None:
        try:
            self.send_response(code)
            self.send_header("content-type", content_type)
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # The browser navigated away or cancelled. Not an application error.
            self.close_connection = True

    def _html(self, body: str) -> None:
        self._send(200, "text/html; charset=utf-8", body.encode("utf-8"))

    def _json(self, code: int, payload) -> None:
        self._send(code, "application/json", json.dumps(payload, default=str).encode("utf-8"))

    def _body(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    # -- routes ------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path
        try:
            if path in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("location", "/scanner")
                self.end_headers()
                return
            if path == "/scanner":
                # Discover = the scanner plus the Sector/Industry Explorer drill-down.
                body = ui.SCANNER_BODY.replace(
                    '<h1 style="font-size:17px;margin:0">Scanner',
                    '<h1 style="font-size:17px;margin:0">Discover &middot; scanner', 1)
                script_at = body.rfind("<script>")
                body = body[:script_at] + ui.EXPLORER_SECTION + body[script_at:]
                close_at = body.rfind("</script>")
                body = body[:close_at] + ui.EXPLORER_JS + "\nloadCatalog();\n" + body[close_at:]
                return self._html(ui.shell("QX Discover", body))
            if path == "/trade":
                return self._html(ui.shell("QX Trade Workspace", ui.TRADE_BODY))
            if path == "/context":
                return self._html(ui.shell("QX Context", ui.CONTEXT_BODY))
            if path == "/settings":
                return self._html(ui.shell("QX Settings", ui.SETTINGS_BODY))
            if path == "/reports":
                return self._html(ui.reports_page())
            if path == "/ideas":
                return self._html(ui.shell("QX Trade Ideas", ui.IDEAS_BODY))

            if path == "/api/ideas":
                # Import the MODULE explicitly: `qx.explorer.ideas` is shadowed by the
                # `ideas` function re-exported from the package __init__.
                from qx.explorer import ideas as ideas_module

                view = (query.get("view") or ["ready_now"])[0].strip()
                sort = (query.get("sort") or ["entry_readiness"])[0].strip()
                sector = (query.get("sector") or [""])[0].strip() or None
                limit = max(1, min(int((query.get("limit") or ["200"])[0]), 500))
                return self._json(200, ideas_module.ideas(view=view, sort=sort,
                                                          sector=sector, limit=limit))
            if path == "/api/ideas/status":
                import qx.explorer.ideas as ideas_module

                return self._json(200, ideas_module.status())
            if path == "/api/ideas/why":
                import qx.explorer.ideas as ideas_module

                symbol = (query.get("symbol") or [""])[0].strip()
                view = (query.get("view") or ["ready_now"])[0].strip()
                sort = (query.get("sort") or ["entry_readiness"])[0].strip()
                if not symbol:
                    return self._json(400, {"error": "symbol is required"})
                return self._json(200, ideas_module.why_ranked(symbol, view=view, sort=sort))
            if path == "/api/candidates":
                # Authoritative candidate contract (reviewer F04): the browser must
                # never derive an execution label, so it reads this instead.
                from qx.app import contracts

                symbol = (query.get("symbol") or [""])[0].strip().upper()
                if not symbol:
                    return self._json(400, {"error": "symbol is required"})
                universe = (query.get("universe") or ["ETF_REPORTED_TOP_HOLDINGS"])[0].strip()
                try:
                    from qx.explorer import explore

                    data = explore(symbol, universe, view="all", limit=300)
                    candidates = [contracts.from_scan_row(r, rule_version=data["rules"]["momo_trend"])
                                  for r in data["rows"]]
                    return self._json(200, {
                        "contract_version": contracts.CONTRACT_VERSION,
                        "symbol": symbol, "universe": universe,
                        "execution_policy": contracts.execution_state(
                            publication_state="RESEARCH_ONLY", executable=False),
                        "candidates": candidates,
                    })
                except Exception as exc:  # noqa: BLE001
                    return self._json(500, {"error": f"{type(exc).__name__}: {exc}"[:300]})
            if path == "/api/explorer/catalog":
                from qx.explorer import catalog

                return self._json(200, catalog())
            if path == "/api/explorer/sector":
                from qx.explorer import explore

                symbol = (query.get("symbol") or ["XLK"])[0].strip().upper() or "XLK"
                universe = (query.get("universe") or ["ETF_REPORTED_TOP_HOLDINGS"])[0].strip()
                view = (query.get("view") or ["aligned_up"])[0].strip()
                timeframe = (query.get("timeframe") or ["1d"])[0].strip()
                limit = max(1, min(int((query.get("limit") or ["120"])[0]), 300))
                try:
                    return self._json(200, explore(symbol, universe, timeframe=timeframe,
                                                   view=view, limit=limit))
                except ValueError as exc:
                    # A caller error (e.g. an unsupported timeframe) is 400, not 500.
                    return self._json(400, {"error": str(exc)[:300]})
                except Exception as exc:  # noqa: BLE001
                    return self._json(500, {"error": f"{type(exc).__name__}: {exc}"[:300]})
            if path == "/api/explorer/notes":
                from qx.app import explorer_notes

                return self._json(200, explorer_notes.build(body))
            if path == "/api/context/levels":
                from qx.app import context as ctx_service

                symbol = (query.get("symbol") or ["SPY"])[0].strip().upper() or "SPY"
                return self._json(200, ctx_service.levels(symbol))
            if path == "/api/context/futures":
                from qx.app import context as ctx_service

                return self._json(200, ctx_service.futures())
            if path == "/api/context/gamma":
                from qx.app import context as ctx_service

                symbol = (query.get("symbol") or ["SPY"])[0].strip().upper() or "SPY"
                return self._json(200, ctx_service.gamma(symbol))
            if path == "/api/settings/schwab":
                from qx.app import settings_service

                return self._json(200, settings_service.status())
            if path == "/api/settings/schwab/accounts":
                from qx.app import settings_service

                return self._json(200, settings_service.accounts_health())

            if path == "/api/health":
                return self._json(200, {"ok": True, "app": "qx",
                                        "pages": ["/scanner", "/trade", "/context", "/reports", "/settings"]})
            if path == "/api/context":
                from qx.scanner.engine import market_context

                return self._json(200, market_context())
            if path == "/api/sectors":
                from qx.scanner.engine import sector_rankings

                return self._json(200, sector_rankings())
            if path == "/api/scan":
                return self._json(200, _scan(query))
            if path == "/api/chart":
                symbol = (query.get("symbol") or [""])[0].strip()
                if not symbol:
                    return self._json(400, {"error": "symbol is required"})
                return self._json(200, _chart(symbol, (query.get("timeframe") or ["1d"])[0]))

            if path == "/api/trade/accounts":
                return self._json(200, trade.list_accounts())
            if path == "/api/trade/account":
                account = (query.get("account") or [""])[0].strip()
                if not account:
                    return self._json(400, {"error": "account is required"})
                return self._json(200, trade.account_detail(account))
            if path == "/api/trade/orders":
                return self._json(200, trade.list_orders())

            # Reports page contract (owned by qx.reporting).
            if path == "/api/accounts":
                accounts, warnings = _account_index()
                return self._json(200, {"accounts": accounts, "warnings": warnings})
            if path == "/api/report":
                account = (query.get("account") or [""])[0].strip()
                days = max(30, min(int((query.get("days") or ["400"])[0]), 400))
                nocache = (query.get("nocache") or ["0"])[0] == "1"
                if not account:
                    return self._json(400, {"error": "account is required"})
                return self._json(200, _report(account, days, nocache))

            return self._json(404, {"error": "not found"})
        except KeyError as exc:
            return self._json(404, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"[:500]})

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/trade/validate":
                ticket = body.get("ticket") or body
                account = str(body.get("account") or ticket.get("account") or "").strip()
                if not account:
                    return self._json(400, {"error": "account is required"})
                return self._json(200, trade.validate_ticket(ticket, account_number=account))

            if path == "/api/trade/orders":
                ticket = dict(body.get("ticket") or {})
                setup = body.get("setup")
                if setup:
                    ticket["setup"] = setup
                account = str(body.get("account") or ticket.get("account") or "").strip()
                if not account:
                    return self._json(400, {"error": "account is required"})
                result = trade.submit_simulated(ticket, account_number=account,
                                                confirm=body.get("confirm") is True)
                return self._json(200 if result.get("ok") else 400, result)

            if path == "/api/trade/orders/cancel":
                intent_id = str(body.get("intent_id") or "").strip()
                if not intent_id:
                    return self._json(400, {"error": "intent_id is required"})
                result = trade.cancel_order(intent_id)
                return self._json(200 if result.get("ok") else 400, result)

            if path == "/api/notes":
                return self._json(200, _notes(body))
            if path == "/api/notes/command":
                return self._json(200, _notes_command(body, str(body.get("command") or "").strip()))
            if path == "/api/ideas/build":
                import qx.explorer.ideas as ideas_module

                return self._json(200, ideas_module.build_async(force=body.get("force") is True))
            if path == "/api/ideas/query":
                import qx.explorer.ideas as ideas_module

                return self._json(200, ideas_module.ideas(
                    view=str(body.get("view") or "ready_now"),
                    sort=str(body.get("sort") or "entry_readiness"),
                    sector=(str(body["sector"]).upper() if body.get("sector") else None),
                    limit=int(body.get("limit") or 200)))
            if path == "/api/explorer/notes":
                from qx.app import explorer_notes

                return self._json(200, explorer_notes.build(body))

            if path == "/api/settings/schwab/authorize":
                # Explicit user action: exchange the pasted Schwab callback code and
                # persist the token server-side. This obtains CREDENTIALS only — it
                # never submits an order, so the execution gate is untouched.
                from qx.app import settings_service

                result = settings_service.authorize(
                    str(body.get("callback") or body.get("code") or ""))
                return self._json(200 if result.get("ok") else 400, result)

            return self._json(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"[:500]})


def main() -> int:
    parser = argparse.ArgumentParser(description="QX trading workspace application")
    parser.add_argument("--host", default=os.environ.get("QX_APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("QX_APP_PORT", "8790")))
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"QX workspace on http://{args.host}:{args.port}/  "
          f"(Discover / Trade Ideas / Trade Workspace / Context / Reports / Settings)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
