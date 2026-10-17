"""Market data + scan orchestration for the QX scanner (live Schwab with cache fallback)."""
from __future__ import annotations

import csv
import datetime as dt
import os
from datetime import datetime
from typing import Any

from qx.scanner.studies import (
    RULE_VERSION,
    SECTOR_ETFS,
    atr,
    macd,
    rsi,
    score_factors,
)

WORKSPACE_ROOT = os.environ.get("QX_WORKSPACE_ROOT", "").strip() or r"C:\Project\2026"

DEFAULT_WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "AMZN", "GOOGL"]


# --------------------------------------------------------------------------- #
# Data access (live Schwab, cache fallback)
# --------------------------------------------------------------------------- #

def _frame_to_rows(frame, interval: str, *, completed: bool) -> list[dict]:
    """Convert a timestamp-indexed OHLCV frame into rows that KEEP their time (F06)."""
    rows: list[dict] = []
    index = getattr(frame, "index", None)
    for position, (_, record) in enumerate(frame.iterrows()):
        close = float(record["close"])
        if close <= 0:
            continue
        stamp = index[position] if index is not None else None
        rows.append({
            "open": float(record["open"]), "high": float(record["high"]),
            "low": float(record["low"]), "close": close,
            "volume": float(record.get("volume") or 0.0),
            "date": stamp.isoformat() if hasattr(stamp, "isoformat") else (str(stamp) if stamp is not None else None),
            "bar_completed": bool(completed),
            "interval": interval,
        })
    return rows


def _cached_bars(symbol: str) -> list[dict] | None:
    """Cached daily bars. The CSV has no date column, so time is UNKNOWN (F06).

    These rows are explicitly marked so nothing downstream can mistake them for a
    dated observation.
    """
    path = os.path.join(WORKSPACE_ROOT, "data", "cache", "bars", f"{symbol.upper()}_2y.csv")
    if not os.path.exists(path):
        return None
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            try:
                rows.append({
                    "open": float(raw["open"]), "high": float(raw["high"]),
                    "low": float(raw["low"]), "close": float(raw["close"]),
                    "volume": float(raw.get("volume") or 0.0),
                    "date": None, "bar_completed": True, "interval": "1d",
                })
            except (KeyError, ValueError, TypeError):
                continue
    return rows or None


class MarketData:
    """Schwab market data with a cached fallback, built lazily and reused."""

    def __init__(self) -> None:
        self._providers: tuple | None = None
        self._bars_cache: dict[str, tuple[list[dict], str]] = {}
        self._quote_cache: dict[str, tuple[dict | None, str]] = {}
        self.quote_delay = 0.0

    def _providers_lazy(self) -> tuple | None:
        if self._providers is not None:
            return self._providers or None
        try:
            from qx.brokers.schwab.auth import SchwabTokenManager
            from qx.brokers.schwab.client import SchwabApiClient
            from qx.brokers.schwab.market_data import SchwabMarketDataProvider
            from qx.brokers.schwab.quotes import SchwabQuoteProvider
            from qx.config.settings import get_settings
            from qx.models.market import BarDataRequest, IntradayBarDataRequest

            settings = get_settings()
            client = SchwabApiClient(SchwabTokenManager(settings), base_url=settings.schwab_api_base_url)
            self._providers = (
                SchwabQuoteProvider(client),
                SchwabMarketDataProvider(client),
                BarDataRequest,
                IntradayBarDataRequest,
            )
        except Exception:  # noqa: BLE001 - cache-only mode is a valid state
            self._providers = ()
        return self._providers or None

    def bars(self, symbol: str, *, interval: str = "1d", use_cache: bool = False) -> tuple[list[dict], str]:
        """OHLCV bars WITH their market observation time.

        Reviewer F06: the provider returns a timestamp-indexed frame and the adapter
        previously discarded it via ``itertuples(index=False)``, so downstream code
        could not tell WHEN a bar was observed. Each row now carries ``date``
        (market observation time, ISO) plus ``bar_completed``, so "as of" can mean
        observation time instead of retrieval time.
        """
        key = f"{symbol.upper()}:{interval}"
        if key in self._bars_cache and not use_cache:
            return self._bars_cache[key]
        providers = self._providers_lazy()
        if providers:
            quote_provider, md_provider, bar_request, intraday_request = providers
            try:
                if interval == "1d":
                    frame = md_provider.get_daily_bars(bar_request(symbol=symbol.upper(), period="2y"))
                else:
                    minutes = int(interval.rstrip("m"))
                    frame = md_provider.get_intraday_bars(
                        intraday_request(symbol=symbol.upper(), interval_minutes=minutes,
                                         period="5d", include_extended_hours=False)
                    )
                rows = _frame_to_rows(frame, interval, completed=True)
                minimum = 40
                if len(rows) >= minimum:
                    self._bars_cache[key] = (rows, "schwab")
                    return rows, "schwab"
            except Exception:  # noqa: BLE001
                pass
        if interval == "1d":
            cached = _cached_bars(key.split(":")[0])
            if cached:
                self._bars_cache[key] = (cached, "cache")
                return cached, "cache"
        return [], "none"

    def quote(self, symbol: str) -> tuple[dict | None, str]:
        """Quote WITH observation time, so age can be verified (F06/F14)."""
        key = symbol.upper()
        if key in self._quote_cache:
            return self._quote_cache[key]
        providers = self._providers_lazy()
        result: tuple[dict | None, str] = (None, "unavailable")
        if providers:
            quote_provider = providers[0]
            try:
                quote = quote_provider.get_quote(key)
                stamp = getattr(quote, "timestamp", None) or getattr(quote, "trade_timestamp", None)
                result = ({
                    "symbol": getattr(quote, "symbol", key),
                    "last": getattr(quote, "last", None),
                    "change_pct": getattr(quote, "change_pct", None),
                    "bid": getattr(quote, "bid", None),
                    "ask": getattr(quote, "ask", None),
                    "volume": getattr(quote, "volume", None),
                    "realtime": bool(getattr(quote, "realtime", False)),
                    "timestamp": stamp.isoformat() if hasattr(stamp, "isoformat") else None,
                    "trade_timestamp": (getattr(quote, "trade_timestamp", None).isoformat()
                                        if hasattr(getattr(quote, "trade_timestamp", None), "isoformat")
                                        else None),
                }, "schwab")
            except Exception:  # noqa: BLE001
                result = (None, "unavailable")
        self._quote_cache[key] = result
        return result

    def quote_age_seconds(self, symbol: str, *, now: datetime | None = None) -> float | None:
        """Age of the quote's own market timestamp. None when time is unknown."""
        quote, _ = self.quote(symbol)
        stamp = (quote or {}).get("timestamp")
        if not stamp:
            return None
        try:
            observed = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=dt.timezone.utc)
        reference = now or datetime.now(dt.timezone.utc)
        return round((reference - observed).total_seconds(), 2)

    def freshness(self, symbol: str, *, mode: str = "swing") -> dict:
        """Classify quote freshness using the repository's existing checker.

        Reuses ``qx.signals.freshness.FreshnessChecker`` rather than inventing
        thresholds, so the freshness vocabulary is the repo's own.
        """
        from qx.signals.freshness import FreshnessChecker, FreshnessStatus

        quote, source = self.quote(symbol)
        stamp = (quote or {}).get("timestamp")
        if not stamp:
            return {"symbol": symbol.upper(), "status": "UNKNOWN", "is_executable": False,
                    "age_seconds": None, "reason": "quote carries no observation time",
                    "source": source, "provider_realtime": bool((quote or {}).get("realtime"))}
        try:
            observed = datetime.fromisoformat(stamp)
        except ValueError:
            return {"symbol": symbol.upper(), "status": "UNKNOWN", "is_executable": False,
                    "age_seconds": None, "reason": "unparseable quote time", "source": source,
                    "provider_realtime": bool((quote or {}).get("realtime"))}
        result = FreshnessChecker().check_freshness(symbol.upper(), observed, mode=mode)
        return {"symbol": symbol.upper(), "status": result.status.value,
                "is_executable": result.is_executable, "age_seconds": result.quote_age_seconds,
                "max_threshold_seconds": result.max_threshold_seconds,
                "reason": result.reason, "source": source,
                "provider_realtime": bool((quote or {}).get("realtime")),
                "observed_at": stamp}


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #

def scan_symbol(symbol: str, market: MarketData, benchmark_bars: list[dict],
                interval: str = "1d") -> dict[str, Any]:
    bars, source = market.bars(symbol, interval=interval)
    quote, quote_source = market.quote(symbol)
    if not bars:
        return {"symbol": symbol.upper(), "error": "no price data (live or cache)",
                "source": source, "score": None, "signal": "WAIT", "side": None}
    scored = score_factors(bars, benchmark_bars, quote)
    last = bars[-1]["close"]
    atr_value = atr(bars)
    rsi_value = rsi([bar["close"] for bar in bars])
    macd_value = macd([bar["close"] for bar in bars])
    invalidation = round(last - 1.5 * atr_value, 4) if atr_value and scored["side"] == "LONG" else (
        round(last + 1.5 * atr_value, 4) if atr_value and scored["side"] == "SHORT" else None)
    target = None
    risk_reward = None
    if invalidation is not None and atr_value:
        reward = abs(last - invalidation) * TARGET_R
        target = round(last + reward if scored["side"] == "LONG" else last - reward, 4)
        risk_reward = TARGET_R
    return {
        "symbol": symbol.upper(),
        "source": source,
        "quote_source": quote_source,
        "last": last,
        "quote": quote,
        "atr": round(atr_value, 4) if atr_value else None,
        "rsi": round(rsi_value, 1) if rsi_value is not None else None,
        "macd_hist": round(macd_value["hist"], 4) if macd_value else None,
        "entry": last,
        "invalidation": invalidation,
        "target": target,
        "risk_reward": risk_reward,
        "reward_risk_basis": (REWARD_RISK_BASIS if risk_reward is not None else None),
        "reward_risk_note": (REWARD_RISK_NOTE if risk_reward is not None else None),
        **_side_status(scored.get("side")),
        **scored,
    }


# --------------------------------------------------------------------------- #
# PLANNED R:R IS A CONFIGURED CONSTANT, NOT A MEASUREMENT.
#
# The target is placed at a fixed ATR multiple, so this ratio is the same for
# every symbol, every side, every timeframe: arithmetic identity, not evidence.
# Measured over a 2-year backtest across 400 symbols, the REALISED long-side
# result was +0.41 R per trade (PF 1.37), median -0.59 R, with only 40.6% of
# trades profitable. Showing a configured ratio beside a live plan reads as an
# expected payoff, which it is not.
# --------------------------------------------------------------------------- #

TARGET_R = 1.8
REWARD_RISK_BASIS = "CONFIGURED_TARGET"
REWARD_RISK_NOTE = (
    "Planned R:R is the configured target multiple, not a measured outcome. The "
    "target sits at a fixed ATR multiple, so this ratio is identical for every "
    "setup. Realised performance over a 2-year backtest was +0.41 R per trade on "
    "the long side (profit factor 1.37), with 40.6% of trades profitable."
)


# --------------------------------------------------------------------------- #
# SHORT-SIDE EXPECTANCY.
#
# The short conditions in master_auto are line-for-line symmetric with the long
# ones, so the negative result below is not an implementation defect. A 2-year
# backtest over 400 symbols / 945 short trades put the short side at -0.60 R per
# trade (PF 0.53) against +0.41 R for the long side (PF 1.37) on the same bars.
#
# A mirror test isolates the cause: negating every long trade's return gives
# -0.41 R, so actual shorts underperform a pure mirror by 0.19 R. That gap is
# market drift, not signal quality (equal-weight drift was +38%, 68% of symbols up).
#
# A regime gate ("short only while the market is below its 50-day mean") was
# TESTED AND REJECTED: it made shorts worse (-0.87 R, PF 0.39) and helped in only
# 1 of 4 folds, because a breached moving average is a LAGGING signal that selects
# the moment a bounce is most likely. Six of seven market-position buckets were
# negative; the best was +0.01 R.
#
# Retained because a sustained bear market could invert this, but marked unproven
# so no surface presents shorts as a peer of the long signals.
# --------------------------------------------------------------------------- #

SHORT_SIDE_STATUS = "UNPROVEN"
SHORT_SIDE_BASIS = "NEGATIVE_EXPECTANCY_MEASURED"
SHORT_SIDE_NOTE = (
    "Short signals are shown for completeness but are NOT validated. Over a 2-year "
    "backtest they returned -0.60 R per trade (profit factor 0.53) while the long "
    "side returned +0.41 R (1.37). The logic is symmetric with the long side, so "
    "this is market drift rather than a bug: a regime gate that allowed shorts only "
    "in falling markets was tested and made results worse. Treat bearish rows as "
    "informational, not as tradeable setups."
)


def _side_status(side: str | None) -> dict[str, Any]:
    """Direction-validation labels, so no consumer has to infer them."""
    if side == "SHORT":
        return {"side_status": SHORT_SIDE_STATUS, "side_basis": SHORT_SIDE_BASIS,
                "side_note": SHORT_SIDE_NOTE}
    if side == "LONG":
        return {"side_status": "MEASURED", "side_basis": None, "side_note": None}
    return {"side_status": None, "side_basis": None, "side_note": None}


def scan_universe(symbols: list[str] | None = None, benchmark: str = "SPY",
                  timeframe: str = "1d") -> dict[str, Any]:
    market = MarketData()
    watch = [s.upper() for s in (symbols or DEFAULT_WATCHLIST)][:60]
    interval = "15m" if str(timeframe).lower() in {"15m", "15", "intraday"} else "1d"
    benchmark_bars, benchmark_source = market.bars(benchmark, interval=interval)
    results = [scan_symbol(symbol, market, benchmark_bars, interval) for symbol in watch]
    actionable = [row for row in results if row.get("side")]
    error_count = sum(1 for row in results if row.get("error"))
    if not actionable:
        verdict = "NO_QUALIFIED_TRADE"
    else:
        verdict = "QUALIFIED"
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rule_version": RULE_VERSION,
        "timeframe": interval,
        "benchmark": benchmark,
        "benchmark_source": benchmark_source,
        "symbols": len(results),
        "actionable": len(actionable),
        "errors": error_count,
        "verdict": verdict,
        "results": results,
    }


def sector_rankings() -> dict[str, Any]:
    """Rank all 11 declared sector ETFs by relative strength versus SPY."""
    market = MarketData()
    benchmark_bars, benchmark_source = market.bars("SPY")
    rows: list[dict[str, Any]] = []

    def ret(bars: list[dict], periods: int) -> float | None:
        if len(bars) <= periods or bars[-1 - periods]["close"] == 0:
            return None
        return bars[-1]["close"] / bars[-1 - periods]["close"] - 1.0

    for symbol, name in SECTOR_ETFS:
        bars, source = market.bars(symbol)
        if not bars:
            rows.append({"symbol": symbol, "sector": name, "coverage": "UNAVAILABLE",
                         "rs_5d": None, "rs_20d": None, "rs_60d": None, "quadrant": "UNKNOWN"})
            continue
        quote, _ = market.quote(symbol)
        rs = {}
        for label, periods in (("rs_5d", 5), ("rs_20d", 20), ("rs_60d", 60)):
            own, bench = ret(bars, periods), ret(benchmark_bars, periods)
            rs[label] = round((own - bench) * 100.0, 2) if own is not None and bench is not None else None
        quadrant = "UNKNOWN"
        if rs["rs_20d"] is not None and rs["rs_60d"] is not None:
            if rs["rs_20d"] > 0 and rs["rs_60d"] > 0:
                quadrant = "LEADING"
            elif rs["rs_20d"] > 0 >= rs["rs_60d"]:
                quadrant = "IMPROVING"
            elif rs["rs_20d"] <= 0 < rs["rs_60d"]:
                quadrant = "WEAKENING"
            else:
                quadrant = "LAGGING"
        rows.append({
            "symbol": symbol, "sector": name, "coverage": "R1000 declared",
            "source": source, "last": bars[-1]["close"], "change_pct": (quote or {}).get("change_pct"),
            "quadrant": quadrant, **rs,
            "score": round((rs["rs_20d"] or 0.0) + (rs["rs_60d"] or 0.0), 2),
        })
    ranked = sorted([r for r in rows if r.get("score") is not None], key=lambda r: r["score"], reverse=True)
    ranked += [r for r in rows if r.get("score") is None]
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "declared": len(SECTOR_ETFS),
        "ranked": len([r for r in ranked if r.get("score") is not None]),
        "benchmark_source": benchmark_source,
        "sectors": ranked,
    }


def market_context() -> dict[str, Any]:
    """Broad-market context and data freshness for the scanner header."""
    market = MarketData()
    out: dict[str, Any] = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "proxies": []}
    for symbol, label in (("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("IWM", "Russell 2000")):
        bars, source = market.bars(symbol)
        quote, quote_source = market.quote(symbol)
        change = (quote or {}).get("change_pct")
        if change is None and len(bars) >= 2 and bars[-2]["close"]:
            change = bars[-1]["close"] / bars[-2]["close"] - 1.0
        out["proxies"].append({
            "symbol": symbol, "label": label,
            "last": (quote or {}).get("last") or (bars[-1]["close"] if bars else None),
            "change_pct": change, "source": source, "quote_source": quote_source,
            "realtime": bool((quote or {}).get("realtime")),
        })
    changes = [p["change_pct"] for p in out["proxies"] if p["change_pct"] is not None]
    average = sum(changes) / len(changes) if changes else None
    out["average_change_pct"] = average
    out["regime"] = (
        "RISK-ON" if average is not None and average > 0.002 else
        "RISK-OFF" if average is not None and average < -0.002 else "NEUTRAL"
    )
    out["freshness"] = "FRESH" if any(p["quote_source"] == "schwab" for p in out["proxies"]) else "CACHE-ONLY"
    return out
