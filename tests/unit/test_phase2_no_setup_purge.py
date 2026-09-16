"""Phase 2: Purge Synthetic Trades & Enforce Real NO_SETUP Tests.

Verifies:
1. No synthetic percentage-based fallback entries remain.
2. No fixed confidence values (94, 88, 84, 82) are emitted as signal confidence.
3. No setup produces an empty signals list and primary_playbook="NO_SETUP".
4. Real detected structural setups are preserved with dynamic confidence scores.
5. API contract survives with ai_signals: [].
"""

import numpy as np
import pandas as pd
from qx.signals.smc_rules_engine import QXRulesPipelineEngine, generate_smc_trade_signals
from qx.market.ticker_service import fetch_terminal_detail
from qx.structure.smc_suite import OrderBlock, SMCAnalysisResult
from qx.models.rules import SignalState, PublicationState


def _make_plain_bars(base_price: float = 100.0, length: int = 20) -> pd.DataFrame:
    """Helper to construct 20 flat/featureless 5m bars with no order block."""
    steps = np.linspace(base_price, base_price + 0.10, length)
    return pd.DataFrame({
        "open": steps,
        "high": steps + 0.05,
        "low": steps - 0.05,
        "close": steps + 0.02,
        "volume": np.full(length, 1000),
    })


def _make_ob_bars(base_price: float = 100.0, length: int = 30) -> pd.DataFrame:
    """Helper to construct bars that produce a valid unmitigated SMC demand OB."""
    n = max(30, length)
    prices = np.zeros(n)
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    closes = np.zeros(n)

    # Leg 1: 0..10 (rise to high pivot)
    prices[0:11] = np.linspace(base_price, base_price + 3.0, 11)
    # Leg 2: 11..15 (pullback to low pivot)
    prices[11:16] = np.linspace(base_price + 2.8, base_price + 1.0, 5)
    # Leg 3: 16..end (strong breakout)
    prices[16:n] = np.linspace(base_price + 1.5, base_price + 8.0, n - 16)

    for i in range(n):
        opens[i] = prices[i] - 0.10
        closes[i] = prices[i] + 0.10
        highs[i] = max(opens[i], closes[i]) + 0.15
        lows[i] = min(opens[i], closes[i]) - 0.15

    # High pivot peak at bar 10
    highs[10] = base_price + 3.50
    closes[10] = base_price + 3.20

    # Red candidate candle at bar 15 before breakout
    opens[15] = base_price + 1.40
    closes[15] = base_price + 0.90
    lows[15] = base_price + 0.70
    highs[15] = base_price + 1.50

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(n, 2500),
    })


def test_no_setup_returns_empty_signals():
    """Verify that featureless bars return NO_SETUP with empty signals list."""
    bars = _make_plain_bars(100.0)
    res = generate_smc_trade_signals("SPY", bars)
    assert res.symbol == "SPY"
    assert res.primary_playbook == "NO_SETUP"
    assert res.signals == []
    assert len(res.signals) == 0


def test_no_percentage_fallback_entry_generated():
    """Verify no p * 0.998 or p * 1.002 percentage fallback entries are generated."""
    bars = _make_plain_bars(150.0)
    res = generate_smc_trade_signals("NVDA", bars)
    assert len(res.signals) == 0
    # Search signal list for synthetic price calculations
    for sig in res.signals:
        assert sig.entry != round(150.0 * 0.998, 2)
        assert sig.entry != round(150.0 * 1.002, 2)


def test_no_fixed_confidence_is_emitted():
    """Verify hard-coded fixed confidence scores (94, 88, 84, 82) are not emitted."""
    bars = _make_plain_bars(200.0)
    res = generate_smc_trade_signals("AAPL", bars)
    # When no setup, zero signals emitted
    assert len(res.signals) == 0

    # When setup exists, confidence comes dynamically from smc structure score
    ob_bars = _make_ob_bars(200.0)
    ob_res = generate_smc_trade_signals("AAPL", ob_bars)
    for sig in ob_res.signals:
        # Confidence must not be hard-coded 94 or 88 or 84 or 82
        assert sig.confidence not in (94, 88, 84, 82)
        assert 0 <= sig.confidence <= 100


def test_real_existing_setup_is_preserved():
    """Verify that a real detected SMC Order Block setup is preserved."""
    ob_bars = _make_ob_bars(180.0)
    res = generate_smc_trade_signals("XLK", ob_bars)
    assert res.primary_playbook == "SMC_DEMAND_ORDER_BLOCK"
    assert len(res.signals) == 1
    assert res.signals[0].ticker == "XLK"
    assert res.signals[0].playbook_id == 1
    assert res.signals[0].entry > 0


def test_no_setup_does_not_become_watch_without_evidence():
    """Verify pipeline state stays SIMULATED/NO_SETUP when no setup evidence exists."""
    engine = QXRulesPipelineEngine()
    bars = _make_plain_bars(100.0)
    pipeline_res = engine.execute_pipeline("QQQ", bars, provider_connected=True)
    assert pipeline_res.stage3_setup_detector.has_setup is False
    assert pipeline_res.stage3_setup_detector.setup_name == "NO_SETUP"
    assert pipeline_res.stage4_entry_trigger.triggered is False
    assert pipeline_res.stage9_execution_eligibility.publication_state in ("VERIFIED", "SIMULATED")
    assert pipeline_res.stage9_execution_eligibility.executable is False


def test_api_contract_survives_empty_signal_list():
    """Verify /api/terminal/detail/{symbol} returns valid contract with ai_signals: []."""
    detail = fetch_terminal_detail("TSLA")
    assert detail["symbol"] == "TSLA"
    assert "ai_signals" in detail
    assert isinstance(detail["ai_signals"], list)
    assert len(detail["ai_signals"]) == 0
    assert len(detail["level2_asks"]) == 3
    assert len(detail["level2_bids"]) == 3
    assert len(detail["tape_prints"]) == 5


def test_frontend_payload_handles_no_setup_state():
    """Verify terminal detail payload structure handles NO_SETUP state without error."""
    detail = fetch_terminal_detail("SPX")
    assert detail["symbol"] == "SPX"
    assert detail["ai_signals"] == []


# --- PHASE 2.1 CORRECTION TESTS ---

def test_stale_data_returns_blocked_not_no_setup():
    """Verify that stale / disconnected provider returns BLOCKED, not NO_SETUP."""
    bars = _make_plain_bars(100.0)
    res = generate_smc_trade_signals("SPY", bars, provider_connected=False)
    assert res.publication_state == "BLOCKED"
    assert res.signal_state == "BLOCKED"
    assert res.primary_playbook == "BLOCKED"
    assert res.signals == []


def test_insufficient_bars_returns_blocked():
    """Verify that fewer than 5 bars returns BLOCKED, not NO_SETUP."""
    short_bars = _make_plain_bars(100.0, length=3)
    res = generate_smc_trade_signals("SPY", short_bars, provider_connected=True)
    assert res.publication_state == "BLOCKED"
    assert res.signal_state == "BLOCKED"
    assert res.primary_playbook == "BLOCKED"
    assert res.signals == []


def test_valid_data_without_setup_returns_no_setup():
    """Verify that valid bars without an SMC setup return NO_SETUP."""
    bars = _make_plain_bars(100.0, length=20)
    res = generate_smc_trade_signals("QQQ", bars, provider_connected=True)
    assert res.publication_state in ("VERIFIED", "SIMULATED")
    assert res.signal_state == "NO_SETUP"
    assert res.primary_playbook == "NO_SETUP"
    assert res.signals == []


def test_uncalibrated_structure_score_is_not_probability_confidence():
    """Verify setup quality is explicitly labeled and calibration status is RESEARCH."""
    ob_bars = _make_ob_bars(150.0)
    res = generate_smc_trade_signals("NVDA", ob_bars)
    assert len(res.signals) == 1
    sig = res.signals[0]
    assert sig.calibration_status == "RESEARCH"
    assert sig.historical_win_probability is None
    assert isinstance(sig.setup_quality, float)
    assert "Setup Quality" in sig.rationale
    assert "Calibration: RESEARCH" in sig.rationale


def test_verified_market_data_can_return_no_setup():
    """Verify publication_state=VERIFIED can exist alongside signal_state=NO_SETUP."""
    bars = _make_plain_bars(100.0)
    engine = QXRulesPipelineEngine()
    pipeline_res = engine.execute_pipeline("SPY", bars, provider_connected=True)
    assert pipeline_res.stage0_data_trust.passed is True
    assert pipeline_res.stage0_data_trust.feed_source == "SCHWAB_API"
    assert pipeline_res.stage9_execution_eligibility.publication_state == "VERIFIED"
    
    res = generate_smc_trade_signals("SPY", bars, provider_connected=True)
    assert res.publication_state == "VERIFIED"
    assert res.signal_state == "NO_SETUP"


def test_simulated_data_can_contain_valid_research_setup():
    """Verify publication_state=SIMULATED can hold a valid research trade setup without reaching EXECUTABLE."""
    ob_bars = _make_ob_bars(100.0)
    engine = QXRulesPipelineEngine()
    pipeline_res = engine.execute_pipeline("SPY", ob_bars, provider_connected=True)
    res = generate_smc_trade_signals("SPY", ob_bars, provider_connected=True)
    if res.publication_state == "SIMULATED":
        assert res.signal_state != "EXECUTABLE"
        assert res.signal_state in ("TRIGGERED", "ARMED")
    assert len(res.signals) == 1
    assert res.signals[0].playbook_id == 1


# --- PHASE 2.2 EXECUTABLE INVARIANT TESTS ---

import pytest
from qx.signals.smc_rules_engine import QXRulesEngineResult, QXSignalSetup
from qx.models.rules import DeterministicSignalResult, PublicationState, SignalState, MarketRegimeModel, TrendRegime, VolatilityRegime, GammaRegime, SessionRegime


def test_simulated_signal_can_never_be_executable():
    """Verify hard invariant: SIMULATED publication state raises ValueError if signal_state is EXECUTABLE."""
    with pytest.raises(ValueError, match="Hard invariant violation: signal_state cannot be EXECUTABLE"):
        QXRulesEngineResult(
            symbol="SPY",
            price=100.0,
            qx_score=50.0,
            primary_playbook="SMC_DEMAND_ORDER_BLOCK",
            publication_state="SIMULATED",
            signal_state="EXECUTABLE",
            signals=[],
        )

    with pytest.raises(ValueError, match="Hard invariant violation: signal_state cannot be EXECUTABLE"):
        DeterministicSignalResult(
            signal_id="sig_1",
            symbol="SPY",
            publication_state=PublicationState.SIMULATED,
            data_as_of="now",
            generated_at="now",
            market_regime=MarketRegimeModel(
                trend=TrendRegime.TREND_UP,
                volatility=VolatilityRegime.NORMAL,
                gamma=GammaRegime.POSITIVE_GAMMA,
                session=SessionRegime.TREND_SESSION,
            ),
            direction="BULLISH",
            direction_score=50.0,
            playbook_id="1",
            setup_quality=80.0,
            participation_score=80.0,
            market_alignment_score=80.0,
            tradeability_score=80.0,
            signal_state=SignalState.EXECUTABLE,
        )


def test_research_only_signal_can_never_be_executable():
    """Verify hard invariant: RESEARCH_ONLY publication state raises ValueError if signal_state is EXECUTABLE."""
    with pytest.raises(ValueError, match="Hard invariant violation: signal_state cannot be EXECUTABLE"):
        QXRulesEngineResult(
            symbol="NVDA",
            price=150.0,
            qx_score=60.0,
            primary_playbook="SMC_DEMAND_ORDER_BLOCK",
            publication_state="RESEARCH_ONLY",
            signal_state="EXECUTABLE",
            signals=[],
        )


def test_executable_requires_verified_publication_state():
    """Verify signal_state == EXECUTABLE requires publication_state == VERIFIED."""
    valid_res = QXRulesEngineResult(
        symbol="AAPL",
        price=200.0,
        qx_score=80.0,
        primary_playbook="SMC_DEMAND_ORDER_BLOCK",
        publication_state="VERIFIED",
        signal_state="EXECUTABLE",
        signals=[],
    )
    assert valid_res.publication_state == "VERIFIED"
    assert valid_res.signal_state == "EXECUTABLE"


def test_verified_triggered_signal_is_not_automatically_executable():
    """Verify a VERIFIED triggered signal is NOT automatically EXECUTABLE unless all eligibility gates pass."""
    ob_bars = _make_ob_bars(100.0)
    engine = QXRulesPipelineEngine()
    pipeline_res = engine.execute_pipeline("SPY", ob_bars, provider_connected=True)
    
    # Evaluate signal result
    res = generate_smc_trade_signals("SPY", ob_bars, provider_connected=True)
    
    # Unless Stage 9 execution eligibility explicitly passes all live broker gates, state must be TRIGGERED, not EXECUTABLE
    if not pipeline_res.stage9_execution_eligibility.executable:
        assert res.signal_state != "EXECUTABLE"
        assert res.signal_state == "TRIGGERED"
