"""Trade workspace service: account detail, deterministic ticket checks, simulated orders.

Design rules honoured here:
  * READ-ONLY against Schwab. No order is ever sent to the broker. The live
    path is explicitly disabled and labelled.
  * Simulated orders are APPLICATION-LEVEL and clearly marked. They do not
    pretend to be the repository's EX-gate approval, so the repo's
    ``validate_execution_eligibility`` result is *reported*, never forged.
  * QX setup states and broker/order states stay in separate namespaces.
  * A ticket-hash intent ledger blocks duplicate submissions from double
    clicks, retries, reconnects or refreshes, because no broker idempotency
    key is assumed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import threading
import uuid
from typing import Any

from qx.core.atomic_store import (
    STATUS_CORRUPT,
    STATUS_OK,
    atomic_write_json,
    quarantine,
    read_json,
)
from qx.reporting.schwab_activity import SchwabActivityReader

WORKSPACE_ROOT = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"
ORDER_STORE = os.path.join(WORKSPACE_ROOT, "data", "qx_orders", "simulated_orders.json")

ORDER_TYPES = ("MARKET", "LIMIT")
DURATIONS = ("DAY", "GTC")
SIDES = ("BUY", "SHORT")

# Deterministic app-level risk limits (not broker rules).
MAX_NOTIONAL_PCT_OF_EQUITY = 35.0     # one position may not exceed 35% of equity
MAX_LIMIT_DEVIATION_PCT = 20.0        # limit price sanity vs latest quote
_LOCK = threading.Lock()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _finite(value: Any) -> float | None:
    """Parse a number, returning None for anything that is not a real finite value.

    Reviewer F16: ``_number`` passes NaN and infinity straight through, so a ticket
    with ``limit_price = -1`` produced an estimated cost of -1.00, and ``inf`` sailed
    past the presence check. Risk checks must operate on real numbers only.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _is_whole_number(value: float, tolerance: float = 1e-9) -> bool:
    return abs(value - round(value)) <= tolerance


def _reader() -> SchwabActivityReader:
    from qx.brokers.schwab.auth import SchwabTokenManager
    from qx.brokers.schwab.client import SchwabApiClient
    from qx.config.settings import get_settings

    settings = get_settings()
    client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
    return SchwabActivityReader(client)


# --------------------------------------------------------------------------- #
# Accounts / positions / open orders (read-only)
# --------------------------------------------------------------------------- #

def list_accounts() -> dict[str, Any]:
    reader = _reader()
    refs = reader.accounts()
    warnings = []
    if len(refs) > 1:
        warnings.append(
            f"{len(refs)} accounts are readable and are handled separately — balances, "
            "positions and orders are never combined across accounts."
        )
    return {
        "accounts": [
            {"account_number": r.account_number, "masked": r.masked,
             "type": r.account_type, "label": (r.account_type or "Account").title()}
            for r in refs
        ],
        "warnings": warnings,
    }


def account_detail(account_number: str) -> dict[str, Any]:
    reader = _reader()
    ref = next((r for r in reader.accounts() if r.account_number == account_number), None)
    if ref is None:
        raise KeyError(f"account {account_number!r} is not readable by this token")
    snapshot = reader.snapshot(account_number)
    balances = snapshot.get("balances") or {}
    equity = _number(balances.get("liquidationValue") or balances.get("equity"))

    positions = []
    for raw in snapshot.get("positions") or []:
        instrument = raw.get("instrument") if isinstance(raw.get("instrument"), dict) else {}
        quantity = _number(raw.get("longQuantity")) - _number(raw.get("shortQuantity"))
        positions.append({
            "symbol": str(instrument.get("symbol") or "").strip().upper(),
            "asset_type": str(instrument.get("assetType") or "EQUITY").upper(),
            "quantity": quantity,
            "average_price": _number(raw.get("averagePrice")),
            "market_value": _number(raw.get("marketValue")),
            "day_pnl": _number(raw.get("currentDayProfitLoss")),
        })
    positions.sort(key=lambda p: abs(p["market_value"]), reverse=True)

    recent_orders = []
    try:
        orders = reader.orders(ref.hash_value, days=60)
        for raw in orders.transactions:
            legs = raw.get("orderLegCollection") or []
            symbol = ""
            if legs and isinstance(legs[0], dict):
                symbol = str((legs[0].get("instrument") or {}).get("symbol") or "")
            recent_orders.append({
                "order_id": raw.get("orderId"),
                "status": raw.get("status"),
                "order_type": raw.get("orderType"),
                "duration": raw.get("duration"),
                "quantity": _number(raw.get("quantity")),
                "filled_quantity": _number(raw.get("filledQuantity")),
                "price": raw.get("price"),
                "stop_price": raw.get("stopPrice"),
                "entered_time": raw.get("enteredTime"),
                "symbol": symbol,
                "instruction": str((legs[0].get("instruction") if legs else "") or ""),
            })
        recent_orders.sort(key=lambda o: str(o.get("entered_time") or ""), reverse=True)
    except Exception:  # noqa: BLE001 - order history is best-effort
        orders = None

    # "Open" means a non-terminal status, matching the repo's own definition.
    terminal = {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "REPLACED"}
    open_orders = [o for o in recent_orders if str(o.get("status") or "").upper() not in terminal]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "account": {"account_number": ref.account_number, "masked": ref.masked,
                    "type": ref.account_type, "label": (ref.account_type or "Account").title()},
        "balances": {
            "equity": round(equity, 2),
            "cash": round(_number(balances.get("cashBalance")), 2),
            "buying_power": round(_number(balances.get("buyingPower") or balances.get("availableFunds")), 2),
            "long_market_value": round(_number(balances.get("longMarketValue")), 2),
            "short_market_value": round(_number(balances.get("shortMarketValue")), 2),
        },
        "positions": positions,
        "open_orders": open_orders,
        "recent_orders_count": len(recent_orders),
        "open_orders_error": None if orders is not None else "order history unavailable",
    }


# --------------------------------------------------------------------------- #
# Ticket validation (deterministic app-level risk checks)
# --------------------------------------------------------------------------- #

def _quote(symbol: str) -> dict[str, Any] | None:
    from qx.scanner.engine import MarketData

    quote, source = MarketData().quote(symbol)
    if quote:
        quote = {**quote, "source": source}
    return quote


def _ticket_hash(ticket: dict[str, Any]) -> str:
    material = "|".join(str(ticket.get(key, "")) for key in
                        ("account", "symbol", "side", "quantity", "order_type", "limit_price", "duration"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def validate_ticket(ticket: dict[str, Any], *, account_number: str) -> dict[str, Any]:
    """Run deterministic checks. Returns the exact proposed order plus verdict."""
    symbol = str(ticket.get("symbol") or "").strip().upper()
    side = str(ticket.get("side") or "").strip().upper()
    order_type = str(ticket.get("order_type") or "LIMIT").strip().upper()
    duration = str(ticket.get("duration") or "DAY").strip().upper()
    # F16: parse through _finite so NaN/inf/blank never masquerade as real values.
    quantity_value = _finite(ticket.get("quantity"))
    quantity = quantity_value if quantity_value is not None else 0.0
    limit_value = _finite(ticket.get("limit_price"))
    limit_price = limit_value
    setup = ticket.get("setup") or {}

    quote = _quote(symbol) if symbol else None
    reference = _finite((quote or {}).get("last")) or _finite(setup.get("entry")) or 0.0

    detail = account_detail(account_number) if account_number else {"balances": {}, "positions": []}
    balances = detail.get("balances") or {}
    equity_value = _finite(balances.get("equity"))
    buying_power_value = _finite(balances.get("buying_power"))
    equity = equity_value if equity_value is not None else 0.0
    held = next((p for p in detail.get("positions") or [] if p["symbol"] == symbol), None)

    # A negative or non-finite price must never produce a negative cost.
    price_for_cost = limit_price if (order_type == "LIMIT" and limit_price) else reference
    if price_for_cost is None or not math.isfinite(price_for_cost) or price_for_cost <= 0:
        price_for_cost = 0.0
    estimated_cost = round(abs(quantity) * price_for_cost, 2)
    notional_pct = (estimated_cost / equity * 100.0) if equity > 0 else None

    invalidation = setup.get("invalidation")
    risk_to_invalidation = (
        round(abs(price_for_cost - _number(invalidation)) * abs(quantity), 2)
        if price_for_cost and invalidation else None
    )

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail_text: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail_text})

    check("symbol", bool(symbol), f"symbol={symbol or '(missing)'}")
    check("side", side in SIDES, f"side={side or '(missing)'} (allowed: {', '.join(SIDES)})")
    # F16: quantity must be a real, positive, WHOLE number. NaN/inf are rejected
    # because _finite returns None for them.
    if quantity_value is None:
        check("quantity", False, f"quantity={ticket.get('quantity')!r} is not a finite number")
    elif quantity_value <= 0:
        check("quantity", False, f"quantity={quantity_value:g} (must be > 0)")
    elif not _is_whole_number(quantity_value):
        check("quantity", False,
              f"quantity={quantity_value:g} (must be a whole number of shares/contracts)")
    else:
        check("quantity", True, f"quantity={quantity_value:g}")
    check("order_type", order_type in ORDER_TYPES, f"type={order_type} (allowed: {', '.join(ORDER_TYPES)})")
    check("duration", duration in DURATIONS, f"duration={duration} (allowed: {', '.join(DURATIONS)})")
    # F16: a LIMIT price must be present AND a positive finite number. Previously any
    # truthy value passed, so -1 and inf were accepted.
    if order_type != "LIMIT":
        check("limit_price", True, "not a LIMIT order")
    elif limit_value is None:
        check("limit_price", False,
              f"LIMIT requires a positive finite limit price (got {ticket.get('limit_price')!r})")
    elif limit_value <= 0:
        check("limit_price", False, f"limit price {limit_value:g} must be > 0")
    else:
        check("limit_price", True, f"limit price {limit_value:.4f}")
    if order_type == "LIMIT" and limit_value and limit_value > 0 and reference:
        deviation = abs(limit_value - reference) / reference * 100.0
        check("limit_sanity", deviation <= MAX_LIMIT_DEVIATION_PCT,
              f"limit {limit_value:.2f} vs last {reference:.2f} = {deviation:.2f}% "
              f"(max {MAX_LIMIT_DEVIATION_PCT:.0f}%)")
    check("market_data", bool(reference), "reference price available" if reference else "no quote or setup entry price")
    check("data_freshness", str((quote or {}).get("source") or "unavailable") == "schwab",
          f"quote source={((quote or {}).get('source') or 'unavailable')} (live Schwab required)")
    check("buys_need_buying_power",
          side != "BUY" or (buying_power_value is not None
                            and estimated_cost <= buying_power_value),
          f"est. cost {estimated_cost:,.2f} vs buying power "
          f"{buying_power_value if buying_power_value is not None else 'unavailable'}")
    # F16: missing equity is UNKNOWN, not "acceptable". The old expression
    # (`notional_pct is None or ...`) passed the check whenever equity was absent.
    if notional_pct is None:
        check("concentration", False,
              f"account equity unavailable (equity={balances.get('equity')!r}) — "
              "concentration cannot be verified")
    else:
        check("concentration", notional_pct <= MAX_NOTIONAL_PCT_OF_EQUITY,
              f"notional {notional_pct:.1f}% of equity (max {MAX_NOTIONAL_PCT_OF_EQUITY:.0f}%)")
    if setup and setup.get("side"):
        direction = {"BUY": "LONG", "SHORT": "SHORT"}.get(side, "")
        check("setup_qualified", str(setup.get("side")).upper() == direction,
              f"setup side={setup.get('side')} vs ticket side={side} (direction {direction or 'n/a'})")
    else:
        check("setup_qualified", True, "no setup attached (free-form ticket)")

    # Report (never forge) the repository's own execution-eligibility gate.
    ex_gate = {"allowed": None, "reason": "not evaluated"}
    try:
        from qx.execution.order_router import OrderRouter

        allowed, reason = OrderRouter().validate_execution_eligibility({
            "publication_state": setup.get("publication_state"),
            "executable": setup.get("executable"),
        })
        ex_gate = {"allowed": bool(allowed), "reason": reason or "VERIFIED and executable"}
    except Exception as exc:  # noqa: BLE001
        ex_gate = {"allowed": None, "reason": f"gate unavailable: {type(exc).__name__}"}

    passed = all(item["passed"] for item in checks)
    proposed = {
        "account": account_number,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "limit_price": limit_price,
        "duration": duration,
        "estimated_cost": estimated_cost,
        "reference_price": reference,
    }
    return {
        "verdict": "READY_FOR_CONFIRMATION" if passed else "BLOCKED",
        "checks": checks,
        "failed": [c["name"] for c in checks if not c["passed"]],
        "proposed_order": proposed,
        "ticket_hash": _ticket_hash(proposed),
        "quote": quote,
        "estimated_cost": estimated_cost,
        "notional_pct_of_equity": round(notional_pct, 2) if notional_pct is not None else None,
        "risk_to_invalidation": risk_to_invalidation,
        "existing_position": held,
        "ex_gate": ex_gate,
        "cost_method": "app-level deterministic checks; repo EX-gate reported, not forged",
    }


# --------------------------------------------------------------------------- #
# Simulated order book (application-level, explicitly labelled)
# --------------------------------------------------------------------------- #

def _load_orders_result() -> Any:
    """Read the simulated order ledger WITH its status (F19).

    The old reader turned any error into an empty list, so a CORRUPT ledger looked
    exactly like "no orders yet" — which silently discarded the duplicate-suppression
    history the intent ledger exists to provide.
    """
    return read_json(ORDER_STORE)


def _load_orders() -> list[dict[str, Any]]:
    """Back-compatible accessor: the orders, or [] when missing OR corrupt."""
    result = _load_orders_result()
    return result.payload if result.ok and isinstance(result.payload, list) else []


def _save_orders(orders: list[dict[str, Any]]) -> None:
    """Atomic write (F19): a crash cannot truncate the ledger."""
    atomic_write_json(ORDER_STORE, orders)


def list_orders(limit: int = 100) -> dict[str, Any]:
    with _LOCK:
        result = _load_orders_result()
    orders = result.payload if result.ok and isinstance(result.payload, list) else []
    orders.sort(key=lambda o: str(o.get("created_at") or ""), reverse=True)
    return {
        "mode": "SIMULATED", "app_level": True,
        "orders": orders[:limit], "count": len(orders),
        # F19: the ledger's own condition, so a damaged file is visible rather than
        # presenting as "no orders".
        "store_status": result.status,
        "store_error": result.error,
    }


def submit_simulated(ticket: dict[str, Any], *, account_number: str, confirm: bool,
                     intent_id: str | None = None) -> dict[str, Any]:
    """Record a SIMULATED order. Never contacts the broker.

    Duplicate defence (reviewer F15): suppression keys on the ticket's REQUEST
    identity and survives TERMINAL status. A MARKET order fills immediately, so a
    status-based guard let every retry through. A deliberate repeat trade must pass
    a NEW ``intent_id``; an identical retry reusing the previous one is refused.
    """
    if confirm is not True:
        return {"ok": False, "error": "explicit confirmation required (confirm: true)"}

    validation = validate_ticket(ticket, account_number=account_number)
    if validation["verdict"] != "READY_FOR_CONFIRMATION":
        return {"ok": False, "error": "local validation blocked submission",
                "validation": validation}

    with _LOCK:
        read_result = _load_orders_result()
        # F19 SAFETY: if the ledger cannot be read, we cannot know whether this ticket
        # was already submitted. Proceeding would either duplicate an order or write
        # over the intent history. Refuse, and quarantine the damaged file so the
        # evidence survives for inspection instead of being overwritten.
        if read_result.status == STATUS_CORRUPT:
            quarantined = quarantine(ORDER_STORE)
            return {"ok": False,
                    "error": "the simulated order ledger is unreadable, so duplicate "
                             "suppression cannot be verified — submission refused",
                    "store_status": read_result.status,
                    "store_error": read_result.error,
                    "quarantined_to": quarantined}
        orders = read_result.payload if read_result.ok and isinstance(read_result.payload, list) else []
        ticket_hash = validation["ticket_hash"]
        request_id = intent_id or validation["ticket_hash"]

        # Any prior record with this request identity blocks a repeat — regardless
        # of status, because a filled or cancelled order is still the SAME request.
        prior = next((o for o in orders if o.get("request_id") == request_id), None)
        if prior is not None:
            return {"ok": False, "error": "duplicate submission blocked by intent ledger",
                    "duplicate_of": prior.get("intent_id"), "ticket_hash": ticket_hash,
                    "request_id": request_id, "prior_status": prior.get("status")}

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        proposed = validation["proposed_order"]
        order = {
            "intent_id": f"SIM-{uuid.uuid4().hex[:10].upper()}",
            "request_id": request_id,
            "ticket_hash": ticket_hash,
            "account": account_number,
            "symbol": proposed["symbol"],
            "side": proposed["side"],
            "quantity": proposed["quantity"],
            "order_type": proposed["order_type"],
            "limit_price": proposed["limit_price"],
            "duration": proposed["duration"],
            "estimated_cost": proposed["estimated_cost"],
            "status": "CONFIRMED_LOCAL",
            "mode": "SIMULATED",
            "app_level": True,
            "broker_order_id": None,
            "fills": [],
            "filled_quantity": 0.0,
            "reject_reason": None,
            "created_at": now,
            "updated_at": now,
            "setup_id": (ticket.get("setup") or {}).get("setup_id"),
            "setup_version": (ticket.get("setup") or {}).get("setup_version"),
            "note": "Application-level simulated order. No broker order was placed.",
        }
        # Simulate an immediate fill for MARKET orders at the reference price,
        # mirroring the repo's in-memory paper router behaviour.
        if order["order_type"] == "MARKET" and validation["proposed_order"]["reference_price"]:
            price = _number(validation["proposed_order"]["reference_price"])
            order["status"] = "FILLED"
            order["filled_quantity"] = order["quantity"]
            order["fills"] = [{"price": price, "quantity": order["quantity"], "at": now}]
            order["updated_at"] = now
        orders.append(order)
        _save_orders(orders)
    return {"ok": True, "order": order, "validation": validation,
            "note": "SIMULATED order recorded. Live submission is gated and disabled."}


def cancel_order(intent_id: str) -> dict[str, Any]:
    with _LOCK:
        orders = _load_orders()
        order = next((o for o in orders if o.get("intent_id") == intent_id), None)
        if order is None:
            return {"ok": False, "error": f"unknown order {intent_id}"}
        if order.get("status") == "FILLED":
            return {"ok": False, "error": "cannot cancel a FILLED order", "order": order}
        order["status"] = "CANCELED"
        order["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _save_orders(orders)
    return {"ok": True, "order": order}
