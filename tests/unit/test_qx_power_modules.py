import pandas as pd
import numpy as np
from qx.options.gex import calculate_gamma_exposure
from qx.patterns.intraday_orb import analyze_intraday_setup
from qx.market.fundamental_quality import evaluate_fundamental_quality


def test_gamma_exposure_calculation():
    chain = pd.DataFrame([
        {"strike": 5000, "option_type": "call", "open_interest": 1000, "volume": 500, "gamma": 0.005, "dte": 0},
        {"strike": 5000, "option_type": "put", "open_interest": 1500, "volume": 800, "gamma": 0.005, "dte": 0},
        {"strike": 5050, "option_type": "call", "open_interest": 2000, "volume": 1200, "gamma": 0.008, "dte": 0},
        {"strike": 4950, "option_type": "put", "open_interest": 1800, "volume": 1100, "gamma": 0.007, "dte": 0},
    ])
    snapshot = calculate_gamma_exposure("SPX", 5010.0, chain)
    assert snapshot.symbol == "SPX"
    assert snapshot.current_price == 5010.0
    assert snapshot.zero_dte_volume_ratio == 1.0
    assert snapshot.expected_move_1sigma > 0
    assert snapshot.regime in ["Long Gamma (Volatility Suppressed)", "Short Gamma (Volatility Accelerated)"]


def test_intraday_vwap_and_orb_setup():
    dates = pd.date_range("2026-09-11 09:30", periods=20, freq="1min")
    bars = pd.DataFrame({
        "open": np.linspace(100, 105, 20),
        "high": np.linspace(101, 106, 20),
        "low": np.linspace(99, 104, 20),
        "close": np.linspace(100.5, 105.5, 20),
        "volume": np.random.randint(1000, 5000, 20),
    }, index=dates)

    snapshot = analyze_intraday_setup("AAPL", bars)
    assert snapshot.symbol == "AAPL"
    assert snapshot.last_price == 105.5
    assert snapshot.vwap > 0
    assert snapshot.vwap_upper_1std >= snapshot.vwap
    assert "ORB" in snapshot.orb_status


def test_fundamental_quality_evaluation():
    fundamentals = {
        "eps_growth_qtr": 35.0,
        "sales_growth_qtr": 20.0,
        "roe": 22.0,
        "pe_ratio": 28.5,
        "fcf_yield": 6.2,
        "debt_to_equity": 0.5,
    }
    metrics = evaluate_fundamental_quality("NVDA", fundamentals)
    assert metrics.symbol == "NVDA"
    assert metrics.fundamental_quality_score >= 0.75
    assert metrics.investment_tier == "Institutional Core Growth"
