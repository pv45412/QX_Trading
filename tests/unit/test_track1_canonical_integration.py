import inspect
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import qx.interfaces.qx_v2 as qx_v2
import qx.interfaces.web as web
import qx.pipeline.adapters as adapters
import qx.pipeline.orchestrator as pipeline_orchestrator
from qx.config.rules_config import load_rules_config
from qx.direction.direction_engine import DirectionEngineResult
from qx.models.rules import SignalState
from qx.models.rules import MarketRegimeModel
from qx.options_expression.models import OptionsContext, OptionsExpressionState
from qx.options_scanner.models import ScanResult
from qx.pipeline.adapters import HistoricalReplayAdapter
from qx.pipeline.models import (
    PIPELINE_VERSION,
    SKIPPED,
    LifecycleState,
    QXEvaluationContext,
    QXEvaluationResult,
)
from qx.pipeline.shadow_telemetry import ShadowTelemetryRepository
from qx.portfolio.models import AccountRiskContext, PortfolioRiskState
from qx.tradeability.models import TradeabilityState


EVALUATION_TIMESTAMP = datetime(2026, 9, 15, 15, 30, tzinfo=timezone.utc)


def _bars(*timestamps: datetime) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": list(timestamps),
            "open": [100.0] * len(timestamps),
            "high": [101.0] * len(timestamps),
            "low": [99.0] * len(timestamps),
            "close": [100.5] * len(timestamps),
            "volume": [1000] * len(timestamps),
        }
    )


def _account_snapshot(timestamp: datetime) -> AccountRiskContext:
    return AccountRiskContext(
        account_id="test-account",
        equity=100000.0,
        cash=50000.0,
        buying_power=50000.0,
        data_as_of=timestamp,
        broker_provenance="TEST_READ_ONLY",
    )


def _result_for_context(
    context: QXEvaluationContext,
    state: LifecycleState = LifecycleState.NO_SETUP,
) -> QXEvaluationResult:
    return QXEvaluationResult(
        symbol=context.symbol,
        timeframe=context.timeframe,
        evaluation_timestamp=context.evaluation_timestamp,
        request_started_at=context.request_started_at,
        publication_state=context.publication_state,
        current_lifecycle_state=state,
        config_version=context.config_version,
        pipeline_version=PIPELINE_VERSION,
    )


def _run_scenario(
    monkeypatch: pytest.MonkeyPatch,
    *,
    playbook_state: SignalState = SignalState.NO_SETUP,
    trigger_state: SignalState = SignalState.ARMED,
    tradeability_state: TradeabilityState = TradeabilityState.NOT_TRADEABLE,
    options_state: OptionsExpressionState = OptionsExpressionState.NOT_SUITABLE,
    portfolio_state: PortfolioRiskState = PortfolioRiskState.PORTFOLIO_APPROVED,
    bars: pd.DataFrame | None = None,
    include_option_chain: bool = True,
    include_account_snapshot: bool = True,
) -> tuple[QXEvaluationResult, list[str], dict[str, object]]:
    calls: list[str] = []
    captured: dict[str, object] = {}
    config = load_rules_config()
    structure = SimpleNamespace(
        regime="RANGE",
        latest_event="NONE",
        engine_version="structure-test",
    )
    regime = MarketRegimeModel.model_construct(engine_version="regime-test")
    direction = DirectionEngineResult.model_construct(
        direction_score=50.0,
        direction_label="BULLISH",
        engine_version="direction-test",
    )
    playbook = SimpleNamespace(
        state=playbook_state,
        structural_target_candidates=[105.0],
        event_timestamp=(EVALUATION_TIMESTAMP - timedelta(minutes=1)).isoformat(),
        trigger_knowledge_timestamp=(EVALUATION_TIMESTAMP - timedelta(minutes=2)).isoformat(),
        playbook_id="playbook_a_pullback",
        symbol="SPY",
        timeframe="5m",
        engine_version="playbooks-test",
    )
    trigger = SimpleNamespace(
        state=trigger_state,
        trigger_confirmed_at=EVALUATION_TIMESTAMP.isoformat(),
        trigger_event_timestamp=EVALUATION_TIMESTAMP.isoformat(),
        engine_version="trigger-test",
    )
    tradeability = SimpleNamespace(
        state=tradeability_state,
        reason_codes=[tradeability_state.value],
        playbook_id="playbook_a_pullback",
        direction="BULLISH",
        target_candidates=[105.0],
        engine_version="tradeability-test",
    )
    candidate = SimpleNamespace(candidate_id="candidate-1")
    options_expression = SimpleNamespace(
        state=options_state,
        reason_codes=[options_state.value],
        candidate_strategies=(
            [candidate] if options_state == OptionsExpressionState.SUITABLE else []
        ),
        primary_candidate_id=(
            "candidate-1" if options_state == OptionsExpressionState.SUITABLE else None
        ),
        engine_version="options-test",
    )
    portfolio_risk = SimpleNamespace(
        state=portfolio_state,
        reason_codes=[portfolio_state.value],
        engine_version="portfolio-test",
    )

    def evaluate_structure(**kwargs):
        calls.append("structure")
        captured["structure_bars"] = kwargs["bars"]
        return structure

    def evaluate_regime(**kwargs):
        calls.append("regime")
        captured["regime_timestamp"] = kwargs["timestamp_str"]
        return regime

    def evaluate_direction(**kwargs):
        calls.append("direction")
        return direction

    class FakePlaybookEngine:
        def evaluate_all(self, context):
            calls.append("playbooks")
            captured["playbook_timestamp"] = context.event_timestamp
            return [playbook], playbook

    class FakeTriggerEngine:
        def __init__(self, _config):
            pass

        def evaluate_trigger(self, **_kwargs):
            calls.append("trigger")
            return trigger

    class FakeTradeabilityEngine:
        def __init__(self, _config):
            pass

        def evaluate_triggered_setup(self, _trigger, evidence, **_kwargs):
            calls.append("tradeability")
            captured["tradeability_timestamp"] = evidence.evaluation_timestamp
            return tradeability

    class FakeOptionsExpressionEngine:
        def __init__(self, _config):
            pass

        def evaluate_options_expression(self, _tradeability, _context, *, evaluation_timestamp):
            calls.append("options_expression")
            captured["options_timestamp"] = evaluation_timestamp
            return options_expression

    class FakePortfolioRiskEngine:
        def __init__(self, _config):
            pass

        def evaluate_portfolio_risk(
            self,
            _candidate,
            _expression,
            _account,
            *,
            evaluation_timestamp,
        ):
            calls.append("portfolio_risk")
            captured["portfolio_timestamp"] = evaluation_timestamp
            return portfolio_risk

    monkeypatch.setattr(pipeline_orchestrator, "analyze_smc_structure", evaluate_structure)
    monkeypatch.setattr(pipeline_orchestrator, "evaluate_market_regime", evaluate_regime)
    monkeypatch.setattr(pipeline_orchestrator, "evaluate_direction_engine", evaluate_direction)
    monkeypatch.setattr(pipeline_orchestrator, "PlaybookEngine", FakePlaybookEngine)
    monkeypatch.setattr(pipeline_orchestrator, "EntryTriggerEngine", FakeTriggerEngine)
    monkeypatch.setattr(pipeline_orchestrator, "TradeabilityEngine", FakeTradeabilityEngine)
    monkeypatch.setattr(
        pipeline_orchestrator,
        "OptionsExpressionEngine",
        FakeOptionsExpressionEngine,
    )
    monkeypatch.setattr(pipeline_orchestrator, "PortfolioRiskEngine", FakePortfolioRiskEngine)

    context = QXEvaluationContext(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVALUATION_TIMESTAMP,
        bars=bars if bars is not None else _bars(EVALUATION_TIMESTAMP),
        option_chain=(
            OptionsContext(
                underlying_symbol="SPY",
                underlying_price=100.5,
                data_as_of=EVALUATION_TIMESTAMP.isoformat(),
            )
            if include_option_chain
            else None
        ),
        account_snapshot=(
            _account_snapshot(EVALUATION_TIMESTAMP) if include_account_snapshot else None
        ),
        config_version=config.version,
        config=config,
    )
    return pipeline_orchestrator.run_pipeline(context, config), calls, captured


def test_no_setup_stops_pipeline_correctly(monkeypatch):
    result, calls, _ = _run_scenario(monkeypatch)
    assert result.current_lifecycle_state == LifecycleState.NO_SETUP
    assert calls == ["structure", "regime", "direction", "playbooks"]


def test_watch_does_not_create_trigger(monkeypatch):
    result, calls, _ = _run_scenario(monkeypatch, playbook_state=SignalState.WATCH)
    assert result.current_lifecycle_state == LifecycleState.WATCH
    assert result.trigger is None
    assert "trigger" not in calls


def test_armed_does_not_create_tradeability(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.ARMED,
    )
    assert result.current_lifecycle_state == LifecycleState.ARMED
    assert result.tradeability is None
    assert "tradeability" not in calls


def test_triggered_continues_to_tradeability(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
    )
    assert result.tradeability is not None
    assert "tradeability" in calls


def test_tradeable_continues_to_options_expression(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
    )
    assert result.options_expression is not None
    assert "options_expression" in calls


def test_suitable_options_continue_to_portfolio_risk(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
        options_state=OptionsExpressionState.SUITABLE,
    )
    assert result.portfolio_risk is not None
    assert calls[-1] == "portfolio_risk"


def test_not_tradeable_stops_before_options(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.NOT_TRADEABLE,
    )
    assert result.current_lifecycle_state == LifecycleState.NOT_TRADEABLE
    assert result.options_expression is None
    assert "options_expression" not in calls


def test_not_suitable_options_stops_before_portfolio(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
        options_state=OptionsExpressionState.NOT_SUITABLE,
    )
    assert result.current_lifecycle_state == LifecycleState.OPTIONS_NOT_SUITABLE
    assert result.portfolio_risk is None
    assert "portfolio_risk" not in calls


def test_missing_option_chain_does_not_fabricate_options_result(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
        include_option_chain=False,
    )
    assert result.current_lifecycle_state == LifecycleState.BLOCKED
    assert result.publication_state.value == "BLOCKED"
    assert result.options_expression is None
    assert result.stage_latencies["options_expression_ms"] == SKIPPED
    assert "options_expression" not in calls


def test_missing_account_snapshot_does_not_fabricate_portfolio_result(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
        options_state=OptionsExpressionState.SUITABLE,
        include_account_snapshot=False,
    )
    assert result.current_lifecycle_state == LifecycleState.BLOCKED
    assert result.portfolio_risk is None
    assert result.stage_latencies["portfolio_risk_ms"] == SKIPPED
    assert "portfolio_risk" not in calls


def test_portfolio_veto_preserved(monkeypatch):
    result, _, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
        options_state=OptionsExpressionState.SUITABLE,
        portfolio_state=PortfolioRiskState.PORTFOLIO_VETOED,
    )
    assert result.current_lifecycle_state == LifecycleState.PORTFOLIO_VETOED


def test_portfolio_approved_preserved(monkeypatch):
    result, calls, _ = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
        options_state=OptionsExpressionState.SUITABLE,
        portfolio_state=PortfolioRiskState.PORTFOLIO_APPROVED,
    )
    assert result.current_lifecycle_state == LifecycleState.PORTFOLIO_APPROVED
    assert calls == [
        "structure",
        "regime",
        "direction",
        "playbooks",
        "trigger",
        "tradeability",
        "options_expression",
        "portfolio_risk",
    ]


def test_no_downstream_object_created_after_stop_state(monkeypatch):
    result, _, _ = _run_scenario(monkeypatch, playbook_state=SignalState.NO_SETUP)
    assert result.trigger is None
    assert result.tradeability is None
    assert result.options_expression is None
    assert result.portfolio_risk is None


def test_pipeline_uses_shared_evaluation_timestamp(monkeypatch):
    result, _, _ = _run_scenario(monkeypatch)
    assert result.evaluation_timestamp == EVALUATION_TIMESTAMP


def test_pipeline_never_uses_future_data(monkeypatch):
    result, _, captured = _run_scenario(
        monkeypatch,
        bars=_bars(EVALUATION_TIMESTAMP, EVALUATION_TIMESTAMP + timedelta(minutes=5)),
    )
    structure_bars = captured["structure_bars"]
    assert len(structure_bars) == 1
    assert pd.to_datetime(structure_bars["timestamp"], utc=True).max() <= EVALUATION_TIMESTAMP
    assert result.current_lifecycle_state == LifecycleState.NO_SETUP


def test_replay_uses_same_orchestrator_as_live_api(monkeypatch):
    contexts: list[QXEvaluationContext] = []

    def spy(context, _config):
        contexts.append(context)
        return _result_for_context(context)

    monkeypatch.setattr(adapters.orchestrator, "run_pipeline", spy)
    replay = HistoricalReplayAdapter(load_rules_config(), "SPY")
    results = replay.replay(
        _bars(EVALUATION_TIMESTAMP, EVALUATION_TIMESTAMP + timedelta(minutes=5)),
        warmup_bars=0,
    )
    assert len(contexts) == len(results) == 2
    assert all(result.pipeline_version == PIPELINE_VERSION for result in results)
    assert contexts[0].evaluation_timestamp == EVALUATION_TIMESTAMP + timedelta(minutes=5)
    assert contexts[1].evaluation_timestamp == EVALUATION_TIMESTAMP + timedelta(minutes=10)


def test_historical_replay_cannot_use_future_retrieval(monkeypatch):
    contexts: list[QXEvaluationContext] = []
    future_timestamp = EVALUATION_TIMESTAMP + timedelta(hours=1)
    past_options = OptionsContext(
        underlying_symbol="SPY",
        underlying_price=100.0,
        data_as_of=EVALUATION_TIMESTAMP.isoformat(),
        retrieved_at=EVALUATION_TIMESTAMP.isoformat(),
    )
    future_options = OptionsContext(
        underlying_symbol="SPY",
        underlying_price=200.0,
        data_as_of=EVALUATION_TIMESTAMP.isoformat(),
        retrieved_at=future_timestamp.isoformat(),
    )
    past_account = _account_snapshot(EVALUATION_TIMESTAMP).model_copy(
        update={"retrieved_at": EVALUATION_TIMESTAMP}
    )
    future_account = _account_snapshot(EVALUATION_TIMESTAMP).model_copy(
        update={"retrieved_at": future_timestamp}
    )

    def spy(context, _config):
        contexts.append(context)
        return _result_for_context(context)

    monkeypatch.setattr(adapters.orchestrator, "run_pipeline", spy)
    replay = HistoricalReplayAdapter(load_rules_config(), "SPY")
    replay.replay(
        _bars(EVALUATION_TIMESTAMP, EVALUATION_TIMESTAMP + timedelta(minutes=5)),
        warmup_bars=0,
        option_chain_snapshots=[past_options, future_options],
        account_snapshots=[past_account, future_account],
    )
    assert all(context.option_chain is past_options for context in contexts)
    assert all(context.account_snapshot is past_account for context in contexts)
    assert all(
        pd.to_datetime(context.bars["timestamp"], utc=True).max() <= context.evaluation_timestamp
        for context in contexts
    )


def test_api_v2_calls_canonical_pipeline(monkeypatch, tmp_path):
    calls: list[QXEvaluationContext] = []
    monkeypatch.setattr(
        qx_v2,
        "load_pipeline_bars",
        lambda *_args, **_kwargs: (_bars(EVALUATION_TIMESTAMP), 1.0, 1, 0),
    )

    def spy(context, _config):
        calls.append(context)
        return _result_for_context(context)

    monkeypatch.setattr(qx_v2.orchestrator, "run_pipeline", spy)
    client = TestClient(web.create_app(tmp_path / "qx.db", tmp_path / "bars"))
    response = client.post(
        "/api/v2/qx/evaluate/SPY",
        params={"evaluation_timestamp": EVALUATION_TIMESTAMP.isoformat()},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert response.json()["pipeline_version"] == PIPELINE_VERSION


def test_api_v2_does_not_call_legacy_ai_review_logic(monkeypatch, tmp_path):
    monkeypatch.setattr(
        qx_v2,
        "load_pipeline_bars",
        lambda *_args, **_kwargs: (_bars(EVALUATION_TIMESTAMP), 1.0, 1, 0),
    )
    monkeypatch.setattr(
        qx_v2.orchestrator,
        "run_pipeline",
        lambda context, _config: _result_for_context(context),
    )
    monkeypatch.setattr(
        web.AIReviewer,
        "review",
        lambda *_args, **_kwargs: pytest.fail("legacy AI called"),
    )
    monkeypatch.setattr(
        web.SignalService,
        "scan_ticker",
        lambda *_args, **_kwargs: pytest.fail("legacy signal called"),
    )
    client = TestClient(web.create_app(tmp_path / "qx.db", tmp_path / "bars"))
    response = client.post("/api/v2/qx/evaluate/SPY")
    assert response.status_code == 200


def test_orchestrator_does_not_import_legacy_signal_service():
    source = inspect.getsource(pipeline_orchestrator)
    assert "SignalService" not in source
    assert "qx.options_scanner" not in source
    assert "ai_review" not in source


def test_shadow_results_written_to_telemetry(monkeypatch, tmp_path):
    database = tmp_path / "shadow.db"
    repository = ShadowTelemetryRepository(database)
    config = load_rules_config()
    legacy_result = SimpleNamespace(
        passed_veto=True,
        direction_result=SimpleNamespace(bias="BULLISH"),
    )
    monkeypatch.setattr(
        web.orchestrator,
        "run_pipeline",
        lambda context, _config: _result_for_context(context),
    )
    web._run_shadow_comparison(
        repository=repository,
        config=config,
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=EVALUATION_TIMESTAMP,
        bars=_bars(EVALUATION_TIMESTAMP),
        legacy_result=legacy_result,
        legacy_latency_ms=2.0,
        external_io_ms=1.0,
        cache_hits=1,
        cache_misses=0,
    )
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT symbol, pipeline_version, legacy_latency_ms, v2_latency_ms
            FROM shadow_telemetry
            """
        ).fetchone()
        columns = {
            item[1] for item in connection.execute("PRAGMA table_info(shadow_telemetry)").fetchall()
        }
    assert row[0] == "SPY"
    assert row[1] == PIPELINE_VERSION
    assert row[2] == 2.0
    assert row[3] is not None
    assert {
        "symbol",
        "timeframe",
        "evaluation_timestamp",
        "legacy_signal",
        "legacy_direction",
        "v2_lifecycle_state",
        "v2_direction_score",
        "v2_primary_playbook",
        "v2_reason_codes",
        "agreement_status",
        "disagreement_category",
        "legacy_latency_ms",
        "v2_latency_ms",
        "legacy_error",
        "v2_error",
        "publication_state",
        "config_version",
        "pipeline_version",
        "engine_versions",
        "created_at",
    }.issubset(columns)


def test_shadow_mode_only_runs_for_configured_symbols(monkeypatch, tmp_path):
    config = load_rules_config()
    config.shadow_mode.symbols = ["SPY"]
    repository = ShadowTelemetryRepository(tmp_path / "shadow.db")
    monkeypatch.setattr(
        web.orchestrator,
        "run_pipeline",
        lambda *_args, **_kwargs: pytest.fail("pipeline should not run"),
    )
    web._run_shadow_comparison(
        repository=repository,
        config=config,
        symbol="IWM",
        timeframe="5m",
        evaluation_timestamp=EVALUATION_TIMESTAMP,
        bars=_bars(EVALUATION_TIMESTAMP),
        legacy_result=SimpleNamespace(),
        legacy_latency_ms=1.0,
        external_io_ms=1.0,
        cache_hits=1,
        cache_misses=0,
    )
    assert not repository.database_path.exists()


def _legacy_scan_result() -> ScanResult:
    return ScanResult(
        symbol="SPY",
        timestamp=EVALUATION_TIMESTAMP,
        passed_veto=False,
    )


def test_shadow_failure_does_not_break_legacy_response(monkeypatch, tmp_path):
    database = tmp_path / "shadow.db"
    monkeypatch.setattr(
        web,
        "load_pipeline_bars",
        lambda *_args, **_kwargs: (_bars(EVALUATION_TIMESTAMP), 1.0, 1, 0),
    )
    monkeypatch.setattr(
        web.SignalService,
        "scan_ticker",
        lambda *_args, **_kwargs: _legacy_scan_result(),
    )
    monkeypatch.setattr(
        web.orchestrator,
        "run_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("v2 failed")),
    )
    client = TestClient(web.create_app(database, tmp_path / "bars"))
    response = client.post("/api/options-scanner/scan", json={"symbol": "SPY"})
    assert response.status_code == 200
    assert response.json()["symbol"] == "SPY"
    with sqlite3.connect(database) as connection:
        v2_error = connection.execute("SELECT v2_error FROM shadow_telemetry").fetchone()[0]
    assert "v2 failed" in v2_error


def test_shadow_telemetry_write_failure_does_not_break_v1(monkeypatch, tmp_path):
    monkeypatch.setattr(
        web,
        "load_pipeline_bars",
        lambda *_args, **_kwargs: (_bars(EVALUATION_TIMESTAMP), 1.0, 1, 0),
    )
    monkeypatch.setattr(
        web.SignalService,
        "scan_ticker",
        lambda *_args, **_kwargs: _legacy_scan_result(),
    )
    monkeypatch.setattr(
        web.orchestrator,
        "run_pipeline",
        lambda context, _config: _result_for_context(context),
    )
    monkeypatch.setattr(
        web.ShadowTelemetryRepository,
        "write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("locked")),
    )
    client = TestClient(web.create_app(tmp_path / "shadow.db", tmp_path / "bars"))
    response = client.post("/api/options-scanner/scan", json={"symbol": "SPY"})
    assert response.status_code == 200
    assert response.json()["publication_state"] == "SIMULATED"


def test_live_api_preserves_request_start_and_single_evaluation_timestamp(monkeypatch, tmp_path):
    calls = 0
    captured: list[QXEvaluationContext] = []
    request_started_at = EVALUATION_TIMESTAMP - timedelta(seconds=1)

    class CountingDateTime:
        @classmethod
        def now(cls, _timezone):
            nonlocal calls
            calls += 1
            return request_started_at if calls == 1 else EVALUATION_TIMESTAMP

    monkeypatch.setattr(
        qx_v2,
        "load_pipeline_bars",
        lambda *_args, **_kwargs: (_bars(EVALUATION_TIMESTAMP), 1.0, 1, 0),
    )

    def spy(context, _config):
        captured.append(context)
        return _result_for_context(context)

    monkeypatch.setattr(qx_v2.orchestrator, "run_pipeline", spy)
    client = TestClient(
        web.create_app(
            tmp_path / "qx.db",
            tmp_path / "bars",
            configure_canonical_providers=False,
        )
    )
    monkeypatch.setattr(qx_v2, "datetime", CountingDateTime)
    response = client.post("/api/v2/qx/evaluate/SPY")
    assert response.status_code == 200
    assert calls == 2
    assert captured[0].request_started_at == request_started_at
    assert captured[0].evaluation_timestamp == EVALUATION_TIMESTAMP
    assert response.json()["request_started_at"] == request_started_at.isoformat().replace(
        "+00:00",
        "Z",
    )
    assert response.json()["evaluation_timestamp"] == EVALUATION_TIMESTAMP.isoformat().replace(
        "+00:00",
        "Z",
    )


def test_downstream_stages_receive_same_evaluation_timestamp(monkeypatch):
    _, _, captured = _run_scenario(
        monkeypatch,
        playbook_state=SignalState.ARMED,
        trigger_state=SignalState.TRIGGERED,
        tradeability_state=TradeabilityState.TRADEABLE,
        options_state=OptionsExpressionState.SUITABLE,
    )
    expected_iso = EVALUATION_TIMESTAMP.isoformat()
    assert captured["regime_timestamp"] == expected_iso
    assert captured["playbook_timestamp"] == expected_iso
    assert captured["tradeability_timestamp"] == expected_iso
    assert captured["options_timestamp"] == EVALUATION_TIMESTAMP
    assert captured["portfolio_timestamp"] == EVALUATION_TIMESTAMP


def test_skipped_pipeline_stage_is_marked_skipped_not_zero_ms(monkeypatch):
    result, _, _ = _run_scenario(monkeypatch, playbook_state=SignalState.NO_SETUP)
    assert result.stage_latencies["trigger_ms"] == SKIPPED
    assert result.stage_latencies["tradeability_ms"] == SKIPPED
    assert result.stage_latencies["options_expression_ms"] == SKIPPED
    assert result.stage_latencies["portfolio_risk_ms"] == SKIPPED
    assert result.stage_latencies["playbooks_ms"] != 0
