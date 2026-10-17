"""QX market context: intraday levels, futures basis and dealer gamma (GEX).

Everything here is READ-ONLY over the broker's market-data API. Levels are
derived from real bars; GEX reuses the repository's own
``qx.options.gex.calculate_gamma_exposure`` so the dealer-positioning semantics
(and its settlement provenance) are the existing ones, not a reinvention.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any

from qx.scanner.engine import MarketData

FUTURES = (
    ("/ES", "E-mini S&P 500", "$SPX"),
    ("/NQ", "E-mini Nasdaq 100", "$NDX"),
    ("/YM", "E-mini Dow", "$DJX"),
    ("/RTY", "E-mini Russell 2000", "$RUT"),
    ("/CL", "Crude Oil", None),
    ("/GC", "Gold", None),
    ("/BTC", "Bitcoin", None),
)

# (root, label, cash proxy) — the cash proxy is what GEX can actually use.
FUTURES_PROXIES = FUTURES


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _session_split(bars: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split daily bars into (all-but-today, reference)."""
    return bars[:-1], bars[-1:]


# --------------------------------------------------------------------------- #
# Levels
# --------------------------------------------------------------------------- #

def levels(symbol: str = "SPY") -> dict[str, Any]:
    """Prior-day, overnight and session-derived reference levels."""
    market = MarketData()
    bars, source = market.bars(symbol)
    quote, quote_source = market.quote(symbol)
    if not bars:
        return {"symbol": symbol.upper(), "error": "no price data", "source": source}

    prior = bars[-2] if len(bars) >= 2 else bars[-1]
    last = bars[-1]
    history, _ = _session_split(bars)
    closes = [b["close"] for b in history]

    # ATR + VWAP-style bands from the last 20 sessions.
    window = bars[-21:-1] if len(bars) > 21 else bars[:-1]
    highs = [b["high"] for b in window]
    lows = [b["low"] for b in window]
    typical = [((b["high"] + b["low"] + b["close"]) / 3.0) for b in window]
    volumes = [_number(b.get("volume")) for b in window]
    total_volume = sum(volumes)
    vwap = (sum(t * v for t, v in zip(typical, volumes)) / total_volume) if total_volume else (
        sum(typical) / len(typical) if typical else 0.0)
    variance = (sum(v * (t - vwap) ** 2 for t, v in zip(typical, volumes)) / total_volume) if total_volume else 0.0
    sigma = variance ** 0.5 if variance > 0 else 0.0

    # True range over the last 15 bars, using the PREVIOUS bar's close relative
    # to the true series (a slice-relative index would read the wrong bar).
    ranges = []
    for i in range(len(bars) - 15, len(bars)):
        if i <= 0:
            continue
        bar, prev = bars[i], bars[i - 1]
        ranges.append(max(bar["high"] - bar["low"],
                          abs(bar["high"] - prev["close"]),
                          abs(bar["low"] - prev["close"])))
    atr = (sum(ranges) / len(ranges)) if ranges else 0.0

    price = _number((quote or {}).get("last")) or last["close"]
    return {
        "symbol": symbol.upper(),
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source,
        "quote_source": quote_source,
        "realtime": bool((quote or {}).get("realtime")),
        "price": round(price, 2),
        "change_pct": (quote or {}).get("change_pct") or (last["close"] / prior["close"] - 1.0 if prior["close"] else None),
        "prior_day": {
            "high": round(prior["high"], 2),
            "low": round(prior["low"], 2),
            "close": round(prior["close"], 2),
            "open": round(prior["open"], 2),
        },
        "today": {
            "open": round(last["open"], 2),
            "high": round(last["high"], 2),
            "low": round(last["low"], 2),
            "close": round(last["close"], 2),
        },
        "range_20d": {"high": round(max(highs), 2) if highs else None,
                      "low": round(min(lows), 2) if lows else None},
        "anchored_vwap_20d": round(vwap, 2),
        "vwap_bands_20d": {
            "upper_2": round(vwap + 2 * sigma, 2),
            "upper_1": round(vwap + sigma, 2),
            "vwap": round(vwap, 2),
            "lower_1": round(vwap - sigma, 2),
            "lower_2": round(vwap - 2 * sigma, 2),
        },
        "atr_14": round(atr, 2),
        "fifty_two_week": {
            "high": round(max(b["high"] for b in bars[-252:]), 2) if bars else None,
            "low": round(min(b["low"] for b in bars[-252:]), 2) if bars else None,
        },
        "position_vs": {
            "vs_prior_close": round((price / prior["close"] - 1.0) * 100, 2) if prior["close"] else None,
            "vs_prior_high": round((price / prior["high"] - 1.0) * 100, 2) if prior["high"] else None,
            "vs_prior_low": round((price / prior["low"] - 1.0) * 100, 2) if prior["low"] else None,
            "vs_vwap": round((price / vwap - 1.0) * 100, 2) if vwap else None,
        },
        "bars": len(bars),
        "closes": [round(b["close"], 2) for b in bars[-120:]],
    }


# --------------------------------------------------------------------------- #
# Futures
# --------------------------------------------------------------------------- #

def futures() -> dict[str, Any]:
    """Index futures with basis versus their OWN cash index (never cross-index)."""
    market = MarketData()
    rows = []
    for symbol, label, cash_symbol in FUTURES:
        # A futures root may have NO declared cash equivalent (crude, gold, bitcoin).
        # Basis is then unavailable and is reported as such — never computed against
        # an unrelated index.
        cash_quote = cash_source = None
        if cash_symbol:
            cash_quote, cash_source = market.quote(cash_symbol)
        cash = _number((cash_quote or {}).get("last"))
        quote, source = market.quote(symbol)
        bars, bar_source = market.bars(symbol)
        last = _number((quote or {}).get("last")) or (bars[-1]["close"] if bars else 0.0)
        prior = bars[-2] if len(bars) >= 2 else None
        rows.append({
            "symbol": symbol,
            "label": label,
            "resolved": (quote or {}).get("symbol"),
            "last": round(last, 2) if last else None,
            "change_pct": (quote or {}).get("change_pct"),
            "realtime": bool((quote or {}).get("realtime")),
            "source": source,
            "bar_source": bar_source,
            "prior_high": round(prior["high"], 2) if prior else None,
            "prior_low": round(prior["low"], 2) if prior else None,
            "cash_symbol": cash_symbol,
            "cash_last": cash or None,
            "cash_source": cash_source,
            "basis_available": bool(cash_symbol and cash),
            "basis_note": None if (cash_symbol and cash) else (
                "no declared cash equivalent for this root" if not cash_symbol
                else "cash index quote unavailable"),
            "basis_vs_cash": round(last - cash, 2) if last and cash else None,
            "basis_pct": round((last / cash - 1.0) * 100, 3) if last and cash else None,
        })
    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "futures": rows,
    }


# --------------------------------------------------------------------------- #
# Dealer gamma (GEX) — reuses the repo engine
# --------------------------------------------------------------------------- #

def chain_symbol(symbol: str) -> str:
    """Map a display symbol to the form Schwab's option-chain endpoint accepts.

    Verified against the live API: INDEX roots MUST carry a ``$`` prefix. ``SPX``
    returns HTTP 400 while ``$SPX`` returns 602 contracts; the same holds for NDX,
    VIX and RUT. Equity and ETF symbols are passed through unchanged, and futures
    roots (``/ES``) have no chain at all, so they are rejected rather than guessed.
    """
    raw = str(symbol or "").strip().upper()
    if not raw:
        return raw
    if raw.startswith("$"):
        return raw
    if raw.startswith("/"):
        return raw          # futures root: caller must decide; no chain exists
    if raw in INDEX_CHAIN_ROOTS:
        return f"${raw}"
    return raw


# Index roots that require the '$' prefix on the chain endpoint.
INDEX_CHAIN_ROOTS = {"SPX", "NDX", "VIX", "RUT", "DJX", "OEX", "XSP"}

# Roots that have NO option chain through this endpoint.
FUTURES_ROOTS = {"/ES", "/NQ", "/CL", "/BTC", "/GC", "/YM", "/RTY", "/SI", "/NG", "/ZB", "/ZN"}


def _expiry_dte(key: str) -> int | None:
    """The ':N' suffix on a Schwab expiry key is days-to-expiration."""
    _, _, suffix = str(key).partition(":")
    try:
        return int(suffix)
    except (TypeError, ValueError):
        return None


def _expiry_open_interest(strikes: Any) -> float:
    total = 0.0
    for contracts in (strikes or {}).values():
        for contract in contracts or []:
            total += _number(contract.get("openInterest"))
    return total


def select_expiries(mapping: dict, max_expiries: int) -> tuple[list[str], dict[str, Any]]:
    """Choose expiries by real DTE, skipping expired and open-interest-empty series.

    The previous rule was ``sorted(mapping.keys())[:n]`` — a LEXICOGRAPHIC sort that
    takes the two earliest expiry keys. On an expiry day after the close those are the
    just-expired 0DTE series, whose open interest has already rolled off, so OI x gamma
    computed to exactly zero and could look like a market reading. Selection now:

      1. orders by real DTE (nearest first), not by string comparison
      2. drops series with DTE < 0 (already expired)
      3. prefers series that actually carry open interest

    and reports what it skipped, so a thin selection is visible rather than silent.
    """
    entries = [{"key": key, "dte": _expiry_dte(key), "oi": _expiry_open_interest(mapping[key])}
               for key in mapping]
    entries.sort(key=lambda e: (e["dte"] is None,
                                e["dte"] if e["dte"] is not None else 0,
                                str(e["key"])))

    def is_expired(entry: dict[str, Any]) -> bool:
        return entry["dte"] is not None and entry["dte"] < 0

    expired = [e for e in entries if is_expired(e)]
    live = [e for e in entries if not is_expired(e)]
    with_oi = [e for e in live if e["oi"] > 0]
    chosen = (with_oi or live)[:max_expiries]
    chosen_keys = {e["key"] for e in chosen}
    return [e["key"] for e in chosen], {
        "expired_skipped": [e["key"] for e in expired],
        "no_open_interest_skipped": [e["key"] for e in live
                                     if e["oi"] <= 0 and e["key"] not in chosen_keys],
        "dte_used": [e["dte"] for e in chosen],
        "selected_from_open_interest": bool(with_oi),
    }


def _chain_frame(symbol: str, max_expiries: int = 2) -> tuple[Any, float, dict[str, Any]]:
    """Fetch a bounded option chain and shape it for the repo's GEX engine."""
    import pandas as pd

    from qx.brokers.schwab.auth import SchwabTokenManager
    from qx.brokers.schwab.client import SchwabApiClient
    from qx.config.settings import get_settings

    settings = get_settings()
    client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
    resolved = chain_symbol(symbol)
    # Large roots overflow Schwab's gateway: $SPX at strikeCount=80 returns a 502
    # (roughly 9,000 contracts), while 40 returns 4,786 in ~2.6s. So the count is
    # tried largest-first and stepped down on a gateway error rather than failing.
    last_error: Exception | None = None
    payload: dict[str, Any] | None = None
    attempts: list[int] = []
    for strike_count in (80, 40, 20, 10):
        attempts.append(strike_count)
        try:
            payload = client.get(
                "/marketdata/v1/chains",
                params={"symbol": resolved, "contractType": "ALL", "strikeCount": strike_count,
                        "includeUnderlyingQuote": "true", "strategy": "SINGLE"},
            )
            break
        except Exception as exc:  # noqa: BLE001 - retry smaller, then re-raise
            last_error = exc
            payload = None
            text = str(exc)
            if not any(code in text for code in ("502", "503", "504", "500")):
                raise
    if payload is None:
        raise last_error if last_error else RuntimeError("option chain unavailable")
    underlying = _number((payload.get("underlying") or {}).get("last"))

    rows: list[dict[str, Any]] = []
    expiries_used: list[str] = []
    selection: dict[str, Any] = {}
    calls_map = payload.get("callExpDateMap") or {}
    puts_map = payload.get("putExpDateMap") or {}
    # Select expiries ONCE from the union of both sides, so calls and puts stay
    # matched at the same expiry and the choice is not order-dependent.
    union: dict[str, Any] = {}
    for source in (calls_map, puts_map):
        for key, value in source.items():
            union.setdefault(key, value)
    chosen_expiries, selection = select_expiries(union, max_expiries)

    for map_key, option_type in (("callExpDateMap", "call"), ("putExpDateMap", "put")):
        mapping = payload.get(map_key) or {}
        for expiry in chosen_expiries:
            if expiry not in mapping:
                continue
            if expiry not in expiries_used:
                expiries_used.append(expiry)
            for strike_key, contracts in (mapping.get(expiry) or {}).items():
                for contract in contracts or []:
                    dte = contract.get("daysToExpiration")
                    rows.append({
                        "strike": _number(contract.get("strikePrice") or strike_key),
                        "option_type": option_type,
                        "open_interest": _number(contract.get("openInterest")),
                        "volume": _number(contract.get("totalVolume")),
                        "gamma": contract.get("gamma"),
                        "delta": contract.get("delta"),
                        "volatility": contract.get("volatility"),
                        "dte": _number(dte),
                        "symbol": contract.get("symbol"),
                        "expiry": expiry,
                    })
    meta = {
        "contracts": len(rows),
        "expiries": expiries_used[:max_expiries],
        "expiry_selection": selection,
        "is_delayed": bool(payload.get("isDelayed")),
        "is_truncated": bool(payload.get("isChainTruncated")),
        "status": payload.get("status"),
        "interest_rate": payload.get("interestRate"),
    }
    return pd.DataFrame(rows), underlying, meta


def gamma(symbol: str = "SPY", max_expiries: int = 2) -> dict[str, Any]:
    """Net dealer gamma, flip level and walls, using the repository's GEX engine.

    A futures root has no chain of its own, so it is mapped to its CASH index when
    one is known (``/ES`` -> ``$SPX``) and the substitution is disclosed rather
    than hidden. Roots with no cash equivalent are refused with a clear reason.
    """
    from qx.options.gex import calculate_gamma_exposure

    requested = str(symbol or "").strip().upper()
    resolved = chain_symbol(requested)
    substituted_from: str | None = None
    if resolved.startswith("/"):
        cash = next((c for f, _label, c in FUTURES_PROXIES if f == resolved), None)
        if not cash:
            return {"symbol": requested, "error": f"no option chain exists for futures root "
                                                  f"{requested}, and no cash equivalent is declared"}
        resolved = chain_symbol(cash)
        substituted_from = requested

    try:
        frame, spot, meta = _chain_frame(resolved, max_expiries)
    except Exception as exc:  # noqa: BLE001 - a broker failure must be reported, not hidden
        return {"symbol": requested, "chain_symbol": resolved,
                "error": f"{type(exc).__name__}: {exc}"[:300]}

    if frame.empty or spot <= 0:
        return {"symbol": requested, "chain_symbol": resolved,
                "error": "empty option chain", "chain": meta}

    # A chain can come back structurally valid but economically EMPTY. Observed on
    # $SPX: ~2,300 contracts across 56 expiries with open interest 0 on EVERY row,
    # which makes OI x gamma exactly zero and would render a confident-looking flat
    # profile. It correlates with the session being closed and affects INDEX roots
    # (SPY was unaffected at the same moment), so the message says what is known and
    # what to try rather than implying the market is neutral.
    total_oi = float(frame["open_interest"].fillna(0).sum())
    if total_oi <= 0:
        from qx.app import timefmt

        session = timefmt.market_session_state().get("state", "UNKNOWN")
        is_index_root = resolved.startswith("$")
        hint = ("Index option open interest can read zero outside regular trading "
                "hours; retry during the session."
                if is_index_root else
                "Source returned no open interest; retry later.")
        return {
            "symbol": requested, "chain_symbol": resolved,
            "substituted_from": substituted_from,
            "spot": round(spot, 2),
            "session_state": session,
            "error": (f"option chain returned no open interest "
                      f"({len(frame)} contracts across "
                      f"{len(meta.get('expiries') or [])} selected expiries, all OI=0) — "
                      f"gamma cannot be computed. Session is {session}. {hint} "
                      "This is a source-data condition, not a market reading."),
            "chain": meta,
        }

    snapshot = calculate_gamma_exposure(resolved, spot, frame)
    # Per-strike net gamma, for the wall profile chart.
    frame = frame.copy()
    multiplier = frame["option_type"].str.lower().map({"call": 1.0, "put": -1.0}).fillna(0.0)
    frame["gex"] = frame["open_interest"] * frame["gamma"].fillna(0.0) * (spot ** 2) * 0.01 * multiplier
    by_strike = (frame.groupby("strike")["gex"].sum().sort_index())
    profile = [
        {"strike": round(float(strike), 2),
         "gex": round(float(value), 2),
         "call_oi": int(frame[(frame["strike"] == strike) & (frame["option_type"] == "call")]["open_interest"].sum()),
         "put_oi": int(frame[(frame["strike"] == strike) & (frame["option_type"] == "put")]["open_interest"].sum())}
        for strike, value in by_strike.items()
    ]
    return {
        "symbol": symbol.upper(),
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "spot": round(spot, 2),
        "net_gamma": snapshot.net_gamma,
        "regime": snapshot.regime,
        "gamma_flip_price": snapshot.gamma_flip_price,
        "call_wall": snapshot.top_call_gamma_strike,
        "put_wall": snapshot.top_put_gamma_strike,
        "call_put_gamma_ratio": snapshot.call_put_gamma_ratio,
        "zero_dte_volume_ratio": snapshot.zero_dte_volume_ratio,
        "expected_move_1sigma": snapshot.expected_move_1sigma,
        "expected_move_2sigma": snapshot.expected_move_2sigma,
        "settlement_source": snapshot.settlement_source,
        "settlement_confidence": snapshot.settlement_confidence,
        "profile": profile,
        "chain": meta,
        "chain_symbol": resolved,
        "substituted_from": substituted_from,
        "method": "repo qx.options.gex.calculate_gamma_exposure (OI x gamma x spot^2 x 0.01, calls +, puts -)",
    }
