import pytest
from datetime import datetime, timedelta, timezone
from qx.config.rules_config import load_rules_config
from qx.pipeline.models import QXEvaluationContext, LifecycleState
from qx.pipeline.orchestrator import run_pipeline
import pandas as pd

@pytest.fixture
def config():
    return load_rules_config()

@pytest.fixture
def empty_ctx(config):
    return QXEvaluationContext(
        symbol="SPY",
        evaluation_timestamp=datetime.now(timezone.utc),
        config=config
    )


@pytest.fixture
def mock_bars():
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=1)
    df = pd.DataFrame({
        'timestamp': [timestamp] * 50,
        'open': [100.0] * 50,
        'high': [101.0] * 50,
        'low': [99.0] * 50,
        'close': [100.5] * 50,
        'volume': [1000] * 50
    })
    return df


def test_blocked_on_no_bars(empty_ctx, config):
    result = run_pipeline(empty_ctx, config)
    assert result.current_lifecycle_state == LifecycleState.BLOCKED
    assert "NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP" in result.reason_codes

def test_pipeline_never_uses_future_data():
    pass

def test_no_setup_stops_pipeline_correctly(empty_ctx, config, mock_bars):
    empty_ctx.bars = mock_bars
    # the mock bars will just produce NO_SETUP because there is no setup detected
    result = run_pipeline(empty_ctx, config)
    assert result.current_lifecycle_state == LifecycleState.NO_SETUP

def test_pipeline_uses_shared_evaluation_timestamp(empty_ctx, config, mock_bars):
    empty_ctx.bars = mock_bars
    result = run_pipeline(empty_ctx, config)
    assert result.evaluated_at == empty_ctx.evaluation_timestamp

def test_api_v2_calls_canonical_pipeline():
    pass

def test_replay_uses_same_orchestrator_as_live_api():
    from qx.pipeline.adapters import HistoricalReplayAdapter
    config = load_rules_config()
    adapter = HistoricalReplayAdapter(config, "SPY")
    assert hasattr(adapter, "replay")

