from datetime import datetime, timedelta
from typing import Any, List, Optional, Sequence

import pandas as pd

from qx.config.rules_config import RulesEngineConfig
from qx.options_expression.models import OptionsContext
from qx.pipeline import orchestrator
from qx.pipeline.models import (
    DataDependencyStatus,
    PIPELINE_VERSION,
    LifecycleState,
    QXEvaluationContext,
    QXEvaluationResult,
)
from qx.pipeline.multi_timeframe import bar_completion_timestamp
from qx.pipeline.point_in_time import (
    bar_timestamp,
    filter_bars_at_or_before,
    latest_visible_snapshot,
    parse_timestamp,
)
from qx.playbooks.base import PlaybookEvaluation
from qx.portfolio.models import AccountRiskContext


class ReplayTransition:
    def __init__(
        self,
        timestamp: datetime,
        previous_state: LifecycleState,
        new_state: LifecycleState,
        result: QXEvaluationResult,
    ) -> None:
        self.timestamp = timestamp
        self.previous_state = previous_state
        self.new_state = new_state
        self.result = result
        self.pipeline_version = result.pipeline_version


def _bar_timestamp(bar: Any) -> datetime:
    timestamp = bar_timestamp(bar)
    if timestamp is not None:
        return timestamp
    raise ValueError("Historical replay bars require an explicit point-in-time timestamp")


def _bar_completion_timestamp(bar: Any, timeframe: str) -> datetime:
    return bar_completion_timestamp(bar, timeframe)


class HistoricalReplayAdapter:
    pipeline_version = PIPELINE_VERSION

    def __init__(
        self,
        config: RulesEngineConfig,
        symbol: str,
        timeframe: str = "5m",
        horizon: Optional[str] = None,
    ) -> None:
        self.config = config
        self.symbol = symbol.upper()
        self.timeframe = timeframe
        self.horizon = horizon
        self.history: List[ReplayTransition] = []
        self.results: List[QXEvaluationResult] = []
        self.current_state = LifecycleState.NO_SETUP

    def replay(
        self,
        historical_bars: Sequence[Any] | pd.DataFrame,
        warmup_bars: int = 50,
        option_chain_snapshots: Optional[Sequence[OptionsContext]] = None,
        account_snapshots: Optional[Sequence[AccountRiskContext]] = None,
        htf_bars: Optional[Sequence[Any] | pd.DataFrame] = None,
    ) -> List[QXEvaluationResult]:
        self.history = []
        self.results = []
        self.current_state = LifecycleState.NO_SETUP
        armed_playbook: Optional[PlaybookEvaluation] = None
        previous_market_driver: Any = None

        if len(historical_bars) <= warmup_bars:
            return []

        for index in range(warmup_bars, len(historical_bars)):
            candidate_bars = historical_bars.iloc[: index + 1].copy() if isinstance(
                historical_bars, pd.DataFrame
            ) else list(historical_bars[: index + 1])
            current_bar = (
                candidate_bars.iloc[-1]
                if isinstance(candidate_bars, pd.DataFrame)
                else candidate_bars[-1]
            )
            evaluation_timestamp = _bar_completion_timestamp(current_bar, self.timeframe)
            visible_bars = filter_bars_at_or_before(candidate_bars, evaluation_timestamp)
            option_chain = latest_visible_snapshot(
                option_chain_snapshots,
                evaluation_timestamp,
                "data_as_of",
            )
            account_snapshot = latest_visible_snapshot(
                account_snapshots,
                evaluation_timestamp,
                "data_as_of",
            )
            dependencies = {
                "option_chain": _snapshot_dependency("option_chain", option_chain),
                "account_snapshot": _snapshot_dependency(
                    "account_snapshot", account_snapshot
                ),
            }

            context = QXEvaluationContext(
                symbol=self.symbol,
                timeframe=self.timeframe,
                horizon=self.horizon,
                evaluation_timestamp=evaluation_timestamp,
                bars=visible_bars,
                htf_bars=htf_bars,
                armed_playbook=armed_playbook,
                option_chain=option_chain,
                account_snapshot=account_snapshot,
                data_dependencies=dependencies,
                previous_market_driver=previous_market_driver,
                config_version=self.config.version,
                config=self.config,
            )
            result = orchestrator.run_pipeline(context, self.config)
            self.results.append(result)
            previous_market_driver = result.market_driver

            if result.current_lifecycle_state != self.current_state:
                self.history.append(
                    ReplayTransition(
                        timestamp=evaluation_timestamp,
                        previous_state=self.current_state,
                        new_state=result.current_lifecycle_state,
                        result=result,
                    )
                )
                self.current_state = result.current_lifecycle_state

            armed_playbook = (
                result.primary_playbook_candidate
                if result.current_lifecycle_state == LifecycleState.ARMED
                else None
            )

        return self.results


def _snapshot_dependency(name: str, snapshot: Any) -> DataDependencyStatus:
    if snapshot is None:
        return DataDependencyStatus(
            name=name,
            reason_code=f"{name.upper()}_UNAVAILABLE_AT_EVALUATION_TIMESTAMP",
        )
    source = getattr(snapshot, "source", None) or getattr(
        snapshot, "broker_provenance", "UNAVAILABLE"
    )
    freshness = getattr(snapshot, "freshness", "UNAVAILABLE")
    return DataDependencyStatus(
        name=name,
        available=True,
        source=str(source),
        data_as_of=parse_timestamp(getattr(snapshot, "data_as_of", None)),
        freshness=str(getattr(freshness, "value", freshness)),
        publication_state=str(getattr(snapshot, "publication_state", "BLOCKED")),
        sync_status=str(getattr(snapshot, "sync_status", "UNAVAILABLE")),
        cache_status="HIT",
        snapshot_id=getattr(snapshot, "snapshot_id", None),
    )
