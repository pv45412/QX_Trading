from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from qx.pipeline.models import LifecycleState


class ObservationMode(str, Enum):
    LIVE = "LIVE"
    SHADOW = "SHADOW"
    REPLAY = "REPLAY"
    RESEARCH = "RESEARCH"
    FIXTURE = "FIXTURE"


class PublicationCommandState(str, Enum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    ABANDONED = "ABANDONED"


class OpportunityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    idempotency_key: str
    schema_version: Literal["qx.opportunity-record.v1"] = "qx.opportunity-record.v1"
    observation_mode: ObservationMode = ObservationMode.LIVE
    environment_id: str
    producer_id: str
    producer_run_id: str
    symbol: str
    timeframe: str
    horizon_context: str | None = None
    evaluation_timestamp: datetime
    request_started_at: datetime | None = None
    recorded_at: datetime
    expires_at: datetime
    freshness_policy_version: str
    publication_state: str
    lifecycle_state: LifecycleState
    pipeline_version: str
    config_version: str
    engine_versions: dict[str, str] = Field(default_factory=dict)
    direction: str | None = None
    primary_playbook_id: str | None = None
    source_setup_reference: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    evidence_coverage: float | None = None
    coverage_status: str | None = None
    data_dependencies: dict[str, Any] = Field(default_factory=dict)
    market_driver: dict[str, Any] | None = None
    decision_payload: dict[str, Any]
    input_fingerprint: str
    bar_window_sha256: str
    result_sha256: str
    stream_key: str
    supersedes_evaluation_id: str | None = None


class OpportunityListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    source_mode: ObservationMode
    symbol: str
    timeframe: str
    horizon_context: str | None = None
    evaluation_timestamp: datetime
    recorded_at: datetime
    expires_at: datetime
    publication_state: str
    lifecycle_state: LifecycleState
    pipeline_version: str
    config_version: str
    direction: str | None = None
    primary_playbook_id: str | None = None
    trigger: float | None = None
    trigger_source: str | None = None
    invalidation: float | None = None
    tradeability_state: str | None = None
    options_state: str | None = None
    portfolio_state: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    evidence_coverage: float | None = None
    coverage_status: str | None = None
    data_dependencies: dict[str, Any] = Field(default_factory=dict)
    market_driver: dict[str, Any] | None = None
    visibility_state: str = "CURRENT"


class OpportunityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "qx.opportunity-list.v1"
    pipeline_version: str = "core_v1"
    generated_at: datetime
    query_as_of: datetime
    source_mode: ObservationMode = ObservationMode.LIVE
    items: list[OpportunityListItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class OpportunityDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "qx.opportunity-detail.v1"
    evaluation_id: str
    source_mode: ObservationMode = ObservationMode.LIVE
    symbol: str
    timeframe: str
    horizon_context: str | None = None
    evaluation_timestamp: datetime
    request_started_at: datetime | None = None
    recorded_at: datetime
    expires_at: datetime
    freshness_policy_version: str
    publication_state: str
    lifecycle_state: LifecycleState
    pipeline_version: str
    config_version: str
    engine_versions: dict[str, str] = Field(default_factory=dict)
    input_fingerprint: str
    result_sha256: str
    decision: dict[str, Any]
