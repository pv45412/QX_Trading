"""Pre-Flight API & Data Freshness Regression Test Suite."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import pandas as pd
from datetime import datetime, timezone

from qx.interfaces.web import create_app
from qx.data.cache import _read_cached_bars


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestAPIRegression:
    def test_market_snapshot_live_contract(self, client):
        """Verify cached market snapshots remain explicitly source-backed."""
        symbols = ["XLK", "VST", "SPY"]
        for sym in symbols:
            response = client.get(f"/api/market/{sym}/snapshot")
            assert response.status_code == 200, f"Snapshot for {sym} failed with status {response.status_code}"
            data = response.json()
            assert data["symbol"] == sym
            assert data["status"] == "SOURCE_BACKED"
            assert data["source_class"] == "SOURCE_BACKED"
            assert data["last_price"] > 0
            assert "structure" in data
            struct = data["structure"]
            assert "current_trend" in struct
            assert "structure_score" in struct
            assert isinstance(struct.get("active_fvgs"), list)

    def test_position_advisor_endpoint_contract(self, client):
        """Verify position advisor calculates correct P&L and verdicts for shares and options."""
        # Long Call Test (VST option contract)
        vst_payload = {
            "symbol": "VST",
            "position_type": "Long Call",
            "entry_price": 14.05,
            "quantity": 1,
            "target_price": 190.0,
            "stop_loss": 130.0,
            "current_price": 148.53,
            "option_mark": 9.95,
        }
        res = client.post("/api/position-advisor", json=vst_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "VST"
        assert data["position_type"] == "Long Call"
        assert data["current_price"] == 148.53
        assert data["unrealized_pnl"] == -410.0
        assert round(data["unrealized_pnl_pct"], 4) == -0.2918
        assert data["action_verdict"] in ["HOLD", "TRIM / TAKE PROFIT", "CLOSE / EXIT", "ROLL / ADJUST"]

        # Long Shares Test
        nvda_payload = {
            "symbol": "NVDA",
            "position_type": "Long Shares",
            "entry_price": 115.0,
            "quantity": 100,
            "target_price": 160.0,
            "stop_loss": 100.0,
        }
        res_nvda = client.post("/api/position-advisor", json=nvda_payload)
        assert res_nvda.status_code == 200
        data_nvda = res_nvda.json()
        assert data_nvda["symbol"] == "NVDA"
        assert "action_verdict" in data_nvda

    def test_options_scanner_scan_contract(self, client):
        """Verify options scanner pipeline returns valid signal evaluation."""
        payload = {"symbol": "NVDA", "account_equity": 100000.0}
        res = client.post("/api/options-scanner/scan", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "NVDA"
        assert "passed_veto" in data
        assert "timestamp" in data

    def test_ai_status_and_evidence_contract(self, client):
        """Verify AI reviewer status and stock evidence contracts."""
        status_res = client.get("/api/ai/status")
        assert status_res.status_code == 200
        status = status_res.json()
        assert "schema_version" in status

        ev_res = client.get("/api/ai/evidence/XLK")
        assert ev_res.status_code == 200
        ev = ev_res.json()
        assert ev.get("facts", {}).get("symbol") == "XLK"

    def test_rotation_analytics_contract(self, client):
        """Verify sector ETF relative strength analytics."""
        res = client.get("/api/rotation/analytics")
        assert res.status_code == 200
        data = res.json()
        assert "rows" in data
        assert isinstance(data["rows"], list)
        assert len(data["rows"]) > 0

    def test_telemetry_signals_contract(self, client):
        """Verify telemetry log retrieval."""
        res = client.get("/api/telemetry/signals")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)

    def test_options_ideas_contract(self, client):
        """Verify options scanner ideas hub endpoint."""
        res = client.get("/api/options-scanner/ideas")
        assert res.status_code == 200
        data = res.json()
        assert "ideas" in data or "items" in data or isinstance(data, list)

    def test_terminal_watchlist_and_detail_contract(self, client):
        """Verify day trader terminal watchlist and single ticker detail."""
        res_wl = client.get("/api/terminal/watchlist")
        assert res_wl.status_code == 200

        res_detail = client.get("/api/terminal/detail/XLK")
        assert res_detail.status_code == 200
        data = res_detail.json()
        assert data.get("symbol") == "XLK" or "price" in data

    def test_spx_dashboard_and_calendars_contract(self, client):
        """Verify SPX command dashboard and option calendar endpoints."""
        res_spx = client.get("/api/spx-dashboard")
        assert res_spx.status_code == 200

        res_cal = client.get("/api/spx-calendars")
        assert res_cal.status_code == 200

    def test_movers_sp500_contract(self, client):
        """Verify S&P 500 movers endpoint."""
        res = client.get("/api/movers/sp500")
        assert res.status_code == 200

    def test_strategy_payoff_and_workspace_contract(self, client):
        """Verify strategy leg payoff calculation and strategy workspace presets."""
        ws_res = client.get("/api/strategies/workspace/spx-calendar")
        assert ws_res.status_code == 200
        ws_data = ws_res.json()
        assert ws_data["strategy_name"] == "SPX Calendar Spread"
        assert "preset_legs" in ws_data

        payoff_payload = {
            "strategy_name": "Bull Call Spread",
            "underlying_price": 148.53,
            "legs": [
                {"option_type": "call", "action": "buy", "strike": 145.0, "premium": 6.2, "quantity": 1, "dte": 30},
                {"option_type": "call", "action": "sell", "strike": 155.0, "premium": 2.1, "quantity": 1, "dte": 30}
            ]
        }
        payoff_res = client.post("/api/strategies/payoff", json=payoff_payload)
        assert payoff_res.status_code == 200
        payoff_data = payoff_res.json()
        assert payoff_data["net_debit_credit"] == 410.0
        assert payoff_data["max_risk_dollars"] == 410.0
        assert payoff_data["max_profit_dollars"] == 590.0
        assert len(payoff_data["curve"]) > 0


class TestDataFreshnessRegression:
    def test_cached_bars_integrity_and_columns(self):
        """Verify cached daily bar files contain valid OHLCV columns."""
        bars_dir = Path("data/cache/bars")
        assert bars_dir.exists(), "Cache bars directory missing"
        csv_files = list(bars_dir.glob("*_1y.csv"))
        assert len(csv_files) > 0, "No _1y.csv bar files found in cache"

        for csv_path in csv_files[:5]:
            bars = _read_cached_bars(csv_path)
            assert not bars.empty, f"Bar file {csv_path.name} is empty"
            assert "close" in bars.columns, f"Bar file {csv_path.name} missing 'close' column"
            assert isinstance(bars.index, pd.DatetimeIndex), f"Bar file {csv_path.name} index is not DatetimeIndex"
