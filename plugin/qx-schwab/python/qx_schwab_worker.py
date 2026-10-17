#!/usr/bin/env python3
"""QX Schwab agent worker — realtime Schwab data + SMC rules-engine scoring.

Run inside the QX workspace venv. It is the single data/decision seam the
DSH ``@qx/schwab-plugin`` shells out to. One JSON object is printed on stdout
per invocation; every failure is folded into that JSON (never a traceback).

Subcommands
-----------
status                 Auth/health snapshot.
quotes '<symbols>'     Realtime quotes for a JSON list of symbols.
scan '<payload>'       Full rules-engine scan over a JSON payload of the form
                       {"symbols": [...], "mode": "auto"|"live"|"cache"}.

The rules engine follows `.agents/skills/smc-rules-engine/resources/qx_rules_engine_spec.md`:
    QX Score = 0.25*SMC + 0.20*Phases + 0.20*CVD_Absorption + 0.15*VScore
             + 0.10*RS_Rank + 0.10*OptionsFlow
    score >= 70 -> LONG / BUY CALL      score <= 30 -> SHORT / BUY PUT
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics
import sys
import datetime as _dt

# The QX workspace root; overridable via QX_WORKSPACE_ROOT.
WORKSPACE = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"


def _boot() -> None:
    os.chdir(WORKSPACE)
    src = os.path.join(WORKSPACE, "src")
    if src not in sys.path:
        sys.path.insert(0, src)


_boot()

# --------------------------------------------------------------------------- #
# Schwab plumbing (reuses the qx broker package verbatim)
# --------------------------------------------------------------------------- #

def _load_settings():
    from qx.config.settings import get_settings
    return get_settings()


def _auth_url() -> dict:
    try:
        from qx.brokers.schwab.auth import SchwabTokenManager
        manager = SchwabTokenManager(_load_settings())
        return {"ok": True, "url": manager.authorization_url()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _authorize(value: str) -> dict:
    try:
        from qx.brokers.schwab.auth import SchwabTokenManager
        manager = SchwabTokenManager(_load_settings())
        manager.exchange_authorization_code(value)
        state = manager.status()
        return {"ok": True, "has_token": bool(state.has_token),
                "access_token_valid": bool(state.access_token_valid),
                "message": str(state.message)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _schwab_providers(settings):
    from qx.brokers.schwab.auth import SchwabTokenManager
    from qx.brokers.schwab.client import SchwabApiClient
    from qx.brokers.schwab.quotes import SchwabQuoteProvider
    from qx.brokers.schwab.market_data import SchwabMarketDataProvider
    from qx.models.market import BarDataRequest

    manager = SchwabTokenManager(settings)
    client = SchwabApiClient(manager, base_url=settings.schwab_api_base_url)
    return (
        manager,
        client,
        SchwabQuoteProvider(client),
        SchwabMarketDataProvider(client),
        BarDataRequest,
    )


def _status() -> dict:
    try:
        settings = _load_settings()
        from qx.brokers.schwab.auth import SchwabTokenManager
        manager = SchwabTokenManager(settings)
        state = manager.status()
        return {
            "configured": bool(state.configured),
            "has_token": bool(state.has_token),
            "access_token_valid": bool(state.access_token_valid),
            "refresh_token_valid": bool(state.refresh_token_valid),
            "restart_required": bool(state.restart_required),
            "message": str(state.message),
            "api_base_url": settings.schwab_api_base_url,
            "workspace": WORKSPACE,
            "venv_python_ok": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {"configured": False, "message": f"status error: {exc}", "venv_python_ok": True}


# --------------------------------------------------------------------------- #
# Cached-bar fallback (data/cache/bars/<SYM>_2y.csv, oldest-first OHLCV)
# --------------------------------------------------------------------------- #

def _cached_bars(symbol: str) -> list[dict] | None:
    path = os.path.join(WORKSPACE, "data", "cache", "bars", f"{symbol.upper()}_2y.csv")
    if not os.path.exists(path):
        return None
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            try:
                rows.append({
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": float(r.get("volume") or 0.0),
                })
            except (KeyError, ValueError, TypeError):
                continue
    return rows or None


def _bars(symbol: str, providers, daily_request) -> tuple[list[dict], str]:
    """Return OHLCV dicts + provenance; fall back to cache on any failure."""
    _, _, quote_provider, md_provider, BarDataRequest = providers
    try:
        frame = md_provider.get_daily_bars(daily_request)
        rows = [
            {"open": float(r.open), "high": float(r.high), "low": float(r.low),
             "close": float(r.close), "volume": float(getattr(r, "volume", 0.0) or 0.0)}
            for r in frame.itertuples(index=False)
            if float(r.close) > 0
        ]
        if len(rows) >= 40:
            return rows, "schwab"
    except Exception:  # noqa: BLE001
        pass
    cached = _cached_bars(symbol)
    if cached:
        return cached, "cache"
    return [], "none"


def _quote(symbol: str, providers) -> tuple[dict | None, str]:
    _, _, quote_provider, _, _ = providers
    try:
        q = quote_provider.get_quote(symbol)
        return ({
            "symbol": getattr(q, "symbol", symbol.upper()),
            "last": getattr(q, "last", None),
            "change_pct": getattr(q, "change_pct", None),
            "bid": getattr(q, "bid", None),
            "ask": getattr(q, "ask", None),
            "volume": getattr(q, "volume", None),
            "realtime": bool(getattr(q, "realtime", False)),
            "asset_type": getattr(q, "asset_type", None),
        }, "schwab")
    except Exception:  # noqa: BLE001
        return None, "unavailable"


# --------------------------------------------------------------------------- #
# Technical studies (pure Python, no pandas) — the study maths in the workspace
# --------------------------------------------------------------------------- #

def _ema(vals: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out: list[float] = []
    prev: float | None = None
    for i, v in enumerate(vals):
        if prev is None:
            prev = v if i == 0 else (sum(vals[: i + 1]) / (i + 1))
        else:
            prev = prev + k * (v - prev)
        out.append(prev)
    return out


def _sma(vals: list[float], period: int) -> float | None:
    if len(vals) < period:
        return None
    return sum(vals[-period:]) / period


def _stdev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return statistics.pstdev(vals)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _macd(closes: list[float]) -> dict | None:
    if len(closes) < 35:
        return None
    e12 = _ema(closes, 12)
    e26 = _ema(closes, 26)
    macd = [a - b for a, b in zip(e12, e26)]
    signal = _ema(macd, 9)
    hist = macd[-1] - signal[-1]
    prev_hist = macd[-2] - signal[-2]
    return {"macd": macd[-1], "signal": signal[-1], "hist": hist,
            "hist_rising": hist > prev_hist}


def _atr(bars: list[dict], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    val = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        val = (val * (period - 1) + trs[i]) / period
    return val


def _anchored_vscore(bars: list[dict]) -> float | None:
    """Anchored VWAP + sigma position (VScore proxy): (price - AVWAP)/sigma."""
    window = bars[-60:]
    if len(window) < 10:
        window = bars
    tp = []; vol = []
    for b in window:
        v = b["volume"] or 0.0
        tp.append(((b["high"] + b["low"] + b["close"]) / 3.0) * v)
        vol.append(v)
    tv = sum(vol)
    if tv <= 0:
        return None
    avwap = sum(tp) / tv
    closes = [b["close"] for b in window]
    mean = statistics.fmean(closes)
    sd = _stdev(closes)
    if sd <= 0:
        return None
    z = (bars[-1]["close"] - avwap) / sd
    # map z in [-3, 3] to 0..100
    return 50.0 + max(-3.0, min(3.0, z)) * (50.0 / 3.0)


# --------------------------------------------------------------------------- #
# QX rules-engine factors (0..100 each) per the spec's weights
# --------------------------------------------------------------------------- #

def _factor_smc(bars: list[dict]) -> float:
    """Structure: recent swing-high/low breakout + higher-highs/higher-lows."""
    closes = [b["close"] for b in bars]
    if len(closes) < 40:
        return 50.0
    recent = closes[-21:-1]
    last = closes[-1]
    swing_high = max(b["high"] for b in bars[-21:-1])
    swing_low = min(b["low"] for b in bars[-21:-1])
    e20 = _ema(closes, 20)
    e50 = _ema(closes, 50)
    score = 50.0
    if last > swing_high:
        score += 25
    elif last < swing_low:
        score -= 25
    if len(recent) >= 5:
        if last > max(recent):
            score += 10
        if closes[-2] < closes[-1]:
            score += 8
    if e20[-1] > e50[-1]:
        score += 7
    else:
        score -= 7
    return max(0.0, min(100.0, score))


def _factor_phases(bars: list[dict]) -> float:
    """James Boyd 5-phase proxy: trend lifecycle from EMA slope + price position."""
    closes = [b["close"] for b in bars]
    if len(closes) < 50:
        return 50.0
    e20 = _ema(closes, 20)
    e50 = _ema(closes, 50)
    last = closes[-1]
    ema20_slope = e20[-1] - e20[-6] if len(e20) >= 6 else 0.0
    ema50_slope = e50[-1] - e50[-6] if len(e50) >= 6 else 0.0
    above20 = last > e20[-1]
    above50 = last > e50[-1]
    score = 50.0
    if ema50_slope > 0 and above50:          # P3 strong uptrend
        score += 30
    elif ema50_slope < 0 and not above50:    # P1 downtrend
        score -= 30
    if ema20_slope > 0 and above20:          # early reversal / momentum
        score += 12
    elif ema20_slope < 0 and not above20:
        score -= 12
    if ema20_slope == 0:
        score += 0
    return max(0.0, min(100.0, score))


def _factor_cvd(bars: list[dict]) -> float:
    """CVD proxy: cumulative delta z-score + absorption (wick/body) exhaustion."""
    if len(bars) < 20:
        return 50.0
    window = bars[-30:]
    deltas = []
    for b in window:
        sign = 1.0 if b["close"] >= b["open"] else -1.0
        deltas.append(sign * (b["volume"] or 0.0))
    cvd = []
    run = 0.0
    for d in deltas:
        run += d
        cvd.append(run)
    sd = _stdev(cvd) or 1.0
    z = cvd[-1] / sd if sd > 0 else 0.0
    # absorption: proportion of last bar that is wick (rejection)
    last = bars[-1]
    rng = last["high"] - last["low"]
    wick = 0.0 if rng <= 0 else (rng - abs(last["close"] - last["open"])) / rng
    score = 50.0 + max(-2.5, min(2.5, z)) * 12.0
    if wick > 0.6 and last["close"] >= last["open"]:
        score += 10   # bullish absorption (sellers absorbed)
    elif wick > 0.6 and last["close"] < last["open"]:
        score -= 10
    return max(0.0, min(100.0, score))


def _factor_vscore(bars: list[dict]) -> float:
    v = _anchored_vscore(bars)
    return 50.0 if v is None else v


def _factor_rs(bars: list[dict], spx_bars: list[dict]) -> float:
    """Relative strength percentile: 10d + 252d total return vs SPY proxy."""
    if len(bars) < 20 or len(spx_bars) < 20:
        return 50.0
    def rtn(bs, n):
        if len(bs) <= n or bs[-1 - n]["close"] == 0:
            return None
        return bs[-1]["close"] / bs[-1 - n]["close"] - 1.0
    score = 50.0
    for n in (10, 60, 252):
        r_sym = rtn(bars, n)
        r_spx = rtn(spx_bars, n)
        if r_sym is None or r_spx is None:
            continue
        edge = r_sym - r_spx
        score += max(-8.0, min(8.0, edge * 200.0))  # +2% relative -> +4pts
    return max(0.0, min(100.0, score))


def _factor_options_flow(quote: dict | None, bars: list[dict]) -> float:
    """Options-flow proxy (no chain in this seam) — neutral with a vol tilt."""
    if not bars:
        return 50.0
    closes = [b["close"] for b in bars[-30:]]
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]
    vol = _stdev(rets)
    # higher realized vol slightly favors aggressive (flow) setups; keep muted.
    tilt = max(-10.0, min(10.0, (vol - 0.01) * 400.0))
    return max(0.0, min(100.0, 50.0 + tilt))


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #

def _score_symbol(symbol: str, providers, spx_bars: list[dict]):
    bars, source = _bars(symbol, providers, providers[4](symbol=symbol, period="2y"))
    quote, quote_source = _quote(symbol, providers)
    if not bars:
        return {
            "symbol": symbol, "error": "no price data (live or cache)",
            "source": source, "score": None, "signal": "WAIT", "side": None,
        }
    factors = {
        "SMC": round(_factor_smc(bars), 1),
        "Phases": round(_factor_phases(bars), 1),
        "CVD_Absorption": round(_factor_cvd(bars), 1),
        "VScore": round(_factor_vscore(bars), 1),
        "RS_Rank": round(_factor_rs(bars, spx_bars), 1),
        "OptionsFlow": round(_factor_options_flow(quote, bars), 1),
    }
    score = round(
        0.25 * factors["SMC"]
        + 0.20 * factors["Phases"]
        + 0.20 * factors["CVD_Absorption"]
        + 0.15 * factors["VScore"]
        + 0.10 * factors["RS_Rank"]
        + 0.10 * factors["OptionsFlow"],
        1,
    )
    signal = "WAIT"; side = None
    if score >= 70:
        signal, side = "LONG / BUY CALL", "LONG"
    elif score <= 30:
        signal, side = "SHORT / BUY PUT", "SHORT"
    last = bars[-1]["close"]
    atr = _atr(bars)
    rsi = _rsi([b["close"] for b in bars])
    macd = _macd([b["close"] for b in bars])
    alerts: list[str] = []
    for name, f in factors.items():
        if f >= 70:
            alerts.append(f"{name} bullish ({f})")
        elif f <= 30:
            alerts.append(f"{name} bearish ({f})")
    if signal != "WAIT":
        alerts.append(f"QX_SCORE {signal} ({score})")
    return {
        "symbol": symbol,
        "source": source,
        "quote_source": quote_source,
        "last": last,
        "atr": round(atr, 4) if atr else None,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "macd_hist": round(macd["hist"], 4) if macd else None,
        "quote": quote,
        "factors": factors,
        "score": score,
        "signal": signal,
        "side": side,
        "alerts": alerts,
    }


def _do_scan(payload: dict) -> dict:
    symbols = payload.get("symbols") or ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META"]
    symbols = [str(s).upper() for s in symbols][:60]
    try:
        providers = _schwab_providers(_load_settings())
        spx_bars, spx_src = _bars("SPY", providers, providers[4](symbol="SPY", period="2y"))
    except Exception as exc:  # noqa: BLE001
        providers = None
        spx_bars = _cached_bars("SPY") or []
        spx_src = f"error:{exc}"

    results, errors = [], []
    for s in symbols:
        try:
            if providers is None:
                bars, _ = _cached_bars(s) or [], "cache"
                if not bars:
                    results.append({"symbol": s, "error": "no data", "score": None,
                                    "signal": "WAIT", "side": None})
                else:
                    results.append(_score_symbol(s, providers, spx_bars))
            else:
                results.append(_score_symbol(s, providers, spx_bars))
        except Exception as exc:  # noqa: BLE001
            results.append({"symbol": s, "error": str(exc), "score": None,
                            "signal": "WAIT", "side": None})

    actionable = [r for r in results if r.get("side")]
    return {
        "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "spxSource": spx_src,
        "symbols": len(results),
        "actionable": len(actionable),
        "results": results,
    }


def _arg_payload(argv: list[str], index: int = 1):
    """Payload from argv[index], else the entire stdin (robust to shell mangling)."""
    if len(argv) > index and argv[index] not in ("", "-"):
        return json.loads(argv[index])
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def main(argv: list[str]) -> int:
    try:
        cmd = argv[0] if argv else "status"
        if cmd == "status":
            print(json.dumps({"ok": True, "status": _status()}))
        elif cmd == "quotes":
            symbols = _arg_payload(argv)
            try:
                providers = _schwab_providers(_load_settings())
                out, errs = {}, []
                for s in symbols:
                    q, src = _quote(str(s).upper(), providers)
                    if q:
                        out[str(s).upper()] = q
                    else:
                        errs.append({"symbol": str(s).upper(), "error": src})
                print(json.dumps({"ok": True, "quotes": out, "errors": errs}))
            except Exception as exc:  # noqa: BLE001
                print(json.dumps({"ok": False, "error": str(exc)}))
        elif cmd == "auth_url":
            print(json.dumps(_auth_url()))
        elif cmd == "authorize":
            if len(argv) > 1 and argv[1] not in ("", "-"):
                value = argv[1]
            else:
                raw = sys.stdin.read().strip()
                try:
                    value = json.loads(raw) if raw else ""
                except Exception:
                    value = raw
            print(json.dumps(_authorize(value)))
        elif cmd == "scan":
            payload = _arg_payload(argv)
            scan = _do_scan(payload)
            print(json.dumps({"ok": True, "scan": scan}))
        else:
            print(json.dumps({"ok": False, "error": f"unknown command {cmd!r}"}))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"worker failure: {exc}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))