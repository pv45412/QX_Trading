import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from qx.models.rules import PublicationState
from qx.pipeline.models import (
    DataDependencyStatus,
    LifecycleState,
    QXEvaluationResult,
    SKIPPED,
)
from qx.pipeline.replay_analysis import (
    ReplayObservation,
    ReplayReport,
    ReplayTransitionRecord,
    calculate_outcomes,
    observation_from_result,
    segment_outcomes,
)
from qx.pipeline.replay_store import ReplayRepository


START = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)


def observation(
    index: int,
    state: LifecycleState,
    *,
    tradeability_state: str = "UNAVAILABLE",
    tradeability_entry: float | None = None,
) -> ReplayObservation:
    return ReplayObservation(
        symbol="SPY",
        timeframe="5m",
        timestamp=START + timedelta(minutes=5 * index),
        session_date="2026-09-16",
        publication_state="RESEARCH_ONLY",
        trend_regime="TREND_UP",
        volatility_regime="NORMAL",
        session_regime="TREND_SESSION",
        direction_score=65.0,
        direction_label="BULLISH",
        direction_coverage=0.8,
        coverage_status="STRONG",
        evidence_coverage_bucket="STRONG",
        playbook="playbook_a_pullback",
        lifecycle_state=state,
        trigger_price=100.0,
        invalidation_price=95.0,
        tradeability_state=tradeability_state,
        observed_entry_reference_price=tradeability_entry,
    )


def result(triggered: bool, targets=None, *, gap_triggered: bool = False):
    trigger = (
        SimpleNamespace(
            playbook_evaluation_id="setup-1",
            direction="BULLISH",
            trigger_event=SimpleNamespace(gap_beyond_trigger=gap_triggered),
        )
        if triggered
        else None
    )
    tradeability = SimpleNamespace(target_candidates=targets or []) if triggered else None
    return SimpleNamespace(trigger=trigger, tradeability=tradeability)


def bars(*values):
    return [
        {
            "timestamp": START + timedelta(minutes=5 * index),
            "open": value[0],
            "high": value[1],
            "low": value[2],
            "close": value[3],
            "volume": 1000,
        }
        for index, value in enumerate(values)
    ]


def test_signal_r_and_tradeability_r_are_separate_measurements():
    observations = [
        observation(0, LifecycleState.ARMED),
        observation(
            1,
            LifecycleState.TRADEABLE,
            tradeability_state="TRADEABLE",
            tradeability_entry=101.0,
        ),
        observation(2, LifecycleState.TRADEABLE, tradeability_state="TRADEABLE"),
        observation(3, LifecycleState.NO_SETUP),
    ]
    replay_bars = bars(
        (99, 100, 96, 99),
        (100, 102, 99, 101),
        (102, 111, 99, 110),
        (105, 111, 98, 110),
    )
    outcomes = calculate_outcomes(
        observations,
        replay_bars,
        [result(False), result(True, [110.0]), result(False), result(False)],
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.outcome == "TARGET_HIT"
    assert outcome.signal_risk == 5.0
    assert outcome.signal_mfe_r == 2.0
    assert outcome.signal_endpoint_r == 2.0
    assert outcome.tradeability_entry_reference_price == 101.0
    assert outcome.tradeability_risk == 6.0
    assert outcome.tradeability_mfe_r == 9.0 / 6.0
    assert outcome.tradeability_endpoint_r == 9.0 / 6.0
    assert outcome.bars_to_trigger == 1


def test_tradeability_r_is_unavailable_when_setup_never_reached_tradeable():
    observations = [
        observation(0, LifecycleState.ARMED),
        observation(1, LifecycleState.NOT_TRADEABLE, tradeability_state="NOT_TRADEABLE"),
    ]
    outcomes = calculate_outcomes(
        observations + [observation(2, LifecycleState.TRIGGERED)],
        bars((99, 100, 96, 99), (100, 102, 96, 101), (100, 102, 94, 95)),
        [result(False), result(True), result(False)],
    )

    assert outcomes[0].signal_endpoint_r == -1.0
    assert outcomes[0].tradeability_risk is None
    assert outcomes[0].tradeability_endpoint_r is None


def test_false_trigger_and_invalidation_before_trigger_are_distinct():
    triggered_observations = [
        observation(0, LifecycleState.ARMED),
        observation(1, LifecycleState.TRIGGERED),
        observation(2, LifecycleState.TRIGGERED),
    ]
    triggered = calculate_outcomes(
        triggered_observations,
        bars((99, 100, 96, 99), (100, 101, 96, 100), (100, 101, 94, 95)),
        [result(False), result(True), result(False)],
    )[0]
    untriggered = calculate_outcomes(
        [observation(0, LifecycleState.ARMED)],
        bars((99, 100, 94, 95)),
        [result(False)],
    )[0]

    assert triggered.outcome == "FALSE_TRIGGER"
    assert triggered.false_trigger is True
    assert triggered.invalidation_before_trigger is False
    assert untriggered.outcome == "NO_TRIGGER"
    assert untriggered.invalidation_before_trigger is True
    assert untriggered.signal_endpoint_r is None


def test_same_bar_target_and_invalidation_is_conservatively_invalidation_first():
    observations = [observation(0, LifecycleState.TRIGGERED)]
    outcome = calculate_outcomes(
        observations,
        bars((100, 111, 94, 100)),
        [result(True, [110.0], gap_triggered=True)],
    )[0]

    assert outcome.outcome == "FALSE_TRIGGER"
    assert outcome.ambiguous_same_bar is True
    assert outcome.signal_endpoint_r == -1.0
    assert outcome.signal_mfe_r == 0.0


def test_segment_summaries_include_required_dimensions():
    observations = [
        observation(0, LifecycleState.ARMED),
        observation(1, LifecycleState.TRIGGERED),
        observation(2, LifecycleState.TRIGGERED),
    ]
    outcomes = calculate_outcomes(
        observations,
        bars((99, 100, 96, 99), (100, 101, 96, 100), (100, 101, 94, 95)),
        [result(False), result(True), result(False)],
    )
    summaries = segment_outcomes(outcomes)

    assert {summary.segment for summary in summaries} == {
        "playbook",
        "market_regime",
        "direction",
        "evidence_coverage",
        "session_regime",
        "volatility_regime",
    }
    playbook = next(summary for summary in summaries if summary.segment == "playbook")
    assert playbook.false_trigger_rate == 1.0


def test_close_confirmed_trigger_does_not_consume_trigger_bar_excursions():
    observations = [
        observation(0, LifecycleState.ARMED),
        observation(1, LifecycleState.TRIGGERED),
        observation(2, LifecycleState.TRIGGERED),
    ]
    outcome = calculate_outcomes(
        observations,
        bars((99, 100, 96, 99), (100, 120, 94, 101), (101, 104, 99, 103)),
        [result(False), result(True, [110.0]), result(False)],
    )[0]

    assert outcome.outcome == "OPEN_AT_SESSION_END"
    assert outcome.signal_mfe == 4.0
    assert outcome.signal_mae == 1.0


def test_lifecycle_termination_stops_outcome_measurement():
    observations = [
        observation(0, LifecycleState.ARMED),
        observation(1, LifecycleState.TRIGGERED),
        observation(2, LifecycleState.NO_SETUP),
    ]
    outcome = calculate_outcomes(
        observations,
        bars((99, 100, 96, 99), (100, 101, 99, 100), (100, 111, 99, 110)),
        [result(False), result(True, [110.0]), result(False)],
    )[0]

    assert outcome.outcome == "OPEN_AT_LIFECYCLE_END"
    assert outcome.ended_at == observations[1].timestamp
    assert outcome.signal_endpoint_r == 0.0


def test_watch_time_counts_but_missing_armed_does_not_fabricate_trigger_duration():
    observations = [
        observation(0, LifecycleState.WATCH),
        observation(1, LifecycleState.TRIGGERED),
    ]
    outcome = calculate_outcomes(
        observations,
        bars((99, 100, 96, 99), (100, 101, 99, 100)),
        [result(False), result(True)],
    )[0]

    assert outcome.setup_started_at == observations[0].timestamp
    assert outcome.armed_at is None
    assert outcome.bars_to_trigger is None
    assert outcome.bars_in_setup == 2


def test_watch_to_armed_preserves_setup_start_when_levels_appear_later():
    observations = [
        observation(0, LifecycleState.WATCH).model_copy(
            update={"trigger_price": None, "invalidation_price": None}
        ),
        observation(1, LifecycleState.ARMED),
        observation(2, LifecycleState.ARMED),
        observation(3, LifecycleState.TRIGGERED),
    ]
    outcome = calculate_outcomes(
        observations,
        bars(
            (99, 100, 96, 99),
            (99, 100, 96, 99),
            (99, 100, 96, 99),
            (100, 101, 99, 100),
        ),
        [result(False), result(False), result(False), result(True)],
    )[0]

    assert outcome.setup_started_at == observations[0].timestamp
    assert outcome.armed_at == observations[1].timestamp
    assert outcome.bars_to_trigger == 2
    assert outcome.bars_in_setup == 4


def test_active_setup_at_dataset_end_is_open_at_session_end():
    observations = [
        observation(0, LifecycleState.ARMED),
        observation(1, LifecycleState.TRIGGERED),
    ]
    outcome = calculate_outcomes(
        observations,
        bars((99, 100, 96, 99), (100, 101, 99, 100)),
        [result(False), result(True)],
    )[0]

    assert outcome.outcome == "OPEN_AT_SESSION_END"


def test_tradeability_target_must_be_beyond_tradeability_entry():
    observations = [
        observation(0, LifecycleState.ARMED),
        observation(
            1,
            LifecycleState.TRADEABLE,
            tradeability_state="TRADEABLE",
            tradeability_entry=106.0,
        ),
        observation(2, LifecycleState.TRADEABLE, tradeability_state="TRADEABLE"),
    ]
    outcome = calculate_outcomes(
        observations,
        bars((99, 100, 96, 99), (100, 106, 99, 106), (106, 108, 103, 107)),
        [result(False), result(True, [105.0]), result(False)],
    )[0]

    assert outcome.target_price == 105.0
    assert outcome.tradeability_target_price is None


def test_bearish_r_math_uses_downward_favorable_excursion():
    bearish = [
        observation(0, LifecycleState.ARMED).model_copy(
            update={"direction_label": "BEARISH", "trigger_price": 100.0, "invalidation_price": 105.0}
        ),
        observation(1, LifecycleState.TRIGGERED).model_copy(
            update={"direction_label": "BEARISH", "trigger_price": 100.0, "invalidation_price": 105.0}
        ),
        observation(2, LifecycleState.TRIGGERED).model_copy(
            update={"direction_label": "BEARISH", "trigger_price": 100.0, "invalidation_price": 105.0}
        ),
    ]
    bearish_result = result(True, [90.0])
    bearish_result.trigger.direction = "BEARISH"
    outcome = calculate_outcomes(
        bearish,
        bars((101, 103, 99, 101), (100, 102, 98, 99), (99, 101, 89, 90)),
        [result(False), bearish_result, result(False)],
    )[0]

    assert outcome.outcome == "TARGET_HIT"
    assert outcome.signal_endpoint_r == 2.0


def test_observation_marks_unreached_downstream_stages_unavailable():
    result_model = QXEvaluationResult(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=START,
        publication_state=PublicationState.RESEARCH_ONLY,
        current_lifecycle_state=LifecycleState.NO_SETUP,
        config_version="research_v1",
        stage_latencies={
            "options_expression_ms": SKIPPED,
            "portfolio_risk_ms": SKIPPED,
        },
    )

    replay_observation = observation_from_result(result_model)

    assert replay_observation.options_state == "UNAVAILABLE"
    assert replay_observation.portfolio_state == "UNAVAILABLE"
    assert replay_observation.stage_latencies["options_expression_ms"] == SKIPPED
    assert replay_observation.stage_latencies["portfolio_risk_ms"] == SKIPPED


def test_observation_persists_consumed_snapshot_provenance():
    result_model = QXEvaluationResult(
        symbol="SPY",
        timeframe="5m",
        evaluation_timestamp=START,
        publication_state=PublicationState.RESEARCH_ONLY,
        current_lifecycle_state=LifecycleState.BLOCKED,
        config_version="research_v1",
        data_dependencies={
            "option_chain": DataDependencyStatus(
                name="option_chain", available=True, source="schwab", snapshot_id=11
            ),
            "account_snapshot": DataDependencyStatus(
                name="account_snapshot",
                available=True,
                source="schwab_read_only",
                snapshot_id=22,
            ),
        },
    )

    replay_observation = observation_from_result(result_model)

    assert replay_observation.option_snapshot_id == 11
    assert replay_observation.account_snapshot_id == 22
    assert replay_observation.option_snapshot_source == "schwab"
    assert replay_observation.account_snapshot_source == "schwab_read_only"


def test_downstream_blocked_state_preserves_trigger_outcome_measurement():
    blocked = observation(1, LifecycleState.BLOCKED)
    outcome = calculate_outcomes(
        [observation(0, LifecycleState.ARMED), blocked],
        bars((99, 100, 96, 99), (100, 101, 99, 100)),
        [result(False), result(True)],
    )[0]

    assert outcome.triggered_at == blocked.timestamp
    assert outcome.outcome == "OPEN_AT_SESSION_END"


def test_replay_repository_persists_core_v1_records(tmp_path: Path):
    replay_observation = observation(0, LifecycleState.NO_SETUP)
    report = ReplayReport(
        symbol="SPY",
        timeframe="5m",
        started_at=START,
        completed_at=START + timedelta(seconds=1),
        observations=[replay_observation],
        transitions=[
            ReplayTransitionRecord(
                timestamp=START,
                previous_state=LifecycleState.WATCH,
                new_state=LifecycleState.NO_SETUP,
            )
        ],
        outcomes=[],
        segments=[],
    )
    database = tmp_path / "replay.db"

    run_id = ReplayRepository(database).save(report)

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT pipeline_version, observation_count, transition_count FROM replay_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        observation_count = connection.execute(
            "SELECT COUNT(*) FROM replay_observations WHERE replay_run_id = ?", (run_id,)
        ).fetchone()[0]
    assert row == ("core_v1", 1, 1)
    assert observation_count == 1
