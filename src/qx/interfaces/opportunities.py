from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, Response

from qx.opportunities.identity import canonical_json_bytes
from qx.opportunities.repository import (
    OpportunityIntegrityError,
    OpportunityRepository,
    OpportunityRepositoryError,
)
from qx.pipeline.models import LifecycleState


EVALUATION_ID_PATTERN = re.compile(r"^qxev1_[0-9a-f]{32}$")
OPPORTUNITY_STORE_SCHEMA_INVALID = "OPPORTUNITY_STORE_SCHEMA_INVALID"
OPPORTUNITY_STORE_UNAVAILABLE = "OPPORTUNITY_STORE_UNAVAILABLE"


def create_unavailable_opportunity_router(reason_code: str) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/qx/opportunities")
    def list_opportunities_unavailable() -> None:
        raise HTTPException(status_code=503, detail={"code": reason_code})

    @router.get("/api/v2/qx/opportunities/{evaluation_id}")
    def get_opportunity_unavailable(evaluation_id: str) -> None:
        del evaluation_id
        raise HTTPException(status_code=503, detail={"code": reason_code})

    return router


def create_opportunity_router(
    repository: OpportunityRepository,
    *,
    environment_id: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/qx/opportunities")
    def list_opportunities(
        symbols: list[str] | None = Query(default=None, max_length=100),
        timeframe: str | None = None,
        states: list[str] | None = Query(default=None),
        publication_states: list[str] | None = Query(default=None),
        direction: str | None = None,
        playbook_id: str | None = None,
        horizon_context: str | None = None,
        query_as_of: datetime | None = None,
        evaluated_after: datetime | None = None,
        evaluated_before: datetime | None = None,
        knowledge_as_of: datetime | None = None,
        include_terminal: bool = False,
        include_blocked: bool = False,
        fresh_only: bool = True,
        limit: int = Query(default=25, ge=1, le=100),
        cursor: str | None = None,
        if_none_match: str | None = Header(default=None),
    ) -> Response:
        if query_as_of is not None and evaluated_before is not None:
            if _aware(query_as_of) != _aware(evaluated_before):
                raise HTTPException(
                    status_code=422,
                    detail="query_as_of and evaluated_before must match when both are supplied",
                )
        timestamp = _aware(evaluated_before or query_as_of or datetime.now(timezone.utc))
        allowed_states = {state.value for state in LifecycleState}
        if any(state not in allowed_states for state in states or ()):
            raise HTTPException(status_code=422, detail="Invalid lifecycle state filter")
        if any(
            state not in {"VERIFIED", "RESEARCH_ONLY", "BLOCKED"}
            for state in publication_states or ()
        ):
            raise HTTPException(status_code=422, detail="Invalid publication state filter")
        try:
            result = repository.list_latest(
                environment_id=environment_id,
                query_as_of=timestamp,
                knowledge_as_of=knowledge_as_of,
                evaluated_after=evaluated_after,
                symbols=symbols or (),
                timeframe=timeframe,
                states=states or (),
                publication_states=publication_states or (),
                direction=direction,
                playbook_id=playbook_id,
                horizon_context=horizon_context,
                include_terminal=include_terminal,
                include_blocked=include_blocked,
                fresh_only=fresh_only,
                limit=limit,
                cursor=cursor,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OpportunityIntegrityError as exc:
            raise HTTPException(status_code=409, detail="Opportunity record integrity conflict") from exc
        except OpportunityRepositoryError as exc:
            raise HTTPException(status_code=503, detail="Opportunity store unavailable") from exc
        return _deterministic_response(result.model_dump(mode="json"), if_none_match)

    @router.get("/api/v2/qx/opportunities/{evaluation_id}")
    def get_opportunity(
        evaluation_id: str,
        if_none_match: str | None = Header(default=None),
    ) -> Response:
        if not EVALUATION_ID_PATTERN.fullmatch(evaluation_id):
            raise HTTPException(status_code=422, detail="Malformed evaluation identity")
        try:
            result = repository.get_detail(evaluation_id, environment_id=environment_id)
        except OpportunityIntegrityError as exc:
            raise HTTPException(status_code=409, detail="Opportunity record integrity conflict") from exc
        except OpportunityRepositoryError as exc:
            raise HTTPException(status_code=503, detail="Opportunity store unavailable") from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Opportunity evaluation not found")
        return _deterministic_response(result.model_dump(mode="json"), if_none_match)

    return router


def _deterministic_response(payload: object, if_none_match: str | None) -> Response:
    body = canonical_json_bytes(payload)
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": "private, must-revalidate"}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
