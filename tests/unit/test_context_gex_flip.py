"""Regression tests for the two Context-page correctness bugs.

1. The gamma "flip" must be None (flip_crossed=False) when cumulative gamma never
   crosses zero across the chain. The old argmin(|cum|) returned the window EDGE
   (e.g. a flip 8-33% away from spot), which is a truncation artifact.
2. When cumulative gamma DOES cross zero, the flip is interpolated — never None.
3. The futures-basis cash index for /YM must be $DJI (1:1 with the futures), while
   the gamma chain proxy stays $DJX (the only Dow root with an option chain).

These lock in behaviour so the "looks populated but is numerically broken" class of
bug cannot silently regress.
"""
import pandas as pd
import pytest

from qx.options.gex import calculate_gamma_exposure


def _gex(strike, option_type, oi, gamma, spot):
    mult = 1.0 if option_type == "call" else -1.0
    return oi * gamma * (spot ** 2) * 0.01 * mult


def test_flip_none_when_no_zero_crossing():
    # Net SHORT across every strike: cumulative gamma is the same sign throughout,
    # so there is no genuine flip. Requires flip=None, not the window edge.
    spot = 760.0
    chain = pd.DataFrame([
        {"strike": 690, "option_type": "put", "open_interest": 1000, "volume": 0, "gamma": 0.01, "dte": 2},
        {"strike": 750, "option_type": "put", "open_interest": 5000, "volume": 0, "gamma": 0.05, "dte": 2},
        {"strike": 800, "option_type": "put", "open_interest": 9000, "volume": 0, "gamma": 0.05, "dte": 2},
    ])
    snap = calculate_gamma_exposure("SPY", spot, chain)
    assert snap.flip_crossed is False
    assert snap.gamma_flip_price is None


def test_flip_interpolated_when_crossing():
    # Call-heavy low strike (positive gex) + put-heavy high strike (negative gex)
    # forces a genuine zero crossing in between.
    spot = 550.0
    chain = pd.DataFrame([
        {"strike": 500, "option_type": "call", "open_interest": 40000, "volume": 0, "gamma": 0.05, "dte": 2},
        {"strike": 600, "option_type": "put", "open_interest": 50000, "volume": 0, "gamma": 0.05, "dte": 2},
    ])
    snap = calculate_gamma_exposure("X", spot, chain)
    assert snap.flip_crossed is True
    assert snap.gamma_flip_price is not None
    # Strictly inside the two strikes (proves interpolation, not an endpoint pick).
    assert 500.0 < snap.gamma_flip_price < 600.0


def test_ym_basis_uses_dow_1to1_not_djx():
    from qx.app import context

    basis_cash = next((c for f, _label, c in context.FUTURES if f == "/YM"), None)
    chain_proxy = next((c for f, _label, c in context.FUTURES_PROXIES if f == "/YM"), None)

    # The bug: $DJX is the Dow quoted /100 (520.02 vs /YM ~52,200), which produced a
    # ~9,938% basis. Basis must use the 1:1 index.
    assert basis_cash == "$DJI"
    # But the gamma chain proxy must keep pointing at $DJX — the only Dow root the
    # option-chain endpoint actually serves. These are different data needs.
    assert chain_proxy == "$DJX"


def test_expected_move_positive_and_regime_set():
    chain = pd.DataFrame([
        {"strike": 500, "option_type": "call", "open_interest": 100, "volume": 10, "gamma": 0.05, "dte": 2},
    ])
    snap = calculate_gamma_exposure("X", 500.0, chain)
    assert snap.expected_move_1sigma > 0
    assert snap.regime in ("Long Gamma (Volatility Suppressed)", "Short Gamma (Volatility Accelerated)")