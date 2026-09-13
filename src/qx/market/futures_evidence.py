"""Explicit-contract futures diagnostics, separate from continuous-series signals."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.market_data import _candles_frame
from qx.brokers.schwab.quotes import SchwabQuoteProvider
from qx.data.quotes import QuoteSnapshot
from qx.market.movers import _validate_bars


def _age(timestamp: datetime | None, now: datetime) -> float | None:
    if timestamp is None or timestamp.utcoffset() is None:
        return None
    return (now - timestamp).total_seconds()


def classify_continuity_readiness(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify whether explicit-contract evidence is safe to combine with cash levels.

    This is intentionally pure: it neither fetches data nor promotes a trade signal.
    A correctly identified contract is only one prerequisite.  The caller must also
    prove a fresh quote, matching contract history, continuous-series comparability,
    and cash-session synchronization before the evidence can be called ready.
    """
    contract_identified = evidence.get("contract_status") == "provider_identified"
    quote_fresh = evidence.get("quote_status") == "fresh_at_check"
    history_identified = evidence.get("history_status") == "provider_contract_matched"
    continuous_verified = evidence.get("continuous_cache_comparable") is True
    cash_session_verified = evidence.get("cash_close_synchronized") is True

    blockers: list[str] = []
    if not contract_identified:
        blockers.append("explicit_contract_identity_unverified")
    if not quote_fresh:
        blockers.append("quote_not_fresh")
    if not history_identified:
        blockers.append("explicit_contract_history_unverified")
    if not continuous_verified:
        blockers.append("continuous_series_comparability_unverified")
    if not cash_session_verified:
        blockers.append("cash_session_synchronization_unverified")

    continuity_ready = bool(
        contract_identified and quote_fresh and history_identified and continuous_verified
    )
    evidence_ready = bool(continuity_ready and cash_session_verified)
    return {
        "contract_identity_verified": contract_identified,
        "quote_fresh": quote_fresh,
        "history_identity_verified": history_identified,
        "continuous_series_verified": continuous_verified,
        "cash_session_verified": cash_session_verified,
        "continuity_status": "verified" if continuity_ready else "blocked",
        "readiness_status": "evidence_ready" if evidence_ready else "blocked",
        "readiness_blockers": blockers,
        # Readiness is evidence-only. Signal eligibility belongs to a separate,
        # explicitly authorized execution layer and is always false here.
        "live_signal_eligible": False,
    }


def quote_evidence(quote: QuoteSnapshot, now: datetime) -> dict[str, Any]:
    if now.utcoffset() is None:
        raise ValueError("Quote check requires an aware clock")
    root = {"ES=F":"/ES", "NQ=F":"/NQ", "/ES":"/ES", "/NQ":"/NQ"}.get(quote.symbol)
    contract = quote.resolved_symbol
    match = re.fullmatch(r"/(ES|NQ)([HMUZ])(\d{2}|\d{4})", contract or "")
    expiry = quote.expiration
    identified = bool(root and match and contract and contract.startswith(root)
                      and quote.asset_type == "FUTURE" and quote.provider == "schwab"
                      and expiry and expiry.utcoffset() is not None and expiry > now)
    if identified and match and expiry:
        expiry_date = expiry.astimezone(ZoneInfo("America/New_York"))
        year = str(expiry_date.year) if len(match[3]) == 4 else f"{expiry_date.year % 100:02d}"
        identified = match[3] == year and {"H":3,"M":6,"U":9,"Z":12}[match[2]] == expiry_date.month
    quote_age, trade_age = _age(quote.timestamp, now), _age(quote.trade_timestamp, now)
    prices = (quote.last, quote.bid, quote.ask)
    price_valid = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                      and math.isfinite(value) and value > 0 for value in prices)
    if price_valid:
        price_valid = bool(quote.bid is not None and quote.ask is not None and quote.bid <= quote.ask)
    fresh = bool(identified and price_valid and quote.realtime is True
                 and quote_age is not None and 0 <= quote_age <= 60
                 and trade_age is not None and 0 <= trade_age <= 60)
    evidence = {
        "requested_symbol": quote.symbol, "contract": contract, "source": quote.provider,
        "checked_at": now.isoformat(), "quote_time": quote.timestamp.isoformat() if quote.timestamp else None,
        "trade_time": quote.trade_timestamp.isoformat() if quote.trade_timestamp else None,
        "quote_age_seconds": quote_age, "trade_age_seconds": trade_age,
        "expiration": expiry.isoformat() if expiry else None, "realtime": quote.realtime,
        "last": quote.last if price_valid else None,
        "contract_status": "provider_identified" if identified else "unverified",
        "quote_status": "fresh_at_check" if fresh else "unverified_or_stale",
        "max_age_seconds": 60, "history_status": "not_checked", "intraday_status": "not_checked",
        "continuous_cache_comparable": False, "cash_close_synchronized": False,
    }
    return {**evidence, **classify_continuity_readiness(evidence)}


def inspect_futures_contracts(client: SchwabApiClient, *, now: datetime | None = None) -> dict[str, Any]:
    """User-triggered provider reads only; no fallback, cache mutation, AI or orders."""
    if now is not None and now.utcoffset() is None:
        raise ValueError("Quote check requires an aware clock")
    # A single check clock makes the two quote reads and the report reproducible.
    # It also prevents a boundary crossing from making one row internally
    # inconsistent merely because its requests took longer than the other row.
    checked_at = now or datetime.now(timezone.utc)
    provider = SchwabQuoteProvider(client)
    rows: list[dict[str, Any]] = []
    for symbol in ("ES=F", "NQ=F"):
        row: dict[str, Any] = {"requested_symbol": symbol, "quote_status":"unavailable",
                               "history_status":"not_checked", "live_signal_eligible":False}
        try:
            quote = provider.get_quote(symbol)
            row = quote_evidence(quote, checked_at)
            if row["contract_status"] != "provider_identified":
                rows.append(row)
                continue
            contract = row["contract"]
            payload = client.get("/marketdata/v1/pricehistory", params={
                "symbol":contract, "periodType":"year", "period":1,
                "frequencyType":"daily", "frequency":1,
                "needExtendedHoursData":"false", "needPreviousClose":"false",
            })
            if payload.get("symbol") != contract:
                raise ValueError("History contract differs from requested contract")
            candles = payload.get("candles")
            if not isinstance(candles, list):
                raise ValueError("Missing contract candles")
            history = _candles_frame(candles)
            _validate_bars(history)
            if history.index[-1] > checked_at:
                raise ValueError("Future contract history")
            intraday_payload = client.get("/marketdata/v1/pricehistory", params={
                "symbol": contract, "periodType": "day", "period": 5,
                "frequencyType": "minute", "frequency": 5,
                "needExtendedHoursData": "true", "needPreviousClose": "false",
            })
            if intraday_payload.get("symbol") != contract:
                raise ValueError("Intraday contract differs from requested contract")
            intraday_candles = intraday_payload.get("candles")
            if not isinstance(intraday_candles, list):
                raise ValueError("Missing intraday contract candles")
            intraday = _candles_frame(intraday_candles)
            _validate_bars(intraday)
            if intraday.index[-1] > checked_at:
                raise ValueError("Future intraday contract history")
            bar_age = _age(intraday.index[-1].to_pydatetime(), checked_at)
            intraday_status = "fresh_at_check" if bar_age is not None and 0 <= bar_age <= 900 else "stale_at_check"
            recheck = provider.get_quote(symbol)
            current = quote_evidence(recheck, checked_at)
            if current["contract"] != contract:
                row.update(history_status="contract_changed_during_check", quote_status="unverified_or_stale")
            else:
                row = {**current, "history_status":"provider_contract_matched",
                       "history_bars":len(history), "history_last_timestamp":history.index[-1].isoformat(),
                       "history_sha256":sha256(json.dumps(candles, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                       "intraday_status":intraday_status, "intraday_bars":len(intraday),
                       "intraday_last_timestamp":intraday.index[-1].isoformat(),
                       "intraday_bar_age_seconds":bar_age,
                       "intraday_sha256":sha256(json.dumps(intraday_candles, sort_keys=True, allow_nan=False).encode()).hexdigest()}
        except Exception:
            # Never expose provider request details, tokens or account information.
            row["history_status"] = "history_or_provider_unavailable"
        rows.append({**row, **classify_continuity_readiness(row)})
    return {"schema_version":"qx.futures-evidence.v1", "checked_at":checked_at.isoformat(),
            "rows":rows, "model_calls":0,
            "limitations":[
                "Contract identity is reported by the provider, not independently certified.",
                "Continuous cached futures are not matched to these explicit contracts; do not combine their levels with these quotes.",
                "Five-minute bars are reported only for the same provider-resolved contract and are fresh only at the recorded check time.",
                "Completed CME sessions, historical roll adjustments and a synchronized cash-close reference remain unverified.",
                "Quote freshness applies only at the recorded check time; no streaming or trade signal is enabled.",
            ]}
