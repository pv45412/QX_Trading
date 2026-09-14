"""
Performance Benchmark & SLA Latency Audit Regression Test Suite.

Measures response latencies (ms) and execution speeds for QX Platform REST API
endpoints and quantitative engines against strictly defined SLAs.
"""

import time
import pytest
from fastapi.testclient import TestClient
from datetime import date

from qx.interfaces.web import create_app
from qx.options.pricing import evaluate_option_pricing, OptionPricingRequest
from qx.portfolio import calculate_portfolio_greeks, PortfolioPosition
from qx.options_flow import analyze_option_flow, OptionFlowTrade, UnderlyingContext


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    # Warmup app initialization
    app.get("/api/ops/health")
    return TestClient(app)


class TestPerformanceBenchmarks:
    def test_api_market_snapshot_latency(self, client: TestClient) -> None:
        """API Benchmark: Warm Market Snapshot response latency < 250 ms."""
        # Warmup call
        client.get("/api/market/XLK/snapshot")

        start = time.perf_counter()
        response = client.get("/api/market/XLK/snapshot")
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert response.status_code == 200
        assert elapsed_ms < 250.0, f"Market Snapshot API latency too high: {elapsed_ms:.2f} ms"
        print(f"\n[PERF BENCHMARK] Market Snapshot XLK: {elapsed_ms:.2f} ms")

    def test_api_position_advisor_latency(self, client: TestClient) -> None:
        """API Benchmark: Position Advisor response latency < 100 ms."""
        payload = {
            "symbol": "VST",
            "position_type": "Long Call",
            "entry_price": 14.05,
            "quantity": 1,
            "target_price": 190.0,
            "stop_loss": 130.0,
            "current_price": 148.53,
            "option_mark": 9.95,
        }
        start = time.perf_counter()
        response = client.post("/api/position-advisor", json=payload)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert response.status_code == 200
        assert elapsed_ms < 100.0, f"Position Advisor API latency too high: {elapsed_ms:.2f} ms"
        print(f"\n[PERF BENCHMARK] Position Advisor API: {elapsed_ms:.2f} ms")

    def test_api_portfolio_greeks_latency(self, client: TestClient) -> None:
        """API Benchmark: Portfolio Greeks calculation latency < 150 ms."""
        payload = [
            {"symbol": "XLK", "asset_class": "STOCK", "quantity": 100, "entry_price": 140.0, "current_price": 148.5, "delta": 1.0},
            {"symbol": "SPY", "asset_class": "OPTION", "quantity": 5, "entry_price": 4.5, "current_price": 5.2, "delta": 0.45, "gamma": 0.02, "theta": -0.15, "vega": 0.25},
        ]
        # Warmup call
        client.post("/api/portfolio/greeks", json=payload)

        start = time.perf_counter()
        response = client.post("/api/portfolio/greeks", json=payload)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert response.status_code == 200
        assert elapsed_ms < 150.0, f"Portfolio Greeks API latency too high: {elapsed_ms:.2f} ms"
        print(f"\n[PERF BENCHMARK] Portfolio Greeks API: {elapsed_ms:.2f} ms")

    def test_api_ops_health_latency(self, client: TestClient) -> None:
        """API Benchmark: System Health Auditor latency < 150 ms."""
        # Warmup call
        client.get("/api/ops/health")

        start = time.perf_counter()
        response = client.get("/api/ops/health")
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert response.status_code == 200
        assert elapsed_ms < 150.0, f"Ops Health API latency too high: {elapsed_ms:.2f} ms"
        print(f"\n[PERF BENCHMARK] Ops Health Check API: {elapsed_ms:.2f} ms")

    def test_engine_options_pricing_speed(self) -> None:
        """Engine Benchmark: Black-Scholes pricing & Greeks calculation speed < 15 ms."""
        req = OptionPricingRequest(
            underlying_price=150.0,
            strike=155.0,
            dte=30.0,
            volatility=0.25,
            interest_rate=0.045,
            option_type="call",
        )
        start = time.perf_counter()
        pricing = evaluate_option_pricing(req)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert pricing.theoretical_price > 0.0
        assert elapsed_ms < 15.0, f"Options Pricing engine speed too slow: {elapsed_ms:.2f} ms"
        print(f"\n[PERF BENCHMARK] Options Pricing Engine: {elapsed_ms:.2f} ms")

    def test_engine_options_flow_speed(self) -> None:
        """Engine Benchmark: Options Order Flow analyzer speed < 15 ms."""
        trades = [
            OptionFlowTrade(
                ticker="XLK",
                option_symbol="XLK260918C00150000",
                expiration=date(2026, 9, 18),
                strike=150.0,
                option_type="call",
                trade_price=3.50,
                bid=3.40,
                ask=3.50,
                size=500,
                effective_premium=175000.0,
                volume=2000,
                open_interest=500,
                implied_volatility=0.28,
                delta=0.55,
                trade_kind="sweep",
            )
        ]
        underlying = UnderlyingContext(ticker="XLK", current_price=148.50)

        start = time.perf_counter()
        analysis = analyze_option_flow(trades, underlying=underlying)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert analysis.ticker == "XLK"
        assert elapsed_ms < 15.0, f"Options Flow engine speed too slow: {elapsed_ms:.2f} ms"
        print(f"\n[PERF BENCHMARK] Options Flow Engine: {elapsed_ms:.2f} ms")
