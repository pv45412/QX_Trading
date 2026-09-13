"""Persisted, source-qualified snapshots for the read-only futures workspace."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, cast

from qx.market.regime import MarketRegimeResult
from qx.market.spx_dashboard import (
    DecisionLevelSet,
    FuturesContextRow,
    FuturesTimingRow,
    OpeningGapRead,
    SpxDashboard,
    TradingPlan,
)


@dataclass(frozen=True)
class FuturesContextSnapshot:
    schema_version: int
    period: str
    requested_source: str
    retrieved_at: str
    dashboard: SpxDashboard


def save_futures_context_snapshot(
    dashboard: SpxDashboard, path: Path, *, period: str, requested_source: str,
    now: datetime | None = None,
) -> FuturesContextSnapshot:
    snapshot = FuturesContextSnapshot(
        schema_version=1,
        period=period,
        requested_source=requested_source.strip().lower(),
        retrieved_at=(now or datetime.now(timezone.utc)).isoformat(),
        dashboard=dashboard,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**asdict(snapshot), "dashboard": asdict(dashboard)}, separators=(",", ":")), encoding="utf-8")
    return snapshot


def load_futures_context_snapshot(path: Path) -> FuturesContextSnapshot:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("Unsupported futures snapshot schema")
        dashboard_raw = raw["dashboard"]
        if not isinstance(dashboard_raw, dict):
            raise ValueError("Futures snapshot dashboard is missing")
        snapshot = FuturesContextSnapshot(
            schema_version=1,
            period=str(raw["period"]),
            requested_source=str(raw["requested_source"]).strip().lower(),
            retrieved_at=str(raw["retrieved_at"]),
            dashboard=_dashboard_from_payload(dashboard_raw),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid futures context snapshot") from exc
    if not snapshot.period or not snapshot.requested_source:
        raise ValueError("Invalid futures context snapshot")
    return snapshot


def _dashboard_from_payload(raw: dict[str, object]) -> SpxDashboard:
    values: dict[str, Any] = dict(raw)
    values["regime"] = MarketRegimeResult(**cast(Any, _mapping(values["regime"])))
    values["spy_levels"] = DecisionLevelSet(**cast(Any, _mapping(values["spy_levels"])))
    values["es_levels"] = DecisionLevelSet(**cast(Any, _mapping(values["es_levels"])))
    values["nq_levels"] = DecisionLevelSet(**cast(Any, _mapping(values["nq_levels"])))
    values["futures_rows"] = [FuturesContextRow(**cast(Any, _mapping(row))) for row in _list(values["futures_rows"])]
    values["decision_level_sets"] = [DecisionLevelSet(**cast(Any, _mapping(row))) for row in _list(values["decision_level_sets"])]
    values["trading_plan"] = TradingPlan(**cast(Any, _mapping(values["trading_plan"])))
    values["timing_rows"] = [FuturesTimingRow(**cast(Any, _mapping(row))) for row in _list(values["timing_rows"])]
    values["opening_gap"] = OpeningGapRead(**cast(Any, _mapping(values["opening_gap"])))
    return SpxDashboard(**cast(Any, values))


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Invalid futures snapshot object")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Invalid futures snapshot list")
    return value
