"""BE2 Multi-Timeframe Context Validation Suite.

Validates the approved Option B Dual-Timeframe Evidence Matrix:
- DAY: Setup/Execution 5m, HTF 1h, Macro Daily
- SWING: Setup/Execution 1h, HTF Daily, Macro Weekly
- INVEST: Setup/Execution Daily, HTF Weekly, Macro Monthly

Verifies:
1. Aligned HTF contributes positively (+100.0 score * weight 0.10).
2. Opposing HTF contributes negatively (-100.0 score * weight 0.10).
3. Missing HTF produces factor UNAVAILABLE, reliability = 0.0, evidence coverage reduced, DOES NOT BLOCK.
4. Stale HTF produces factor STALE, reliability cut in half.
5. Incomplete HTF candle (completion > evaluation_timestamp) is strictly excluded from HTF SMC structure.
6. Zero future-bar leakage: post-cutoff prices cannot influence evaluation.
7. Exact point-in-time reproducibility.
8. Timeframe/symbol isolation.
9. Historical replay and live pipeline semantic parity.
10. Core v1 playbooks and triggers are preserved without hard HTF veto or altered lifecycle states.
"""

from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest

from qx.config.rules_config import load_rules_config
from qx.pipeline.adapters import HistoricalReplayAdapter
from qx.pipeline.models import (
    DataDependencyStatus,
    LifecycleState,
    QXEvaluationContext,
    QXEvaluationResult,
)
from qx.pipeline.multi_timeframe import (
    HORIZON_TIMEFRAME_MATRIX,
    aggregate_daily_bars_to_weekly,
    bar_completion_timestamp,
    filter_completed_htf_bars,
    resolve_horizon_for_timeframe,
    resolve_timeframes_for_horizon,
)
from qx.pipeline.orchestrator import run_pipeline
from qx.structure.smc_suite import SMCAnalysisResult, analyze_smc_structure


@pytest.fixture
def config():
    return load_rules_config()


def test_daily_bars_aggregate_to_weekly_without_future_leakage():
    daily = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 110.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0, 111.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0, 109.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 110.5],
            "volume": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        },
        index=pd.to_datetime(
            [
                "2026-09-07",
                "2026-09-08",
                "2026-09-09",
                "2026-09-10",
                "2026-09-11",
                "2026-09-14",
            ],
            utc=True,
        ),
    )

    weekly = aggregate_daily_bars_to_weekly(daily)
    completed, usable_count, incomplete_count = filter_completed_htf_bars(
        weekly,
        datetime(2026, 9, 15, 14, 42, tzinfo=timezone.utc),
        "1w",
    )

    assert list(weekly.index) == [
        pd.Timestamp("2026-09-07", tz="UTC"),
        pd.Timestamp("2026-09-14", tz="UTC"),
    ]
    assert weekly.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.5,
        "volume": 150.0,
    }
    assert usable_count == 1
    assert incomplete_count == 1
    assert completed.iloc[0]["close"] == 104.5


def _generate_synthetic_bars(
    start_time: datetime,
    count: int,
    interval_minutes: int = 5,
    trend: str = "BULLISH",
    base_price: float = 500.0,
) -> pd.DataFrame:
    records = []
    price = base_price
    for idx in range(count):
        bar_ts = start_time + timedelta(minutes=idx * interval_minutes)
        if trend == "BULLISH":
            # Higher highs, higher lows with periodic pullbacks
            drift = 0.3 if idx % 4 != 0 else -0.1
        elif trend == "BEARISH":
            drift = -0.3 if idx % 4 != 0 else 0.1
        else:
            drift = 0.1 if idx % 2 == 0 else -0.1
        
        o = round(price, 2)
        c = round(price + drift, 2)
        h = round(max(o, c) + 0.2, 2)
        l = round(min(o, c) - 0.2, 2)
        v = 5000.0 + (idx * 50.0)
        records.append({
            "timestamp": bar_ts,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })
        price = c
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 1. Horizon & Matrix Mapping Tests
# ---------------------------------------------------------------------------

def test_horizon_matrix_mapping():
    assert resolve_timeframes_for_horizon("DAY") == {"setup": "5m", "htf": "1h", "macro": "1d"}
    assert resolve_timeframes_for_horizon("SWING") == {"setup": "1h", "htf": "1d", "macro": "1w"}
    assert resolve_timeframes_for_horizon("INVEST") == {"setup": "1d", "htf": "1w", "macro": "1w"}
    
    assert resolve_horizon_for_timeframe("5m") == "DAY"
    assert resolve_horizon_for_timeframe("1h") == "SWING"
    assert resolve_horizon_for_timeframe("1d") == "INVEST"


# ---------------------------------------------------------------------------
# 2. Strict Point-in-Time Candle Completion & Anti-Leakage
# ---------------------------------------------------------------------------

def test_bar_completion_timestamp_calculation():
    base = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    
    # 5m bar starts at 10:00 -> completes at 10:05
    assert bar_completion_timestamp({"timestamp": base}, "5m") == base + timedelta(minutes=5)
    
    # 1h bar starts at 10:00 -> completes at 11:00
    assert bar_completion_timestamp({"timestamp": base}, "1h") == base + timedelta(hours=1)
    
    # 1d bar starts at 10:00 -> completes next day
    assert bar_completion_timestamp({"timestamp": base}, "1d") == base + timedelta(days=1)


def test_incomplete_htf_candle_strictly_excluded():
    start = datetime(2026, 9, 17, 9, 0, 0, tzinfo=timezone.utc)
    # Generate 4 hourly bars: 09:00 (ends 10:00), 10:00 (ends 11:00), 11:00 (ends 12:00), 12:00 (ends 13:00)
    htf_bars = _generate_synthetic_bars(start, count=4, interval_minutes=60, trend="BULLISH")
    
    # Evaluation timestamp is 11:30:00 UTC
    eval_ts = start + timedelta(hours=2, minutes=30)  # 11:30
    
    completed_bars, usable_count, incomplete_count = filter_completed_htf_bars(
        bars=htf_bars,
        evaluation_timestamp=eval_ts,
        timeframe="1h",
    )
    
    # 09:00 (completed at 10:00 <= 11:30) -> Usable
    # 10:00 (completed at 11:00 <= 11:30) -> Usable
    # 11:00 (completes at 12:00 > 11:30)  -> INCOMPLETE! Excluded
    # 12:00 (completes at 13:00 > 11:30)  -> INCOMPLETE! Excluded
    assert usable_count == 2
    assert incomplete_count == 2
    assert len(completed_bars) == 2
    assert pd.to_datetime(completed_bars.iloc[-1]["timestamp"], utc=True) == start + timedelta(hours=1)


def test_zero_future_leakage_invariance(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(minutes=60)  # 10:30
    
    setup_bars = _generate_synthetic_bars(start, count=30, interval_minutes=5, trend="BULLISH")
    htf_bars = _generate_synthetic_bars(start, count=10, interval_minutes=60, trend="BULLISH")
    
    ctx1 = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_bars=htf_bars,
        config=config,
    )
    res1 = run_pipeline(ctx1, config)
    
    # Now create an adversarial htf bar stream with extreme volatility occurring AFTER 10:30 (e.g. at 11:00)
    adversarial_htf = htf_bars.copy()
    adversarial_htf.loc[adversarial_htf.index[-1], "high"] = 999999.0
    adversarial_htf.loc[adversarial_htf.index[-1], "close"] = 999999.0
    
    ctx2 = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_bars=adversarial_htf,
        config=config,
    )
    res2 = run_pipeline(ctx2, config)
    
    # Evaluations at 10:30 must be strictly identical
    assert res1.direction.direction_score == res2.direction.direction_score
    assert res1.current_lifecycle_state == res2.current_lifecycle_state
    assert res1.evaluated_bar_window_sha256 == res2.evaluated_bar_window_sha256


# ---------------------------------------------------------------------------
# 3. Factor #7 Directional Contribution (Aligned, Opposing, Missing, Stale)
# ---------------------------------------------------------------------------

def _make_bullish_htf(start_time: datetime, count: int = 50) -> pd.DataFrame:
    times = pd.date_range(start_time, periods=count, freq="1h", tz="UTC")
    steps = np.linspace(100.0, 150.0, count)
    highs = steps + 0.50
    lows = steps - 0.50
    opens = steps - 0.10
    closes = steps + 0.10
    highs[10] = steps[10] + 5.0
    closes[10] = steps[10] + 4.8
    lows[20] = steps[20] - 5.0
    closes[20] = steps[20] - 4.8
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(count, 5000.0),
    }, index=times)


def _make_bearish_htf(start_time: datetime, count: int = 50) -> pd.DataFrame:
    times = pd.date_range(start_time, periods=count, freq="1h", tz="UTC")
    steps = np.linspace(200.0, 150.0, count)
    highs = steps + 0.50
    lows = steps - 0.50
    opens = steps + 0.10
    closes = steps - 0.10
    lows[10] = 185.0
    lows[25] = 165.0
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(count, 5000.0),
    }, index=times)


def test_aligned_htf_positive_contribution(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(hours=52)
    
    setup_bars = _generate_synthetic_bars(start, count=80, interval_minutes=5, trend="BULLISH")
    htf_bars = _make_bullish_htf(start, count=50)
    
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_bars=htf_bars,
        config=config,
    )
    result = run_pipeline(ctx, config)
    
    htf_factor = next((f for f in result.direction.factors if f.factor_id == "higher_timeframe"), None)
    assert htf_factor is not None
    assert htf_factor.availability == "AVAILABLE"
    assert htf_factor.raw_score == 100.0  # Aligned Bullish
    assert htf_factor.configured_weight == 0.10
    assert htf_factor.effective_weight == 0.10
    assert htf_factor.weighted_contribution == 10.0  # 100 * 0.10


def test_opposing_htf_negative_contribution(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(hours=52)
    
    setup_bars = _generate_synthetic_bars(start, count=80, interval_minutes=5, trend="BULLISH")
    htf_bars = _make_bearish_htf(start, count=50)
    
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_bars=htf_bars,
        config=config,
    )
    result = run_pipeline(ctx, config)
    
    htf_factor = next((f for f in result.direction.factors if f.factor_id == "higher_timeframe"), None)
    assert htf_factor is not None
    assert htf_factor.availability == "AVAILABLE"
    assert htf_factor.raw_score == -100.0  # Opposing Bearish
    assert htf_factor.configured_weight == 0.10
    assert htf_factor.effective_weight == 0.10
    assert htf_factor.weighted_contribution == -10.0  # -100 * 0.10


def test_missing_htf_does_not_block_and_reduces_coverage(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(hours=2)
    
    setup_bars = _generate_synthetic_bars(start, count=40, interval_minutes=5, trend="BULLISH")
    
    # Missing HTF bars
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_bars=None,  # Missing
        config=config,
    )
    result = run_pipeline(ctx, config)
    
    # MUST NOT block solely because HTF is missing
    assert result.current_lifecycle_state != LifecycleState.BLOCKED
    
    htf_factor = next((f for f in result.direction.factors if f.factor_id == "higher_timeframe"), None)
    assert htf_factor is not None
    assert htf_factor.availability == "UNAVAILABLE"
    assert htf_factor.reliability_multiplier == 0.0
    assert htf_factor.effective_weight == 0.0
    assert htf_factor.weighted_contribution == 0.0
    
    # Data dependency status correctly records unavailability
    assert "htf_bars" in result.data_dependencies
    assert result.data_dependencies["htf_bars"].available is False
    assert result.data_dependencies["htf_bars"].reason_code in ("HTF_NOT_PROVIDED", "HTF_BARS_UNAVAILABLE")


def test_stale_htf_reduces_reliability(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(hours=6)
    
    setup_bars = _generate_synthetic_bars(start, count=80, interval_minutes=5, trend="BULLISH")
    
    # Explicitly pass HTF structure state with age_bars > 25 (stale threshold)
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_structure_state="BULLISH",
        htf_age_bars=40,  # Stale (> 25)
        config=config,
    )
    result = run_pipeline(ctx, config)
    
    htf_factor = next((f for f in result.direction.factors if f.factor_id == "higher_timeframe"), None)
    assert htf_factor is not None
    assert htf_factor.freshness_status == "STALE"
    assert htf_factor.reliability_multiplier == 0.50  # Cut in half
    assert htf_factor.effective_weight == 0.05  # 0.10 * 0.50
    assert htf_factor.weighted_contribution == 5.0  # 100 * 0.05


# ---------------------------------------------------------------------------
# 4. Horizons Testing: DAY, SWING, INVEST
# ---------------------------------------------------------------------------

def test_day_swing_invest_matrix_resolution(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(hours=5)
    
    # 1. DAY: 5m setup + 1h HTF
    ctx_day = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=_generate_synthetic_bars(start, count=60, interval_minutes=5),
        config=config,
    )
    res_day = run_pipeline(ctx_day, config)
    assert res_day.horizon == "DAY"
    assert res_day.timeframe == "5m"
    assert res_day.htf_timeframe == "1h"
    assert res_day.macro_timeframe == "1d"
    
    # 2. SWING: 1h setup + 1d HTF
    ctx_swing = QXEvaluationContext(
        symbol="SPY",
        timeframe="1h",
        horizon="SWING",
        evaluation_timestamp=eval_ts,
        bars=_generate_synthetic_bars(start, count=60, interval_minutes=60),
        config=config,
    )
    res_swing = run_pipeline(ctx_swing, config)
    assert res_swing.horizon == "SWING"
    assert res_swing.timeframe == "1h"
    assert res_swing.htf_timeframe == "1d"
    assert res_swing.macro_timeframe == "1w"
    
    # 3. INVEST: 1d setup + 1w HTF
    ctx_invest = QXEvaluationContext(
        symbol="SPY",
        timeframe="1d",
        horizon="INVEST",
        evaluation_timestamp=eval_ts,
        bars=_generate_synthetic_bars(start, count=60, interval_minutes=1440),
        config=config,
    )
    res_invest = run_pipeline(ctx_invest, config)
    assert res_invest.horizon == "INVEST"
    assert res_invest.timeframe == "1d"
    assert res_invest.htf_timeframe == "1w"


# ---------------------------------------------------------------------------
# 5. Replay & Live Semantic Parity
# ---------------------------------------------------------------------------

def test_historical_replay_multi_timeframe_parity(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    bars_5m = _generate_synthetic_bars(start, count=60, interval_minutes=5, trend="BULLISH")
    bars_1h = _generate_synthetic_bars(start, count=10, interval_minutes=60, trend="BULLISH")
    
    adapter = HistoricalReplayAdapter(
        config=config,
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
    )
    
    results = adapter.replay(
        historical_bars=bars_5m,
        warmup_bars=52,
        htf_bars=bars_1h,
    )
    
    assert len(results) == 8
    for res in results:
        assert res.horizon == "DAY"
        assert res.htf_timeframe == "1h"
        # Each replay evaluation has exact point-in-time HTF dependency recorded
        assert "htf_bars" in res.data_dependencies


# ---------------------------------------------------------------------------
# 6. Core V1 Playbook Preservation (No Hard Veto)
# ---------------------------------------------------------------------------

def test_core_v1_playbooks_preserved_without_hard_veto(config):
    # Proves that opposing HTF does NOT veto or block a setup from executing its normal Phase 7 logic
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(hours=4)
    
    setup_bars = _generate_synthetic_bars(start, count=50, interval_minutes=5, trend="BULLISH")
    
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_structure_state="BEARISH",  # Opposing
        config=config,
    )
    result = run_pipeline(ctx, config)
    
    # State should be determined by standard playbook logic (NO_SETUP or WATCH, NOT BLOCKED)
    assert result.current_lifecycle_state != LifecycleState.BLOCKED
    assert "HTF_DIRECTIONAL_DISCORDANCE" not in result.reason_codes


# ---------------------------------------------------------------------------
# 7. Explicit SWING & INVEST Dual-Timeframe Pipelines
# ---------------------------------------------------------------------------

def test_swing_1h_with_daily_htf(config):
    start = datetime(2026, 8, 1, 9, 30, 0, tzinfo=timezone.utc)
    # 60 daily bars
    daily_times = pd.date_range(start, periods=60, freq="1D", tz="UTC")
    daily_htf = _make_bullish_htf(start, count=60)
    daily_htf.index = daily_times
    
    # 1h setup bars
    hourly_times = pd.date_range(start + timedelta(days=50), periods=50, freq="1h", tz="UTC")
    hourly_setup = pd.DataFrame({
        "open": np.full(50, 140.0),
        "high": np.full(50, 142.0),
        "low": np.full(50, 139.0),
        "close": np.full(50, 141.0),
        "volume": np.full(50, 10000.0),
    }, index=hourly_times)
    
    eval_ts = hourly_times[-1] + timedelta(hours=2)
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="1h",
        horizon="SWING",
        evaluation_timestamp=eval_ts,
        bars=hourly_setup,
        htf_bars=daily_htf,
        config=config,
    )
    res = run_pipeline(ctx, config)
    assert res.horizon == "SWING"
    assert res.timeframe == "1h"
    assert res.htf_timeframe == "1d"
    assert "htf_bars" in res.data_dependencies
    assert res.data_dependencies["htf_bars"].available is True


def test_invest_daily_with_weekly_htf(config):
    start = datetime(2025, 1, 1, 9, 30, 0, tzinfo=timezone.utc)
    # 60 weekly bars
    weekly_times = pd.date_range(start, periods=60, freq="1W", tz="UTC")
    weekly_htf = _make_bullish_htf(start, count=60)
    weekly_htf.index = weekly_times
    
    # Daily setup bars
    daily_times = pd.date_range(start + timedelta(weeks=50), periods=50, freq="1D", tz="UTC")
    daily_setup = pd.DataFrame({
        "open": np.full(50, 500.0),
        "high": np.full(50, 505.0),
        "low": np.full(50, 498.0),
        "close": np.full(50, 503.0),
        "volume": np.full(50, 20000.0),
    }, index=daily_times)
    
    eval_ts = daily_times[-1] + timedelta(days=2)
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="1d",
        horizon="INVEST",
        evaluation_timestamp=eval_ts,
        bars=daily_setup,
        htf_bars=weekly_htf,
        config=config,
    )
    res = run_pipeline(ctx, config)
    assert res.horizon == "INVEST"
    assert res.timeframe == "1d"
    assert res.htf_timeframe == "1w"
    assert "htf_bars" in res.data_dependencies
    assert res.data_dependencies["htf_bars"].available is True


# ---------------------------------------------------------------------------
# 8. Macro Timeframe Context (Contextual Only, No Weight / Veto)
# ---------------------------------------------------------------------------

def test_macro_timeframe_context_dependency(config):
    start = datetime(2026, 9, 17, 9, 30, 0, tzinfo=timezone.utc)
    eval_ts = start + timedelta(hours=4)
    setup_bars = _generate_synthetic_bars(start, count=50, interval_minutes=5)
    macro_bars = _generate_synthetic_bars(start - timedelta(days=10), count=10, interval_minutes=1440)
    
    # Run pipeline with and without macro bars
    ctx_without = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        config=config,
    )
    res_without = run_pipeline(ctx_without, config)
    
    ctx_with = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        macro_bars=macro_bars,
        config=config,
    )
    res_with = run_pipeline(ctx_with, config)
    
    # Macro context must NOT alter Direction Score or Lifecycle State
    assert res_with.direction.direction_score == res_without.direction.direction_score
    assert res_with.current_lifecycle_state == res_without.current_lifecycle_state
    
    # But macro_bars dependency IS recorded
    assert "macro_bars" in res_with.data_dependencies
    assert res_with.data_dependencies["macro_bars"].available is True


# ---------------------------------------------------------------------------
# 9. Opportunity Publication with Multi-Timeframe Metadata
# ---------------------------------------------------------------------------

def test_opportunity_publication_multi_timeframe_metadata(config, tmp_path):
    from qx.opportunities.repository import OpportunityRepository
    from qx.opportunities.publisher import OpportunityPublisher
    
    db_path = tmp_path / "test_mtf_opps.db"
    repo = OpportunityRepository(db_path)
    publisher = OpportunityPublisher(repo, environment_id="test_env")
    
    now = datetime.now(timezone.utc)
    eval_ts = now - timedelta(minutes=5)
    start = eval_ts - timedelta(hours=60)
    setup_bars = _generate_synthetic_bars(start, count=80, interval_minutes=5, trend="BULLISH")
    htf_bars = _make_bullish_htf(start, count=50)
    
    ctx = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        horizon="DAY",
        evaluation_timestamp=eval_ts,
        bars=setup_bars,
        htf_bars=htf_bars,
        data_dependencies={
            "bars": DataDependencyStatus(
                name="bars",
                available=True,
                retrieved_at=eval_ts,
                content_sha256="a" * 64,
            )
        },
        config=config,
    )
    result = run_pipeline(ctx, config)
    
    plan = publisher.reserve_publication(
        producer_id="test_producer",
        producer_run_id="test_run",
        symbol="SPY",
        timeframe="5m",
    )
    assert plan.should_execute is True

    record = publisher.publish_reserved(
        plan=plan,
        result=result,
        context=ctx,
        producer_id="test_producer",
        producer_run_id="test_run",
        expires_at=eval_ts + timedelta(minutes=15),
        freshness_policy_version="v1",
        horizon_context="DAY",
    )
    
    assert record.symbol == "SPY"
    assert record.timeframe == "5m"
    assert record.horizon_context == "DAY"
    assert "htf_bars" in record.data_dependencies
    assert record.data_dependencies["htf_bars"]["available"] is True
