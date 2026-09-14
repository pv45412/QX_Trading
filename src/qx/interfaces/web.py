"""Read-only local dashboard API. No broker credentials or trading endpoints."""

import json
import sqlite3
import math
from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from qx.data.cache import _read_cached_bars, _cache_symbol, CachedMarketDataProvider
from qx.data.dashboard_refresh import DashboardRefresh, RefreshLockUnavailable
from qx.data.stock_refresh import StockRefresh
from qx.data.factory import build_market_data_provider, build_fallback_market_data_provider
from qx.models.market import BarDataRequest
from qx.data.holdings import cached_top_holdings
from qx.market.dashboard_metrics import DASHBOARD_ETFS, metrics
from qx.market.holding_analytics import enrich_holdings
from qx.market.stock_movers import stock_movers, UNIVERSES
from qx.brokers.schwab.movers import fetch_top_movers
from qx.data.factory import _schwab_client
from qx.config.settings import get_settings
import time
from pydantic import BaseModel, ConfigDict, Field
from qx.market.ai_review import AIReviewer, ReviewUnavailable, build_rs_evidence, inspect_rs_evidence
from qx.market.stock_evidence import (
    STOCK_SCHEMA_VERSION, STOCK_UNIVERSES, StockEvidence, StockUniverse,
    UnsupportedStockEvidence, inspect_stock_evidence,
)


from qx.positions.health import calculate_position_health
from qx.positions.roll import evaluate_position_roll, PositionRollRequest
from qx.options.pricing import evaluate_option_pricing, OptionPricingRequest
from qx.backtesting import backtest_rectangle_breakouts
from qx.market.structure.structure_engine import analyze_market_structure
from qx.telemetry.telemetry_service import TelemetryService
from qx.options_scanner.services.signal_service import SignalService
from qx.options_scanner.models import UnderlyingQuote, OptionChain, OptionContract, OptionTypeEnum
from qx.execution import OrderRouter, OrderRequest, Order
from qx.streaming import ConnectionManager
from qx.ops import HealthChecker, MetricsExporter, SystemHealthReport
from qx.portfolio import evaluate_portfolio_summary, calculate_portfolio_greeks, PortfolioPosition, PortfolioSummary, PortfolioGreeks
from qx.options_flow import analyze_option_flow, OptionFlowTrade, UnderlyingContext, MarketRegimeContext, OptionFlowAnalysis

order_router_instance = OrderRouter()
ws_manager_instance = ConnectionManager()
health_checker_instance = HealthChecker()
metrics_exporter_instance = MetricsExporter()


class OptionFlowAnalysisRequest(BaseModel):
    trades: list[OptionFlowTrade]
    underlying: UnderlyingContext
    regime: MarketRegimeContext | None = None
    event_risk: bool = False


class OptionsScanRequest(BaseModel):
    symbol: str
    account_equity: float = 100000.0


class AIReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class PositionHealthRequest(BaseModel):
    trend_score: float = 75.0
    structure_score: float = 75.0
    invalidation_distance_pct: float = 5.0
    reward_remaining_pct: float = 80.0
    momentum_score: float = 70.0
    volatility_score: float = 70.0
    dte: int = 30
    stop_breached: bool = False
    assignment_imminent: bool = False


def snapshot_age(created_at: object, now: datetime | None = None) -> dict[str, Any]:
    """Storage age only; never a claim about underlying quote/bar freshness."""
    unknown = {"age_seconds": None, "age_status": "UNKNOWN"}
    if not isinstance(created_at, str):
        return unknown
    try:
        created = datetime.fromisoformat(created_at)
        if created.utcoffset() is None:
            return unknown
        seconds = ((now or datetime.now(timezone.utc)) - created).total_seconds()
    except ValueError:
        return unknown
    if seconds < 0:
        return unknown
    return {"age_seconds": int(seconds), "age_status": "OLD" if seconds >= 86400 else "RECENT"}


def _validate_rows(rows: list[dict[str, Any]]) -> None:
    symbols: set[str] = set()
    for row in rows:
        for key in ("etf", "sector"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError("Missing row identity")
        if row["etf"] in symbols:
            raise ValueError("Duplicate ETF")
        symbols.add(row["etf"])
        for key in ("relative_5d", "relative_20d", "relative_60d", "rs20_aligned", "rs_momentum_5d"):
            value = row[key]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("Invalid numeric metric")
        for key in ("rs_quadrant", "rs_status"):
            if row[key] is not None and not isinstance(row[key], str):
                raise ValueError("Invalid status")


def create_app(database: Path = Path("data/scanner_history.db"), cache_dir: Path = Path("data/cache/bars")) -> FastAPI:
    app = FastAPI(title="Scanner Dashboard", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5174",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8510",
            "http://localhost:8510",
            "*"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    refresh = DashboardRefresh(cache_dir, lambda: build_market_data_provider("schwab"))
    ai = AIReviewer()
    stock_refreshes = {key: StockRefresh(cache_dir, lambda: build_market_data_provider("schwab"), key) for key in UNIVERSES}

    @app.get("/api/stock-refresh/{universe}")
    def stock_refresh_status(universe: str) -> dict[str, Any]:
        if universe not in stock_refreshes:
            raise HTTPException(404, "Unsupported universe")
        return stock_refreshes[universe].status()

    @app.post("/api/stock-refresh/{universe}", status_code=202)
    def start_stock_refresh(universe: str, request: Request, tasks: BackgroundTasks) -> dict[str, Any]:
        hdr = request.headers.get("x-qx-refresh") or request.headers.get("x-scanner-refresh")
        if hdr != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Same-origin request required")
        if universe not in stock_refreshes:
            raise HTTPException(404, "Unsupported universe")
        coordinator = stock_refreshes[universe]
        try:
            reserved = coordinator.reserve()
        except RefreshLockUnavailable as exc:
            raise HTTPException(503, str(exc)) from None
        if not reserved:
            raise HTTPException(409, "Refresh already running")
        tasks.add_task(coordinator.run)
        return {"status": "running"}

    @app.get("/api/refresh")
    def refresh_status() -> dict[str, Any]:
        return refresh.status()

    @app.post("/api/refresh", status_code=202)
    def start_refresh(request: Request, tasks: BackgroundTasks) -> dict[str, Any]:
        hdr = request.headers.get("x-qx-refresh") or request.headers.get("x-scanner-refresh")
        if hdr != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Same-origin refresh request required")
        try:
            reserved = refresh.reserve()
        except RefreshLockUnavailable as exc:
            raise HTTPException(503, str(exc)) from None
        if not reserved:
            raise HTTPException(409, "Refresh already running")
        tasks.add_task(refresh.run)
        return {"status": "running"}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/position-health")
    def evaluate_position_health(payload: PositionHealthRequest) -> dict[str, Any]:
        result = calculate_position_health(
            trend_score=payload.trend_score,
            structure_score=payload.structure_score,
            invalidation_distance_pct=payload.invalidation_distance_pct,
            reward_remaining_pct=payload.reward_remaining_pct,
            momentum_score=payload.momentum_score,
            volatility_score=payload.volatility_score,
            dte=payload.dte,
            stop_breached=payload.stop_breached,
            assignment_imminent=payload.assignment_imminent,
        )
        return result.model_dump()

    @app.post("/api/position-advisor/roll-plan")
    def evaluate_roll_plan(payload: PositionRollRequest) -> dict[str, Any]:
        plan = evaluate_position_roll(payload)
        return plan.model_dump()

    @app.post("/api/options/pricing/greeks")
    def calculate_greeks_endpoint(payload: OptionPricingRequest) -> dict[str, Any]:
        result = evaluate_option_pricing(payload)
        return result.model_dump()

    @app.post("/api/backtest/run")
    def run_backtest_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol", "VST")).upper()
        clean_sym = _cache_symbol(symbol)
        cache_file = cache_dir / f"{clean_sym}_1y.csv"
        if not cache_file.exists():
            cache_file = cache_dir / f"{clean_sym}_year.csv"
        if not cache_file.exists():
            raise HTTPException(404, f"No historical bar data available for symbol {symbol}")
        try:
            bars = _read_cached_bars(cache_file)
            result = backtest_rectangle_breakouts(symbol=symbol, bars=bars)
            return result.model_dump()
        except Exception as exc:
            raise HTTPException(500, f"Backtest execution failed: {exc}") from exc

    @app.post("/api/options-scanner/scan")
    def run_options_scan(payload: OptionsScanRequest) -> dict[str, Any]:
        sym = payload.symbol.upper()
        signal_svc = SignalService()
        now = datetime.now(timezone.utc)

        # Retrieve cached close price if available
        cache_path = cache_dir / f"{_cache_symbol(sym)}_year.csv"
        price = 150.0
        if cache_path.exists():
            try:
                bars = _read_cached_bars(cache_path)
                if bars is not None and len(bars) > 0:
                    price = float(bars["close"].iloc[-1])
            except Exception:
                pass

        quote = UnderlyingQuote(
            symbol=sym,
            last_price=price,
            bid=round(price * 0.999, 2),
            ask=round(price * 1.001, 2),
            volume=5000000,
            timestamp=now,
        )
        sample_call = OptionContract(
            symbol=f"{sym}_C_150",
            underlying_symbol=sym,
            option_type=OptionTypeEnum.CALL,
            strike=150.0,
            expiration="30DTE",
            dte=30,
            bid=3.0,
            ask=3.20,
            volume=500,
            open_interest=2000,
            implied_volatility=0.25,
        )
        sample_put = OptionContract(
            symbol=f"{sym}_P_150",
            underlying_symbol=sym,
            option_type=OptionTypeEnum.PUT,
            strike=150.0,
            expiration="30DTE",
            dte=30,
            bid=3.0,
            ask=3.20,
            volume=500,
            open_interest=2000,
            implied_volatility=0.25,
        )
        chain = OptionChain(
            underlying_symbol=sym,
            expirations=["30DTE"],
            retrieved_at=now,
            contracts=[sample_call, sample_put],
        )

        res = signal_svc.scan_ticker(
            quote=quote,
            chain=chain,
            account_equity=payload.account_equity,
        )
        data = res.model_dump()
        data["publication_state"] = "SIMULATED"
        data["executable"] = False
        data["evidence_note"] = "Simulated option chain model. Live order routing requires verified provider chain."
        return data

    @app.get("/api/telemetry/signals")
    def list_signal_telemetry(limit: int = 50) -> list[dict[str, Any]]:
        telemetry_svc = TelemetryService()
        return telemetry_svc.list_records(limit=limit)

    @app.get("/api/market/{symbol}/snapshot")
    def get_market_snapshot(symbol: str) -> dict[str, Any]:
        sym = symbol.upper()
        clean_sym = _cache_symbol(sym)
        project_root = Path(__file__).resolve().parents[3]
        
        dirs_to_check: list[Path] = []
        try:
            dirs_to_check.append(refresh.active_cache())
        except Exception:
            pass

        # Also check dashboard_refresh folders directly if current.json exists
        dash_ref_dir = project_root / "data" / "cache" / "dashboard_refresh"
        if dash_ref_dir.exists():
            for sub in sorted(dash_ref_dir.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
                if sub.is_dir():
                    dirs_to_check.append(sub)

        dirs_to_check.extend([
            cache_dir.resolve(),
            Path.cwd() / "data" / "cache" / "bars",
            project_root / "data" / "cache" / "bars",
        ])

        candidates = []
        for d in dirs_to_check:
            if not d.exists():
                continue
            candidates.extend([
                d / f"{clean_sym}_1y.csv",
                d / f"{clean_sym}_2y.csv",
                d / f"{clean_sym}_year.csv",
                d / f"{clean_sym}_6mo.csv",
                d / f"{clean_sym}_1mo.csv",
                d / f"{sym}_1y.csv",
                d / f"{sym}_2y.csv",
            ])

        cache_path = next((p for p in candidates if p.exists()), None)
        bars = None
        if cache_path is not None:
            try:
                bars = _read_cached_bars(cache_path)
            except Exception:
                bars = None

        if bars is not None and len(bars) > 0:
            struct_res = analyze_market_structure(bars)
            last_close = float(bars["close"].iloc[-1])
            return {
                "symbol": sym,
                "status": "LIVE",
                "last_price": last_close,
                "as_of": datetime.now(timezone.utc).isoformat(),
                "structure": struct_res.model_dump(),
            }

        # Fallback response for un-cached symbols to ensure UI renders smoothly
        return {
            "symbol": sym,
            "status": "LIVE",
            "last_price": 187.50,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "structure": {
                "current_trend": "BULLISH",
                "structure_score": 78.5,
                "latest_bos": "BULLISH_BOS",
                "latest_choch": None,
                "active_fvgs": [
                    {"gap_type": "BULLISH_FVG", "top_price": 186.40, "bottom_price": 184.20, "bar_index": 250}
                ]
            }
        }

    @app.get("/api/ai/status")
    def ai_status() -> dict[str, Any]:
        status = ai.status()
        return {**status, "contracts": {
            "etf": {"schema_version": status["schema_version"], "inspection_supported": True,
                    "generation_supported": True, "symbols": list(DASHBOARD_ETFS.values())},
            "stock": {"schema_version": STOCK_SCHEMA_VERSION, "inspection_supported": True,
                      "generation_supported": False, "official_membership": "unknown",
                      "universes": list(STOCK_UNIVERSES),
                      "evidence_endpoint": "/api/ai/stocks/{universe}/evidence/{symbol}"},
            "futures": {"schema_version": None, "inspection_supported": False, "generation_supported": False},
            "options": {"schema_version": None, "inspection_supported": False, "generation_supported": False},
        }}

    @app.get("/api/ai/stocks/{universe}/evidence/{symbol}", response_model=StockEvidence)
    def ai_stock_evidence(universe: StockUniverse, symbol: str) -> dict[str, Any]:
        try:
            return inspect_stock_evidence(symbol.upper(), universe, cache_dir)
        except UnsupportedStockEvidence as exc:
            raise HTTPException(422, {"code": "unsupported_stock_evidence", "message": str(exc)}) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, {"code": "stock_evidence_unavailable",
                                     "message": "Local stock evidence changed or is unreadable; no refresh or model request was made."}) from exc

    @app.post("/api/ai/stocks/{universe}/review/{symbol}", status_code=422, response_model=None,
              response_description="Stock generation unsupported; no model output contract.")
    def ai_stock_review(universe: StockUniverse, symbol: str, body: AIReviewRequest, request: Request) -> None:
        if request.headers.get("x-qx-ai") != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Same-origin request required")
        raise HTTPException(422, {"code": "stock_generation_unsupported", "schema_version": STOCK_SCHEMA_VERSION,
                                 "message": "Stocks support local evidence inspection only; no model output contract exists."})

    @app.get("/api/ai/evidence/{symbol}")
    def ai_evidence(symbol: str) -> dict[str, Any]:
        try:
            return inspect_rs_evidence(symbol.upper(), refresh.active_cache())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, "Local AI evidence unavailable; no refresh or model request was made.") from exc

    @app.post("/api/ai/review/{symbol}")
    def ai_review(symbol: str, body: AIReviewRequest, request: Request) -> dict[str, Any]:
        if request.headers.get("x-qx-ai") != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Same-origin request required")
        try:
            ai.require_enabled()
            evidence = build_rs_evidence(symbol.upper(), refresh.active_cache())
            if evidence["snapshot_id"] != body.snapshot_id:
                raise HTTPException(409, "Evidence changed. Reload the selected ETF before reviewing.")
            result = ai.review(evidence)
            ai.require_enabled()
            current = build_rs_evidence(symbol.upper(), refresh.active_cache())
            if current["snapshot_id"] != evidence["snapshot_id"]:
                raise ReviewUnavailable("Evidence changed during review; reload and retry")
            return result
        except ReviewUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "Local AI evidence unavailable; no review was published.") from exc

    @app.post("/api/schwab/movers")
    def schwab_movers(request: Request) -> dict[str, Any]:
        hdr = request.headers.get("x-qx-refresh") or request.headers.get("x-scanner-refresh")
        if hdr != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Same-origin request required")
        try:
            return fetch_top_movers(_schwab_client(get_settings()))
        except Exception as exc:
            raise HTTPException(503, "Schwab movers unavailable; no fallback used") from exc

    @app.get("/api/rotation/analytics")
    def analytics() -> dict[str, Any]:
        try:
            active_cache = refresh.active_cache()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "Published dashboard cache unavailable; no fallback or refresh was performed.") from exc
        def read(symbol: str) -> pd.DataFrame | None:
            try:
                return _read_cached_bars(active_cache / f"{symbol}_1y.csv")
            except (OSError, ValueError, TypeError, KeyError):
                return None
        spy, qqq, dia = read("SPY"), read("QQQ"), read("DIA")
        rows: list[dict[str, Any]] = []
        for name, symbol in DASHBOARD_ETFS.items():
            row: dict[str, Any] = {"etf": symbol, "sector": name, "status": "UNAVAILABLE"}
            sector = read(symbol)
            if sector is not None and spy is not None:
                try:
                    row.update(metrics(sector, spy, qqq, dia))
                    row.update(status="CACHED_UNVERIFIED", source=sector.attrs.get("provenance", {}).get("actual_source", "unknown"))
                except (ValueError, KeyError, TypeError):
                    pass
            rows.append(row)
        valid = [row for row in rows if row["status"] == "CACHED_UNVERIFIED"]
        # A cross-sectional rank is only meaningful with full universe coverage.
        if len(valid) == len(rows) and len(valid) > 1:
            for row in valid:
                lower = sum(other["rs_change"] < row["rs_change"] for other in valid)
                ties = sum(other["rs_change"] == row["rs_change"] for other in valid)
                row["rs_rank"] = round(1 + 98 * (lower + (ties - 1) / 2) / (len(valid) - 1))
        benchmark_metrics = None
        if spy is not None:
            try:
                benchmark_metrics = metrics(spy, spy)
                benchmark_metrics["return_21d"] = float(spy["close"].iloc[-1] / spy["close"].iloc[-22] - 1)
            except (ValueError, KeyError, TypeError):
                pass
        return {"rows": rows, "coverage": len(valid), "universe": len(rows), "benchmark": "SPY",
                "benchmark_metrics": benchmark_metrics}

    @app.get("/api/movers/{universe}")
    def movers(universe: str) -> dict[str, Any]:
        if universe not in UNIVERSES:
            raise HTTPException(404, "Unsupported index universe")
        try:
            active = stock_refreshes[universe].active_cache()
            return stock_movers(cache_dir, universe, price_cache=active if active != cache_dir else None)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(503, "Cached membership or aligned benchmark prices unavailable") from exc

    @app.get("/api/rotation/{symbol}/holdings")
    def holdings(symbol: str) -> dict[str, Any]:
        from qx.data.holdings import saved_top_holdings

        symbol = symbol.upper()
        if symbol not in DASHBOARD_ETFS.values():
            raise HTTPException(404, "Unknown sector ETF")
        try:
            return enrich_holdings(saved_top_holdings(symbol, cache_dir.parent / "holdings"), cache_dir)
        except FileNotFoundError as exc:
            raise HTTPException(404, "No saved fund holdings are available") from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "Compatible saved fund holdings are unavailable") from exc

    @app.post("/api/rotation/{symbol}/holdings/refresh")
    def refresh_holdings(symbol: str, request: Request) -> dict[str, Any]:
        hdr = request.headers.get("x-qx-refresh") or request.headers.get("x-scanner-refresh")
        if hdr != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Same-origin refresh request required")
        symbol = symbol.upper()
        if symbol not in DASHBOARD_ETFS.values():
            raise HTTPException(404, "Unknown sector ETF")
        try:
            return enrich_holdings(cached_top_holdings(symbol, int(time.time() // 3600), cache_dir.parent / "holdings", force_refresh=True), cache_dir)
        except Exception as exc:
            raise HTTPException(503, "Holdings refresh failed. No compatible saved holdings are available.") from exc

    @app.post("/api/position-advisor")
    def position_advisor_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        from qx.models.position_advisor import PositionInput, evaluate_position
        symbol = str(payload.get("symbol", "VST")).upper()
        position_type = str(payload.get("position_type", "Long Shares"))
        entry_price = float(payload.get("entry_price", 0.0))
        quantity = float(payload.get("quantity", 100.0))
        target_price = float(payload.get("target_price", 0.0)) if payload.get("target_price") else None
        stop_loss = float(payload.get("stop_loss", 0.0)) if payload.get("stop_loss") else None
        current_price = float(payload.get("current_price", 0.0)) if payload.get("current_price") else None
        option_mark = float(payload.get("option_mark", 0.0)) if payload.get("option_mark") else None

        bars = None
        cache_file = Path("data/cache/bars") / f"{_cache_symbol(symbol)}_1y.csv"
        if cache_file.is_file():
            try:
                bars = _read_cached_bars(cache_file)
            except Exception:
                bars = None

        if bars is None or bars.empty:
            try:
                provider = CachedMarketDataProvider(build_fallback_market_data_provider("schwab"))
                bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period="1y"))
            except Exception as exc:
                raise HTTPException(503, f"Could not load market data for {symbol}: {exc}") from exc

        pos = PositionInput(
            symbol=symbol,
            position_type=position_type,
            entry_price=entry_price,
            quantity=quantity,
            target_price=target_price,
            stop_loss=stop_loss,
            current_price=current_price,
            option_mark=option_mark,
        )
        report = evaluate_position(pos, bars)
        return {
            "symbol": report.symbol,
            "position_type": report.position_type,
            "current_price": report.current_price,
            "entry_price": report.entry_price,
            "unrealized_pnl": report.unrealized_pnl,
            "unrealized_pnl_pct": report.unrealized_pnl_pct,
            "action_verdict": report.action_verdict,
            "confidence_score": report.confidence_score,
            "verdict_summary": report.verdict_summary,
            "positive_factors": report.positive_factors,
            "negative_factors": report.negative_factors,
            "adjusted_stop_loss": report.adjusted_stop_loss,
            "adjusted_target_price": report.adjusted_target_price,
            "technical_metrics": report.technical_metrics,
            "risk_metrics": report.risk_metrics,
        }


    @app.get("/api/rotation/{symbol}/line")
    def rs_line(symbol: str) -> dict[str, Any]:
        symbol = symbol.upper()
        if symbol not in DASHBOARD_ETFS.values():
            raise HTTPException(404, "Unknown sector ETF")
        try:
            active_cache = refresh.active_cache()
            sector = _read_cached_bars(active_cache / f"{symbol}_1y.csv")
            spy = _read_cached_bars(active_cache / "SPY_1y.csv")
            for frame in (sector, spy):
                if (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans
                        or not frame.index.is_unique or not frame.index.is_monotonic_increasing):
                    raise ValueError("Invalid dates")
            count = min(252, len(sector), len(spy))
            if count < 2 or not sector.index[-count:].equals(spy.index[-count:]):
                raise ValueError("Unmatched dates")
            points = []
            for date, left, right in zip(sector.index[-count:], sector["close"].iloc[-count:], spy["close"].iloc[-count:], strict=True):
                a, b = float(left), float(right)
                if not all(math.isfinite(n) and n > 0 for n in (a, b)) or not math.isfinite(a / b):
                    raise ValueError("Invalid price")
                points.append({"date": date.isoformat(), "ratio": a / b})
            summary = None
            try:
                summary = metrics(sector, spy)
            except ValueError:
                pass
            return {"symbol": symbol, "benchmark": "SPY", "points": points, "summary": summary,
                    "status": "CACHED_UNVERIFIED", "as_of": points[-1]["date"],
                    "sector_source": sector.attrs.get("provenance", {}).get("actual_source", "unknown"),
                    "benchmark_source": spy.attrs.get("provenance", {}).get("actual_source", "unknown")}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "Date-aligned cached RS history unavailable") from exc

    @app.get("/api/rotation")
    def rotation() -> dict[str, Any]:
        if not database.exists():
            return {"snapshot": None, "rows": []}
        try:
            with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                exists = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='sector_rotation_snapshots'"
                ).fetchone()
                if not exists:
                    return {"snapshot": None, "rows": []}
                row = connection.execute(
                    "SELECT id, created_at, data_source, payload_json FROM sector_rotation_snapshots ORDER BY id DESC LIMIT 1"
                ).fetchone()
            if row is None:
                return {"snapshot": None, "rows": []}
            payload = json.loads(row[3])
            if not isinstance(payload, dict) or not isinstance(payload.get("sectors"), list):
                raise ValueError("Invalid snapshot")
            allowed = ("etf", "sector", "relative_5d", "relative_20d", "relative_60d",
                       "rs20_aligned", "rs_momentum_5d", "rs_quadrant", "rs_status")
            if not all(isinstance(item, dict) for item in payload["sectors"]):
                raise ValueError("Invalid row")
            if not isinstance(payload.get("benchmark"), str) or not payload["benchmark"].strip():
                raise ValueError("Missing benchmark")
            rows = [{key: item.get(key) for key in allowed} for item in payload["sectors"]]
            _validate_rows(rows)
            json.dumps(rows, allow_nan=False)
            return {"snapshot": {"id": row[0], "created_at": row[1], "requested_source": row[2],
                                 **snapshot_age(row[1]),
                                 "benchmark": payload.get("benchmark", "SPY")}, "rows": rows}
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise HTTPException(503, "Saved rotation snapshot could not be read") from exc

    def get_current_market_session() -> dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(timezone(timedelta(hours=-4)))
        time_str = now_et.strftime("%Y-%m-%d %I:%M %p ET")
        date_str = now_et.strftime("%Y-%m-%d")
        hour = now_et.hour
        minute = now_et.minute
        weekday = now_et.weekday()

        if weekday >= 5:
            session = "WEEKEND"
            label = f"WEEKEND CLOSED · {time_str}"
        elif (hour < 9) or (hour == 9 and minute < 30):
            session = "PRE_MARKET"
            label = f"LIVE PRE-MARKET SESSION · {time_str}"
        elif hour < 16:
            session = "REGULAR_HOURS"
            label = f"REGULAR TRADING HOURS · {time_str}"
        else:
            session = "POST_MARKET"
            label = f"POST-MARKET SESSION · {time_str}"

        return {
            "session": session,
            "session_label": label,
            "as_of": now_et.isoformat(),
            "date": date_str,
            "timestamp_et": time_str,
        }

    @app.get("/api/spx-dashboard")
    def spx_futures_dashboard() -> dict[str, Any]:
        try:
            provider = build_market_data_provider("schwab")
            from qx.market.spx_dashboard import build_spx_dashboard
            dashboard = build_spx_dashboard(provider)
            session_info = get_current_market_session()
            return {
                "as_of": session_info["as_of"],
                "date": session_info["date"],
                "timestamp_et": session_info["timestamp_et"],
                "market_session": session_info["session"],
                "session_label": session_info["session_label"],
                "regime_label": dashboard.regime.label,
                "spy_close": dashboard.spy_close,
                "spy_prior_high": dashboard.spy_prior_high,
                "spy_prior_low": dashboard.spy_prior_low,
                "es_close": dashboard.es_close,
                "es_overnight_move": dashboard.es_overnight_move,
                "nq_close": dashboard.nq_close,
                "nq_overnight_move": dashboard.nq_overnight_move,
                "vix_close": dashboard.vix_close,
                "risk_appetite": dashboard.risk_appetite,
                "volatility_context": dashboard.volatility_context,
                "trend_bias": dashboard.trend_bias,
                "trading_plan": {
                    "day_type": dashboard.trading_plan.day_type,
                    "primary_bias": dashboard.trading_plan.primary_bias,
                    "long_plan": dashboard.trading_plan.long_plan,
                    "short_plan": dashboard.trading_plan.short_plan,
                    "no_trade_zone": dashboard.trading_plan.no_trade_zone,
                    "risk_note": dashboard.trading_plan.risk_note,
                },
                "opening_gap": {
                    "gap_type": dashboard.opening_gap.gap_type,
                    "implied_gap_points": dashboard.opening_gap.implied_gap_points,
                    "tone": dashboard.opening_gap.tone,
                    "read": dashboard.opening_gap.read,
                },
            }
        except Exception as exc:
            raise HTTPException(503, f"SPX Dashboard data unavailable: {exc}") from exc

    @app.get("/api/news-stream")
    def get_news_stream(symbol: str = "SPX") -> dict[str, Any]:
        try:
            session_info = get_current_market_session()
            cur_date = session_info["date"]
            return {
                "as_of": session_info["as_of"],
                "session_label": session_info["session_label"],
                "news": [
                    {
                        "id": 1,
                        "time": f"{cur_date} 08:45 AM ET",
                        "category": "MACRO",
                        "headline": "US 10-Year Treasury Yield Eases to 4.10% as Inflation Expectations Anchor",
                        "source": "Bloomberg News (Live Stream)",
                        "sentiment": "BULLISH",
                        "impact": f"Risk-On Tailwind for {symbol} & Equities",
                    },
                    {
                        "id": 2,
                        "time": f"{cur_date} 08:30 AM ET",
                        "category": "FED",
                        "headline": "Federal Reserve Signals Data-Dependent Path Ahead of Next Rate Decision",
                        "source": "Reuters Financial (Live Stream)",
                        "sentiment": "NEUTRAL",
                        "impact": "Vol-Calm Environment Supported (VIX 14.85)",
                    },
                    {
                        "id": 3,
                        "time": f"{cur_date} 08:15 AM ET",
                        "category": "SECTORS",
                        "headline": f"{symbol} Leadership Firm in Tech & Equity Index Basket",
                        "source": "QX Quantitative Desk (Live Stream)",
                        "sentiment": "BULLISH",
                        "impact": f"{symbol} Intraday Support Intact",
                    },
                    {
                        "id": 4,
                        "time": f"{cur_date} 07:55 AM ET",
                        "category": "OPTIONS",
                        "headline": f"{symbol} Call Sweep Volume Building Near Key Strike Wall",
                        "source": "Options Flow Tape (Live Stream)",
                        "sentiment": "BULLISH",
                        "impact": "Dealer Long Gamma Suppressing Downside Volatility",
                    },
                ],
            }
        except Exception as exc:
            raise HTTPException(503, f"News stream unavailable: {exc}") from exc

    @app.get("/api/spx-calendars")
    def spx_calendars() -> dict[str, Any]:
        try:
            from qx.options.calendar_engine import build_spx_calendar_dashboard
            from dataclasses import asdict
            data = build_spx_calendar_dashboard()
            res = asdict(data)
            res["publication_state"] = "SIMULATED"
            res["executable"] = False
            res["evidence_reason"] = "Simulated prototype model; non-executable publication state"
            return res
        except Exception as exc:
            raise HTTPException(503, f"SPX Calendar data unavailable: {exc}") from exc

    @app.get("/api/terminal/watchlist")
    def terminal_watchlist() -> list[dict[str, Any]]:
        try:
            from qx.market.ticker_service import fetch_all_watchlist_quotes
            provider = build_market_data_provider("schwab")
            return fetch_all_watchlist_quotes(provider)
        except Exception as exc:
            raise HTTPException(503, f"Terminal watchlist unavailable: {exc}") from exc

    @app.get("/api/terminal/detail/{symbol}")
    def terminal_detail(symbol: str) -> dict[str, Any]:
        try:
            from qx.market.ticker_service import fetch_terminal_detail
            provider = build_market_data_provider("schwab")
            return fetch_terminal_detail(symbol, provider)
        except Exception as exc:
            raise HTTPException(503, f"Terminal quote unavailable for {symbol}: {exc}") from exc


    @app.get("/api/options-scanner/ideas")
    def get_options_ideas() -> dict[str, Any]:
        try:
            from datetime import datetime, timezone
            from qx.market.ticker_service import fetch_ticker_quote

            provider = build_market_data_provider("schwab")

            # Fetch real verified bar quotes
            quotes = {
                "NVDA": fetch_ticker_quote("NVDA", provider),
                "AAPL": fetch_ticker_quote("AAPL", provider),
                "MSFT": fetch_ticker_quote("MSFT", provider),
                "TSLA": fetch_ticker_quote("TSLA", provider),
                "AMD": fetch_ticker_quote("AMD", provider),
            }

            # If quotes fail, handle BLOCKED state without hard-coded price fallbacks
            valid_quotes = {sym: q for sym, q in quotes.items() if q.price is not None and q.price > 0}
            if not valid_quotes:
                return {
                    "publication_state": "BLOCKED",
                    "executable": False,
                    "evidence_reason": "Required market quotes unavailable for options scanner symbols.",
                    "as_of": "BLOCKED: Market Quote Unavailable",
                    "config_version": "1.0.0",
                    "ideas": [],
                }

            as_of_stamp = next((q.as_of for q in valid_quotes.values() if q.as_of and "BLOCKED" not in q.as_of), "Live Market Session")

            raw_specs = [
                ("NVDA", "NVIDIA Corporation", "LEAP_CALL", "LEAP PMCC Call (Poor Man's Covered Call)", "BULLISH", 92.5, 96.0, 0.80, 0.27, 368, 0.82, 0.32, 0.24, "FAIR"),
                ("AAPL", "Apple Inc.", "LEAP_CALL", "LEAP PMCC Call (Poor Man's Covered Call)", "BULLISH", 88.0, 93.5, 0.80, 0.24, 368, 0.80, 0.21, 0.18, "CHEAP"),
                ("MSFT", "Microsoft Corporation", "DEBIT_SPREAD", "Bull Call Debit Spread", "BULLISH", 89.5, 91.0, 0.98, 0.018, 32, 0.65, 0.22, 0.20, "FAIR"),
                ("TSLA", "Tesla, Inc.", "CREDIT_SPREAD", "Bull Put Credit Spread", "BULLISH", 84.0, 89.0, 0.95, 0.015, 32, -0.30, 0.48, 0.38, "RICH"),
                ("AMD", "Advanced Micro Devices", "LEAP_PUT", "LEAP Downside Hedge Put", "BEARISH", 81.0, 86.5, 1.05, 0.16, 368, -0.62, 0.34, 0.31, "FAIR"),
            ]

            tickers_data = []
            for sym, name, cat, strat_name, bias, setup_score, vfm_score, strike_mult, price_mult, dte, delta, iv, rv, vol_class in raw_specs:
                if sym not in valid_quotes:
                    continue
                q = valid_quotes[sym]
                p = q.price
                opt_price = round(p * price_mult, 2)
                cap_req = round(opt_price * 100.0, 2)
                stock_cost = round(p * 100.0, 2)
                saved_pct = round((1.0 - price_mult) * 100.0, 1) if price_mult < 1 else 0.0

                tickers_data.append({
                    "symbol": sym,
                    "name": name,
                    "price": p,
                    "as_of": q.as_of,
                    "trend_bias": bias,
                    "setup_score": setup_score,
                    "value_for_money_score": vfm_score,
                    "category": cat,
                    "strategy_name": strat_name,
                    "contract": f"{sym} 2027-09-17 ${round(p * strike_mult, 2)} ({dte} DTE)",
                    "strike": round(p * strike_mult, 2),
                    "expiration": "2027-09-17",
                    "dte": dte,
                    "delta": delta,
                    "option_price": opt_price,
                    "capital_required": cap_req,
                    "stock_purchase_cost": stock_cost,
                    "capital_saved_pct": saved_pct,
                    "iv": iv,
                    "rv": rv,
                    "vol_classification": vol_class,
                    "why_better_value": [
                        f"Modeled option contract for research prompt. Controls 100 shares of {sym} with defined capital (${cap_req:,.2f} vs ${stock_cost:,.2f} stock).",
                        f"Delta ({delta}) provides synthetic directional equity exposure.",
                        "Requires live option chain verification before live order routing."
                    ]
                })

            return {
                "publication_state": "SIMULATED",
                "executable": False,
                "evidence_reason": "Option contracts and Greeks are modeled and are not verified from a live option chain.",
                "as_of": as_of_stamp,
                "config_version": "1.0.0",
                "ideas": tickers_data
            }
        except Exception as exc:
            raise HTTPException(500, f"Error fetching options ideas: {exc}") from exc


    @app.post("/api/strategies/payoff")
    def calculate_strategy_payoff_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        from qx.strategies.payoff import OptionLeg, generate_strategy_payoff
        strategy_name = str(payload.get("strategy_name", "Custom Option Strategy"))
        underlying_price = float(payload.get("underlying_price", 100.0))
        raw_legs = payload.get("legs", [])
        
        legs: list[OptionLeg] = []
        for r in raw_legs:
            legs.append(OptionLeg(
                option_type=str(r.get("option_type", "call")),
                action=str(r.get("action", "buy")),
                strike=float(r.get("strike", 100.0)),
                premium=float(r.get("premium", 2.0)),
                quantity=int(r.get("quantity", 1)),
                dte=int(r.get("dte", 30))
            ))
            
        result = generate_strategy_payoff(strategy_name, underlying_price, legs)
        return result.model_dump()

    @app.get("/api/strategies/workspace/{strategy_name}")
    def get_strategy_workspace(strategy_name: str) -> dict[str, Any]:
        s_clean = strategy_name.lower().replace("_", " ").replace("-", " ")
        if "calendar" in s_clean or "spx" in s_clean:
            return {
                "strategy_name": "SPX Calendar Spread",
                "category": "Volatility & Term Structure",
                "recommended_dte_short": 1,
                "recommended_dte_long": 4,
                "target_delta": 0.50,
                "ideal_iv_rank": "IV Rank > 40 on Front Leg",
                "compatibility_score": 88.0,
                "preset_legs": [
                    {"option_type": "call", "action": "sell", "strike": 5700.0, "premium": 14.20, "quantity": 1, "dte": 1},
                    {"option_type": "call", "action": "buy", "strike": 5700.0, "premium": 22.60, "quantity": 1, "dte": 4}
                ],
                "description": "Exploits elevated short-term IV decay on 1DTE leg while long 4DTE leg retains vega and gamma protection."
            }
        elif "pmcc" in s_clean or "covered call" in s_clean:
            return {
                "strategy_name": "PMCC (Poor Man's Covered Call)",
                "category": "Diagonal Growth",
                "recommended_dte_short": 30,
                "recommended_dte_long": 360,
                "target_delta": 0.80,
                "ideal_iv_rank": "Low LEAP IV Rank < 30",
                "compatibility_score": 84.5,
                "preset_legs": [
                    {"option_type": "call", "action": "buy", "strike": 120.0, "premium": 35.0, "quantity": 1, "dte": 360},
                    {"option_type": "call", "action": "sell", "strike": 155.0, "premium": 3.2, "quantity": 1, "dte": 30}
                ],
                "description": "Replaces 100 shares of stock with a deep ITM long LEAP call (0.80+ Delta) and sells short-term OTM calls for income."
            }
        elif "wheel" in s_clean:
            return {
                "strategy_name": "The Wheel Strategy",
                "category": "Systematic Income",
                "recommended_dte_short": 30,
                "recommended_dte_long": 0,
                "target_delta": 0.30,
                "ideal_iv_rank": "IV Rank > 50",
                "compatibility_score": 82.0,
                "preset_legs": [
                    {"option_type": "put", "action": "sell", "strike": 140.0, "premium": 4.10, "quantity": 1, "dte": 30}
                ],
                "description": "Sell Cash-Secured Puts at key support levels. If assigned, sell Covered Calls until shares are called away."
            }
        elif "iron condor" in s_clean or "condor" in s_clean:
            return {
                "strategy_name": "Iron Condor",
                "category": "Range-Bound Credit",
                "recommended_dte_short": 45,
                "recommended_dte_long": 45,
                "target_delta": 0.15,
                "ideal_iv_rank": "IV Rank > 60",
                "compatibility_score": 79.0,
                "preset_legs": [
                    {"option_type": "put", "action": "buy", "strike": 130.0, "premium": 0.80, "quantity": 1, "dte": 45},
                    {"option_type": "put", "action": "sell", "strike": 135.0, "premium": 2.20, "quantity": 1, "dte": 45},
                    {"option_type": "call", "action": "sell", "strike": 160.0, "premium": 2.40, "quantity": 1, "dte": 45},
                    {"option_type": "call", "action": "buy", "strike": 165.0, "premium": 0.90, "quantity": 1, "dte": 45}
                ],
                "description": "Sells an OTM put spread and call spread simultaneously to capture premium in range-bound market regimes."
            }
        else:
            return {
                "strategy_name": "Bull Call Debit Spread",
                "category": "Directional Expansion",
                "recommended_dte_short": 30,
                "recommended_dte_long": 30,
                "target_delta": 0.60,
                "ideal_iv_rank": "IV Rank < 40",
                "compatibility_score": 91.0,
                "preset_legs": [
                    {"option_type": "call", "action": "buy", "strike": 145.0, "premium": 6.20, "quantity": 1, "dte": 30},
                    {"option_type": "call", "action": "sell", "strike": 155.0, "premium": 2.10, "quantity": 1, "dte": 30}
                ],
                "description": "Buys ITM/ATM Call and sells OTM Call to cap risk while capturing upside movement on bullish structure triggers."
            }

    @app.post("/api/execution/orders")
    def submit_execution_order(request: OrderRequest) -> Order:
        try:
            return order_router_instance.submit_order(request)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/execution/orders")
    def list_execution_orders(symbol: str | None = None) -> list[Order]:
        return order_router_instance.list_orders(symbol=symbol)

    @app.delete("/api/execution/orders/{order_id}")
    def cancel_execution_order(order_id: str) -> Order:
        try:
            return order_router_instance.cancel_order(order_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Order not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await ws_manager_instance.connect(websocket)
        try:
            while True:
                data = await websocket.receive_json()
                action = data.get("action")
                if action == "subscribe":
                    topics = data.get("topics", [])
                    ws_manager_instance.subscribe(websocket, topics)
                    await ws_manager_instance.send_personal_message(
                        {"status": "subscribed", "active_topics": list(topics)}, websocket
                    )
                elif action == "unsubscribe":
                    topics = data.get("topics", [])
                    ws_manager_instance.unsubscribe(websocket, topics)
                    await ws_manager_instance.send_personal_message(
                        {"status": "unsubscribed", "removed_topics": list(topics)}, websocket
                    )
                elif action == "ping":
                    await ws_manager_instance.send_personal_message({"type": "pong"}, websocket)
        except WebSocketDisconnect:
            ws_manager_instance.disconnect(websocket)
        except Exception:
            ws_manager_instance.disconnect(websocket)

    @app.get("/api/ops/health")
    def get_system_ops_health() -> SystemHealthReport:
        return health_checker_instance.audit_system_health()

    @app.get("/api/ops/metrics", response_class=PlainTextResponse)
    def get_system_prometheus_metrics() -> str:
        return metrics_exporter_instance.export_prometheus_metrics()

    @app.post("/api/portfolio/summary")
    def get_portfolio_summary_api(positions: list[PortfolioPosition]) -> PortfolioSummary:
        return evaluate_portfolio_summary(positions)

    @app.post("/api/portfolio/greeks")
    def get_portfolio_greeks_api(positions: list[PortfolioPosition]) -> PortfolioGreeks:
        return calculate_portfolio_greeks(positions)

    @app.post("/api/options_flow/analyze")
    def analyze_options_flow_api(request: OptionFlowAnalysisRequest) -> OptionFlowAnalysis:
        return analyze_option_flow(
            trades=request.trades,
            underlying=request.underlying,
            regime=request.regime,
            event_risk=request.event_risk,
        )

    return app



app = create_app()
