from types import SimpleNamespace

import pandas as pd

import qx.pipeline.orchestrator as orchestrator
from qx.config.rules_config import load_rules_config
from qx.direction.direction_engine import DirectionEngineResult, compute_structure_factor
from qx.models.rules import SignalState, TrendRegime
from qx.pipeline.models import QXEvaluationContext
from qx.playbooks.context import QXEvaluationContext as PlaybookContext
from qx.playbooks.pullback import TrendPullbackEvaluator
from qx.regime.market_regime import evaluate_market_regime
from qx.structure.smc_suite import LiquidityPool, analyze_smc_structure


def _structural_sequence() -> pd.DataFrame:
    index = pd.date_range("2026-09-16 09:30", periods=32, freq="5min", tz="UTC")
    rows = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000}
        for _ in index
    ]
    rows[5].update(high=105.0, close=104.0)
    rows[8].update(low=95.0, close=96.0)
    rows[12].update(high=107.0, close=106.0)
    rows[15].update(high=110.0, close=109.0)
    rows[18].update(low=98.0, close=99.0)
    rows[21].update(high=112.0, close=111.0)
    rows[27].update(low=93.0, close=94.0)
    return pd.DataFrame(rows, index=index)


def _analyze(end_index: int, *, symbol: str = "SPY", timeframe: str = "5m"):
    bars = _structural_sequence().iloc[: end_index + 1]
    return analyze_smc_structure(
        bars,
        is_fast_chart=True,
        symbol=symbol,
        timeframe=timeframe,
        evaluation_bar_index=end_index,
    )


def _direction(score: float = 80.0) -> DirectionEngineResult:
    return DirectionEngineResult(
        symbol="SPY",
        timeframe="5m",
        direction_score=score,
        direction_label="BULLISH" if score >= 0 else "BEARISH",
        direction_evidence_coverage=1.0,
        coverage_status="COMPLETE",
        total_effective_weight=1.0,
    )


def test_confirmed_protected_swing_and_bos_produce_usable_context():
    structure = _analyze(21)

    assert structure.regime == "BULLISH"
    assert structure.protected_low is not None
    assert structure.latest_bos == "BULLISH_BOS"
    assert structure.latest_event.knowledge_timestamp == "2026-09-16 11:20 UTC"

    regime = evaluate_market_regime(structure_result=structure)
    factor = compute_structure_factor(structure_result=structure)

    assert regime.trend == TrendRegime.TREND_UP
    assert factor.raw_score > 0


def test_confirmed_choch_produces_correct_transition_context():
    structure = _analyze(27)

    assert structure.regime == "BEARISH"
    assert structure.latest_choch == "BEARISH_CHOCH"
    assert structure.latest_event is not None
    assert structure.latest_event.previous_structure_state == "BULLISH"
    assert structure.latest_event.new_structure_state == "BEARISH"
    assert evaluate_market_regime(structure_result=structure).trend == TrendRegime.TREND_DOWN


def test_structure_context_persists_after_event_bar():
    event_bar = _analyze(21)
    later_bar = _analyze(24)

    assert event_bar.latest_bos == "BULLISH_BOS"
    assert later_bar.regime == "BULLISH"
    assert later_bar.latest_bos == "BULLISH_BOS"
    assert later_bar.protected_low is not None
    assert later_bar.protected_low.pivot_id == event_bar.protected_low.pivot_id


def test_future_unconfirmed_pivot_does_not_create_context():
    before_confirmation = _analyze(6)
    after_confirmation = _analyze(7)

    pivot_id = "PIVOT_HIGH_5_5m"
    assert pivot_id not in {pivot.pivot_id for pivot in before_confirmation.confirmed_pivots}
    assert pivot_id in {pivot.pivot_id for pivot in after_confirmation.confirmed_pivots}
    assert before_confirmation.regime == "NEUTRAL"
    confirmed = next(pivot for pivot in after_confirmation.confirmed_pivots if pivot.pivot_id == pivot_id)
    assert confirmed.confirmation_timestamp == "2026-09-16 10:10 UTC"
    assert confirmed.knowledge_timestamp == "2026-09-16 10:10 UTC"


def test_structure_symbol_and_timeframe_are_isolated():
    spy = _analyze(21, symbol="SPY", timeframe="5m")
    qqq = _analyze(21, symbol="QQQ", timeframe="15m")

    assert spy.events and qqq.events
    assert {event.symbol for event in spy.events} == {"SPY"}
    assert {event.timeframe for event in spy.events} == {"5m"}
    assert {event.symbol for event in qqq.events} == {"QQQ"}
    assert {event.timeframe for event in qqq.events} == {"15m"}
    assert {pivot.pivot_id for pivot in spy.confirmed_pivots}.isdisjoint(
        {pivot.pivot_id for pivot in qqq.confirmed_pivots}
    )


def test_structure_output_is_consumed_by_pullback_without_false_no_context():
    structure = _analyze(21)
    regime = evaluate_market_regime(structure_result=structure)
    context = PlaybookContext(
        symbol="SPY",
        timeframe="5m",
        latest_bar={"close": 111.0, "high": 112.0, "low": 110.0},
        market_regime=regime,
        direction=_direction(),
        structure_result=structure,
        order_blocks=structure.order_blocks,
        vwap=111.0,
        atr=2.0,
        event_timestamp="2026-09-16T11:15:00+00:00",
        knowledge_timestamp="2026-09-16T11:15:00+00:00",
    )

    evaluation = TrendPullbackEvaluator().evaluate(context)

    structure_rule = next(rule for rule in evaluation.rule_results if rule.rule_id == "QX-PB-A-003")
    assert structure_rule.passed is True
    assert evaluation.reason_code != "NO_STRUCTURAL_CONTEXT"


def test_canonical_order_block_fields_are_consumed_without_legacy_aliases():
    structure = _analyze(21)
    regime = evaluate_market_regime(structure_result=structure)
    context = PlaybookContext(
        symbol="SPY",
        timeframe="5m",
        latest_bar={"close": 99.5, "high": 100.0, "low": 99.0},
        market_regime=regime,
        direction=_direction(),
        structure_result=structure,
        order_blocks=structure.order_blocks,
        atr=2.0,
        event_timestamp="2026-09-16T11:15:00+00:00",
        knowledge_timestamp="2026-09-16T11:15:00+00:00",
    )

    evaluation = TrendPullbackEvaluator().evaluate(context)

    assert evaluation.state == SignalState.ARMED
    assert "OB_BULL_20_5m" in evaluation.source_order_block_ids


def test_pipeline_forwards_canonical_structural_references(monkeypatch):
    captured = {}

    class CapturingPlaybookEngine:
        def evaluate_all(self, context):
            captured["context"] = context
            result = SimpleNamespace(
                state=SignalState.NO_SETUP,
                engine_version="test",
            )
            return [result], result

    monkeypatch.setattr(orchestrator, "PlaybookEngine", CapturingPlaybookEngine)
    bars = _structural_sequence().iloc[:22]
    config = load_rules_config()
    context = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=bars.index[-1].to_pydatetime(),
        bars=bars,
        config=config,
        config_version=config.version,
    )

    result = orchestrator.run_pipeline(context, config)
    playbook_context = captured["context"]

    assert result.structure is not None
    assert playbook_context.order_blocks == result.structure.order_blocks
    assert playbook_context.session_levels == {}
    assert result.structure.protected_low in playbook_context.liquidity_levels
    assert all(
        pool in playbook_context.liquidity_levels for pool in result.structure.liquidity_pools
    )


def test_canonical_protected_swing_identity_reaches_liquidity_playbook():
    structure = _analyze(24)
    regime = evaluate_market_regime(structure_result=structure)
    context = PlaybookContext(
        symbol="SPY",
        timeframe="5m",
        latest_bar={"close": 98.5, "high": 99.0, "low": 97.0},
        market_regime=regime,
        direction=_direction(),
        structure_result=structure,
        liquidity_levels=[structure.protected_low],
        atr=2.0,
        event_timestamp="2026-09-16T11:30:00+00:00",
        knowledge_timestamp="2026-09-16T11:30:00+00:00",
    )

    from qx.playbooks.liquidity_sweep import LiquiditySweepEvaluator

    evaluation = LiquiditySweepEvaluator().evaluate(context)

    assert evaluation.state == SignalState.ARMED
    assert evaluation.source_pivot_ids == [structure.protected_low.pivot_id]
    assert evaluation.trigger_source_id == structure.protected_low.pivot_id
    assert evaluation.trigger_knowledge_timestamp == structure.protected_low.knowledge_timestamp


def test_canonical_liquidity_pool_provenance_reaches_playbook():
    structure = _analyze(24)
    regime = evaluate_market_regime(structure_result=structure)
    pool = LiquidityPool(
        pool_id="EQL_PIVOT_LOW_8_5m_PIVOT_LOW_18_5m",
        pool_type="EQL",
        price=98.0,
        source_pivot_ids=["PIVOT_LOW_8_5m", "PIVOT_LOW_18_5m"],
        knowledge_timestamp="2026-09-16 11:15 UTC",
    )
    context = PlaybookContext(
        symbol="SPY",
        timeframe="5m",
        latest_bar={"close": 97.5, "high": 98.0, "low": 97.0},
        market_regime=regime,
        direction=_direction(),
        structure_result=structure,
        liquidity_levels=[pool],
        atr=2.0,
        event_timestamp="2026-09-16T11:30:00+00:00",
        knowledge_timestamp="2026-09-16T11:30:00+00:00",
    )

    from qx.playbooks.liquidity_sweep import LiquiditySweepEvaluator

    evaluation = LiquiditySweepEvaluator().evaluate(context)

    assert evaluation.state == SignalState.ARMED
    assert evaluation.source_pivot_ids == pool.source_pivot_ids
    assert evaluation.trigger_source_id == pool.pool_id
    assert evaluation.trigger_knowledge_timestamp == pool.knowledge_timestamp
