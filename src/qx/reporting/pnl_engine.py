"""Deterministic P&L engine over normalized Schwab activity.

Cost convention (verified live): every transfer item carries a *signed* ``cost``
in cash terms — negative when cash leaves the account, positive when cash
arrives. ``positionEffect`` is ``OPENING`` or ``CLOSING`` on security legs, and
the ``CURRENCY_USD`` leg carries the cash movement with no position effect.

Because ``cost`` is signed cash, realized P&L for a matched open/close pair is
simply the sum of the two signed costs — no long/short special-casing:

    buy  50 @ cost -3835.50 (cash out)
    sell 50 @ cost +4000.00 (cash in)   ->  realized +164.50

Fees are separate CURRENCY legs carrying ``feeType``, so they are accumulated
separately and never double-counted inside the security leg.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict, deque
from typing import Any

SECURITY_ASSET_TYPES = {"EQUITY", "OPTION", "FUTURE", "COLLECTIVE_INVESTMENT", "MUTUAL_FUND", "BOND", "ETF"}

_ASSET_LABELS = {
    "EQUITY": "Equity",
    "OPTION": "Options",
    "FUTURE": "Futures",
    "COLLECTIVE_INVESTMENT": "Funds",
    "MUTUAL_FUND": "Funds",
    "BOND": "Bonds",
    "ETF": "Equity",
    "CURRENCY": "Cash",
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def _asset_label(asset_type: str) -> str:
    return _ASSET_LABELS.get((asset_type or "").upper(), (asset_type or "Other").title() or "Other")


def _instrument_symbol(item: dict[str, Any]) -> str:
    """Reporting label. For options this is the UNDERLYING (a group dimension)."""
    instrument = item.get("instrument") if isinstance(item.get("instrument"), dict) else {}
    symbol = str(instrument.get("symbol") or "").strip().upper()
    if instrument.get("assetType") == "OPTION":
        underlying = str(instrument.get("underlyingSymbol") or "").strip().upper()
        return f"{underlying or symbol}"
    return symbol


def _contract_key(item: dict[str, Any]) -> str:
    """FIFO matching identity — the FULL instrument, not the reporting label.

    Reviewer F05: keying FIFO on the underlying let different strikes, expiries and
    call/put legs consume each other's lots. An option's own contract symbol is its
    identity, so it is used verbatim. Non-options keep their symbol (plus CUSIP when
    the provider supplies one, to survive ticker changes).
    """
    instrument = item.get("instrument") if isinstance(item.get("instrument"), dict) else {}
    asset = str(instrument.get("assetType") or "").upper()
    symbol = str(instrument.get("symbol") or "").strip().upper()
    cusip = str(instrument.get("cusip") or "").strip().upper()
    if asset == "OPTION":
        # The contract symbol already encodes root, expiry, right and strike.
        return f"OPTION:{symbol or cusip}"
    return f"{asset}:{cusip or symbol}"


def _is_security_item(item: dict[str, Any]) -> bool:
    instrument = item.get("instrument") if isinstance(item.get("instrument"), dict) else {}
    return str(instrument.get("assetType") or "").upper() in SECURITY_ASSET_TYPES


def _is_fee_item(item: dict[str, Any]) -> bool:
    return bool(str(item.get("feeType") or "").strip())


# --------------------------------------------------------------------------- #
# Realized P&L (FIFO)
# --------------------------------------------------------------------------- #

def realized_pnl(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Match OPENING/CLOSING security legs FIFO and return realized P&L detail."""
    lots: dict[tuple[str, str], deque[dict[str, float]]] = defaultdict(deque)
    trades: list[dict[str, Any]] = []
    fees_total = 0.0
    income_total = 0.0
    income_by_type: dict[str, float] = defaultdict(float)
    unmatched_closes: list[dict[str, Any]] = []

    ordered = sorted(transactions, key=lambda r: str(r.get("time") or ""))
    for row in ordered:
        tx_type = str(row.get("type") or "").upper()
        when = _parse_time(row.get("time") or row.get("tradeDate"))
        items = [i for i in (row.get("transferItems") or []) if isinstance(i, dict)]

        if tx_type != "TRADE":
            amount = _number(row.get("netAmount"))
            if tx_type in {"DIVIDEND_OR_INTEREST", "CASH_RECEIPT"} and amount:
                income_total += amount
                income_by_type[tx_type] += amount
            continue

        for item in items:
            if _is_fee_item(item) and not _is_security_item(item):
                fees_total += -_number(item.get("cost"))  # fees leave cash
                continue
            if not _is_security_item(item):
                continue
            symbol = _instrument_symbol(item)
            asset_type = str((item.get("instrument") or {}).get("assetType") or "").upper()
            qty = _number(item.get("amount"))
            cost = _number(item.get("cost"))
            effect = str(item.get("positionEffect") or "").upper()
            if not symbol or qty == 0:
                continue
            key = (_contract_key(item), asset_type)
            remaining = abs(qty)

            if effect == "OPENING":
                lots[key].append({"qty": remaining, "cash_per_unit": cost / remaining if remaining else 0.0,
                                  "time": when, "symbol": symbol, "contract_key": key[0]})
                continue

            # CLOSING (or unknown effect with a matching lot): consume FIFO.
            # Always divide by ABS(qty): `cost` is signed cash, `amount` is signed
            # position, so cash-per-position-unit must use the magnitude.
            proceeds_per_unit = cost / remaining if remaining else 0.0
            realized = 0.0
            matched = 0.0
            while remaining > 1e-9 and lots[key]:
                lot = lots[key][0]
                take = min(remaining, lot["qty"])
                realized += take * (proceeds_per_unit + lot["cash_per_unit"])
                lot["qty"] -= take
                remaining -= take
                matched += take
                if lot["qty"] <= 1e-9:
                    lots[key].popleft()
            if matched <= 0:
                unmatched_closes.append({
                    "symbol": symbol, "asset_type": asset_type, "qty": abs(qty),
                    "time": when.isoformat() if when else None,
                    "note": "closing leg without a matched opening lot in the window",
                })
                continue
            # F17b: a close can exceed the lots available in this window. The matched
            # part is reported below, but the EXCESS must be surfaced too — otherwise
            # a partial close silently hides an unmatched residual and the cost basis
            # looks complete when it is not.
            residual = remaining
            if residual > 1e-9:
                unmatched_closes.append({
                    "symbol": symbol, "asset_type": asset_type, "qty": round(residual, 4),
                    "time": when.isoformat() if when else None,
                    "note": ("unmatched residual: the close exceeded the opening lots "
                             "available in this window (partial match only)"),
                })
            trades.append({
                "symbol": symbol,
                "asset_type": asset_type,
                "asset_label": _asset_label(asset_type),
                "qty": matched,
                "realized": round(realized, 2),
                "closed_at": when.isoformat() if when else None,
                "order_id": row.get("orderId"),
                "partial": residual > 1e-9,
                "unmatched_qty": round(residual, 4) if residual > 1e-9 else 0.0,
            })

    open_lots = [
        {"symbol": queue[0]["symbol"] if queue else contract_key,
         "contract_key": contract_key,
         "asset_type": asset,
         "qty": round(sum(l["qty"] for l in queue), 4),
         "cost_per_unit": round(queue[0]["cash_per_unit"], 4) if queue else 0.0}
        for (contract_key, asset), queue in lots.items() if queue
    ]

    wins = [t for t in trades if t["realized"] > 0]
    losses = [t for t in trades if t["realized"] < 0]
    gross_win = sum(t["realized"] for t in wins)
    gross_loss = -sum(t["realized"] for t in losses)
    return {
        "trades": trades,
        "trade_count": len(trades),
        "realized_gross": round(sum(t["realized"] for t in trades), 2),
        "fees": round(fees_total, 2),
        "realized_net": round(sum(t["realized"] for t in trades) - fees_total, 2),
        "income": round(income_total, 2),
        "income_by_type": {k: round(v, 2) for k, v in income_by_type.items()},
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades), 4) if trades else None,
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "open_lots": sorted(open_lots, key=lambda r: r["symbol"]),
        "unmatched_closes": unmatched_closes,
    }


# --------------------------------------------------------------------------- #
# Unrealized P&L (from positions)
# --------------------------------------------------------------------------- #

def unrealized_pnl(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Unrealized P&L per position, using a SIGNED identity (reviewer F17a).

    Schwab reports ``marketValue`` as a signed figure: positive for a long, NEGATIVE
    for a short (a short is a liability). The previous fallback computed
    ``market_value - abs(qty)*avg``, which for a short became
    ``-900 - 1000 = -1900`` instead of the correct ``+100``.

    The correct identity needs no convention guesswork, because it uses the same
    sign on both sides:

        signed_qty  = longQuantity - shortQuantity
        cost_signed = signed_qty * averagePrice * multiplier
        unrealized  = marketValue - cost_signed

    Long  : +1100 - (+10 * 100) = +100
    Short :  -900 - (-10 * 100) = +100

    ``cost_basis`` is still REPORTED as a positive magnitude, because that is the
    capital at risk a reader expects. When no market value is available and the
    broker did not supply a P&L, the result is ``None`` rather than a guess.
    """
    rows: list[dict[str, Any]] = []
    for raw in snapshot.get("positions") or []:
        instrument = raw.get("instrument") if isinstance(raw.get("instrument"), dict) else {}
        asset_type = str(instrument.get("assetType") or "EQUITY").upper()
        symbol = _instrument_symbol(raw)
        long_qty = _number(raw.get("longQuantity"))
        short_qty = _number(raw.get("shortQuantity"))
        qty = long_qty - short_qty
        avg = _number(raw.get("averagePrice"))
        multiplier = 100.0 if asset_type == "OPTION" else 1.0
        cost_basis = abs(qty) * avg * multiplier

        supplied = raw.get("longOpenProfitLoss") if qty >= 0 else raw.get("shortOpenProfitLoss")
        if supplied is None:
            supplied = raw.get("openProfitLoss")

        market_value_raw = raw.get("marketValue")
        has_market_value = market_value_raw is not None
        market_value = _number(market_value_raw)

        if supplied is not None:
            pnl: float | None = _number(supplied)
            basis = "BROKER_SUPPLIED"
        elif has_market_value and abs(qty) > 1e-9:
            pnl = market_value - (qty * avg * multiplier)
            basis = "SIGNED_IDENTITY"
        else:
            pnl = None
            basis = "UNAVAILABLE"

        pnl_pct = (pnl / cost_basis * 100.0) if (pnl is not None and cost_basis > 0) else None
        day = raw.get("currentDayProfitLoss")
        rows.append({
            "symbol": symbol,
            "asset_type": asset_type,
            "asset_label": _asset_label(asset_type),
            "quantity": qty,
            "average_price": avg,
            "market_value": round(market_value, 2) if has_market_value else None,
            "cost_basis": round(cost_basis, 2),
            "unrealized": round(pnl, 2) if pnl is not None else None,
            "unrealized_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "day_pnl": round(_number(day), 2) if day is not None else None,
            "basis": basis,
        })
    rows.sort(key=lambda r: (r["unrealized"] is None, -(r["unrealized"] or 0.0)))
    return {
        "positions": rows,
        "total_unrealized": round(sum(r["unrealized"] for r in rows
                                      if r["unrealized"] is not None), 2),
        "total_day_pnl": round(sum(r["day_pnl"] or 0.0 for r in rows), 2),
        "total_market_value": round(sum(r["market_value"] or 0.0 for r in rows), 2),
        "positions_without_pnl": [r["symbol"] for r in rows if r["unrealized"] is None],
    }


# --------------------------------------------------------------------------- #
# Aggregations
# --------------------------------------------------------------------------- #

def _group(trades: list[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for trade in trades:
        name = trade.get(key) or "Unknown"
        bucket = buckets.setdefault(name, {"name": name, "realized": 0.0, "trades": 0, "wins": 0, "losses": 0})
        bucket["realized"] += trade["realized"]
        bucket["trades"] += 1
        if trade["realized"] > 0:
            bucket["wins"] += 1
        elif trade["realized"] < 0:
            bucket["losses"] += 1
    out = []
    for bucket in buckets.values():
        out.append({
            "name": bucket["name"],
            "label": bucket["name"] if key != "asset_type" else _asset_label(bucket["name"]),
            "realized": round(bucket["realized"], 2),
            "trades": bucket["trades"],
            "wins": bucket["wins"],
            "losses": bucket["losses"],
            "win_rate": round(bucket["wins"] / bucket["trades"], 4) if bucket["trades"] else None,
        })
    out.sort(key=lambda r: r["realized"], reverse=True)
    return out


def _bucket(trades: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Aggregate trades by an arbitrary date key (YYYY-MM or YYYY-MM-DD)."""
    buckets: dict[str, dict[str, Any]] = {}
    for trade in trades:
        closed = str(trade.get("closed_at") or "")
        stamp = closed[:7] if key == "month" else closed[:10]
        if not stamp:
            stamp = "unknown"
        bucket = buckets.setdefault(stamp, {
            "key": stamp, "realized": 0.0, "trades": 0, "wins": 0, "losses": 0,
            "gross_win": 0.0, "gross_loss": 0.0, "fees": 0.0,
            "equity": 0.0, "options": 0.0, "futures": 0.0, "funds": 0.0,
            "symbols": {},
        })
        amount = float(trade.get("realized") or 0.0)
        bucket["realized"] += amount
        bucket["trades"] += 1
        if amount > 0:
            bucket["wins"] += 1
            bucket["gross_win"] += amount
        elif amount < 0:
            bucket["losses"] += 1
            bucket["gross_loss"] += -amount
        bucket["fees"] += float(trade.get("fees") or 0.0)
        asset = str(trade.get("asset_type") or "").upper()
        if asset == "OPTION":
            bucket["options"] += amount
        elif asset == "FUTURE":
            bucket["futures"] += amount
        elif asset in {"COLLECTIVE_INVESTMENT", "MUTUAL_FUND"}:
            bucket["funds"] += amount
        else:
            bucket["equity"] += amount
        symbol = str(trade.get("symbol") or "?")
        entry = bucket["symbols"].setdefault(symbol, {"realized": 0.0, "trades": 0})
        entry["realized"] += amount
        entry["trades"] += 1

    out: list[dict[str, Any]] = []
    for bucket in buckets.values():
        trades_n = bucket["trades"]
        gross_loss = bucket["gross_loss"]
        top = sorted(bucket["symbols"].items(), key=lambda kv: kv[1]["realized"], reverse=True)
        out.append({
            "key": bucket["key"],
            "realized": round(bucket["realized"], 2),
            "trades": trades_n,
            "wins": bucket["wins"],
            "losses": bucket["losses"],
            "win_rate": round(bucket["wins"] / trades_n, 4) if trades_n else None,
            "gross_win": round(bucket["gross_win"], 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(bucket["gross_win"] / gross_loss, 2) if gross_loss > 0 else None,
            "equity": round(bucket["equity"], 2),
            "options": round(bucket["options"], 2),
            "futures": round(bucket["futures"], 2),
            "funds": round(bucket["funds"], 2),
            "best": {"symbol": top[0][0], "realized": round(top[0][1]["realized"], 2)} if top else None,
            "worst": {"symbol": top[-1][0], "realized": round(top[-1][1]["realized"], 2)} if top else None,
            "symbols": [{"symbol": s, "realized": round(v["realized"], 2), "trades": v["trades"]}
                        for s, v in top],
        })
    out.sort(key=lambda r: r["key"])
    return out


def _month_days(trades: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Per-month, per-day breakdown for drill-down."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        closed = str(trade.get("closed_at") or "")
        month = closed[:7] or "unknown"
        grouped.setdefault(month, []).append(trade)
    return {month: _bucket(rows, "day") for month, rows in grouped.items()}


def _trade_split(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """The headline split: options vs stocks vs futures vs funds."""
    categories = {
        "OPTION": "options",
        "FUTURE": "futures",
        "COLLECTIVE_INVESTMENT": "funds",
        "MUTUAL_FUND": "funds",
        "BOND": "bonds",
        "EQUITY": "stocks",
        "ETF": "stocks",
    }
    buckets: dict[str, dict[str, Any]] = {}
    for trade in trades:
        asset = str(trade.get("asset_type") or "EQUITY").upper()
        name = categories.get(asset, "other")
        bucket = buckets.setdefault(name, {
            "name": name, "realized": 0.0, "trades": 0, "wins": 0, "losses": 0,
            "gross_win": 0.0, "gross_loss": 0.0, "symbols": set(),
        })
        amount = float(trade.get("realized") or 0.0)
        bucket["realized"] += amount
        bucket["trades"] += 1
        if amount > 0:
            bucket["wins"] += 1
            bucket["gross_win"] += amount
        elif amount < 0:
            bucket["losses"] += 1
            bucket["gross_loss"] += -amount
        bucket["symbols"].add(str(trade.get("symbol") or "?"))

    order = ["options", "stocks", "futures", "funds", "bonds", "other"]
    total = sum(b["realized"] for b in buckets.values())
    rows = []
    for name in order:
        bucket = buckets.get(name)
        if bucket is None:
            continue
        trades_n = bucket["trades"]
        rows.append({
            "name": name,
            "realized": round(bucket["realized"], 2),
            "trades": trades_n,
            "wins": bucket["wins"],
            "losses": bucket["losses"],
            "win_rate": round(bucket["wins"] / trades_n, 4) if trades_n else None,
            "gross_win": round(bucket["gross_win"], 2),
            "gross_loss": round(bucket["gross_loss"], 2),
            "profit_factor": round(bucket["gross_win"] / bucket["gross_loss"], 2)
            if bucket["gross_loss"] > 0 else None,
            "avg_per_trade": round(bucket["realized"] / trades_n, 2) if trades_n else None,
            "share_of_realized": round(bucket["realized"] / total, 4) if total else None,
            "symbols": len(bucket["symbols"]),
        })
    return {
        "options": next((r for r in rows if r["name"] == "options"), {"realized": 0.0, "trades": 0}),
        "stocks": next((r for r in rows if r["name"] == "stocks"), {"realized": 0.0, "trades": 0}),
        "futures": next((r for r in rows if r["name"] == "futures"), {"realized": 0.0, "trades": 0}),
        "funds": next((r for r in rows if r["name"] == "funds"), {"realized": 0.0, "trades": 0}),
        "rows": rows,
        "total_realized": round(total, 2),
    }


def _monthly(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for trade in trades:
        stamp = str(trade.get("closed_at") or "")[:7] or "unknown"
        bucket = buckets.setdefault(stamp, {"month": stamp, "realized": 0.0, "trades": 0})
        bucket["realized"] += trade["realized"]
        bucket["trades"] += 1
    out = [{"month": b["month"], "realized": round(b["realized"], 2), "trades": b["trades"]}
           for b in buckets.values()]
    out.sort(key=lambda r: r["month"])
    return out


def normalize_transactions(transactions: list[dict[str, Any]], limit: int = 500) -> list[dict[str, Any]]:
    """Flatten transactions into display rows (most recent first)."""
    rows: list[dict[str, Any]] = []
    for row in transactions[:limit]:
        items = [i for i in (row.get("transferItems") or []) if isinstance(i, dict)]
        security = next((i for i in items if _is_security_item(i)), None)
        fees = sum(-_number(i.get("cost")) for i in items if _is_fee_item(i) and not _is_security_item(i))
        instrument = (security or {}).get("instrument") if security else {}
        instrument = instrument if isinstance(instrument, dict) else {}
        asset_type = str(instrument.get("assetType") or "").upper()
        rows.append({
            "activity_id": row.get("activityId"),
            "time": row.get("time") or row.get("tradeDate"),
            "type": row.get("type"),
            "status": row.get("status"),
            "sub_account": row.get("subAccount"),
            "order_id": row.get("orderId"),
            "net_amount": round(_number(row.get("netAmount")), 2),
            "fees": round(fees, 2),
            "symbol": _instrument_symbol(security) if security else None,
            "asset_type": asset_type or None,
            "asset_label": _asset_label(asset_type) if asset_type else None,
            "description": instrument.get("description"),
            "quantity": round(_number(security.get("amount")), 4) if security else None,
            "price": round(_number(security.get("price")), 4) if security else None,
            "cost": round(_number(security.get("cost")), 2) if security else None,
            "position_effect": (security or {}).get("positionEffect"),
        })
    return rows


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #

def build_report(
    activity: Any,
    snapshot: dict[str, Any],
    *,
    account: dict[str, Any] | None = None,
    days: int = 400,
    transaction_limit: int = 500,
) -> dict[str, Any]:
    """Assemble the complete deterministic account report."""
    transactions = list(getattr(activity, "transactions", []) or [])
    realized = realized_pnl(transactions)
    unreal = unrealized_pnl(snapshot)
    balances = snapshot.get("balances") or {}
    equity = _number(balances.get("liquidationValue") or balances.get("equity"))

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_days": days,
        "account": account or {},
        "balances": {
            "equity": round(equity, 2),
            "cash": round(_number(balances.get("cashBalance")), 2),
            "buying_power": round(_number(balances.get("buyingPower") or balances.get("availableFunds")), 2),
            "long_market_value": round(_number(balances.get("longMarketValue")), 2),
            "short_market_value": round(_number(balances.get("shortMarketValue")), 2),
            "long_option_value": round(_number(balances.get("longOptionMarketValue")), 2),
            "short_option_value": round(_number(balances.get("shortOptionMarketValue")), 2),
        },
        "totals": {
            "realized_gross": realized["realized_gross"],
            "realized_net": realized["realized_net"],
            "fees": realized["fees"],
            "income": realized["income"],
            "unrealized": unreal["total_unrealized"],
            "day_pnl": unreal["total_day_pnl"],
            "total_pnl": round(realized["realized_net"] + unreal["total_unrealized"], 2),
        },
        "performance": {
            "closed_trades": realized["trade_count"],
            "wins": realized["wins"],
            "losses": realized["losses"],
            "win_rate": realized["win_rate"],
            "avg_win": realized["avg_win"],
            "avg_loss": realized["avg_loss"],
            "profit_factor": realized["profit_factor"],
            "gross_win": realized["gross_win"],
            "gross_loss": realized["gross_loss"],
        },
        "by_asset_type": _group(realized["trades"], "asset_type", "asset"),
        "by_symbol": _group(realized["trades"], "symbol", "symbol"),
        "monthly": _monthly(realized["trades"]),
        # Drill-down: month rows carry per-day rows for that month.
        "by_month": _bucket(realized["trades"], "month"),
        "month_days": _month_days(realized["trades"]),
        "by_day": _bucket(realized["trades"], "day"),
        # Headline split the brief asks for: options vs stocks.
        "trade_split": _trade_split(realized["trades"]),
        "income_by_type": realized["income_by_type"],
        "open_lots": realized["open_lots"],
        "unmatched_closes": realized["unmatched_closes"],
        "closed_trades": realized["trades"][:500],
        "positions": unreal["positions"],
        "transactions": normalize_transactions(transactions, limit=transaction_limit),
        "transaction_count": len(transactions),
        "quality": {
            "windows": getattr(activity, "windows", 0),
            "truncated": bool(getattr(activity, "truncated", False)),
            "truncated_windows": list(getattr(activity, "truncated_windows", []) or []),
            "errors": list(getattr(activity, "errors", []) or []),
            "cost_method": "FIFO over signed transfer-item cost; fees reported separately",
            "accounting_scope": "per-account only; lots, P&L and balances are never combined across accounts",
        },
    }
