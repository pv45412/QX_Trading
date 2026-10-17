"""Read-only live market quote API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from qx.config.rules_config import RulesEngineConfig, load_rules_config
from qx.data.quotes import QuoteProvider, QuoteSnapshot


logger = logging.getLogger(__name__)

SUPPORTED_SYMBOLS = frozenset({"SPY", "QQQ", "SPX"})


class MarketQuoteFieldEvidence(BaseModel):
    availability: Literal["AVAILABLE", "NOT_PUBLISHED", "UNAVAILABLE"]
    source: str
    reason_code: str | None = None


class MarketQuoteFieldEvidenceSet(BaseModel):
    last: MarketQuoteFieldEvidence
    bid: MarketQuoteFieldEvidence
    ask: MarketQuoteFieldEvidence
    change_pct: MarketQuoteFieldEvidence
    volume: MarketQuoteFieldEvidence


class MarketQuoteResponse(BaseModel):
    symbol: str
    resolved_symbol: str | None
    asset_type: str | None
    source: str
    status: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    last: float | None
    bid: float | None
    ask: float | None
    change_pct: float | None
    volume: float | None
    quote_timestamp: datetime | None
    trade_timestamp: datetime | None
    realtime: bool | None
    retrieved_at: datetime
    age_seconds: float | None
    freshness: Literal["FRESH", "STALE", "UNAVAILABLE"]
    field_evidence: MarketQuoteFieldEvidenceSet


def create_market_quotes_router(
    provider: QuoteProvider | None,
    *,
    config: RulesEngineConfig | None = None,
    now: Callable[[], datetime] | None = None,
) -> APIRouter:
    router = APIRouter()
    resolved_config = config or load_rules_config()
    clock = now or (lambda: datetime.now(timezone.utc))
    max_age_seconds = resolved_config.direction_engine.freshness.quote_max_age_seconds

    @router.get(
        "/api/v2/market/quote/{symbol}",
        response_model=MarketQuoteResponse,
    )
    def market_quote(symbol: str) -> MarketQuoteResponse:
        canonical_symbol = symbol.strip().upper()
        if canonical_symbol not in SUPPORTED_SYMBOLS:
            raise HTTPException(status_code=404, detail="Unsupported market quote symbol.")
        if provider is None:
            raise _provider_unavailable(canonical_symbol)

        try:
            quote = provider.get_quote(canonical_symbol)
            _validate_quote_identity(quote, canonical_symbol)
        except Exception as exc:
            logger.warning(
                "Market quote provider unavailable for %s (%s)",
                canonical_symbol,
                type(exc).__name__,
            )
            raise _provider_unavailable(canonical_symbol) from None

        retrieved_at = _as_utc(clock())
        age_seconds, freshness = _quote_freshness(
            quote.timestamp,
            retrieved_at,
            max_age_seconds=max_age_seconds,
        )
        return MarketQuoteResponse(
            symbol=canonical_symbol,
            resolved_symbol=quote.resolved_symbol,
            asset_type=quote.asset_type,
            source=quote.provider,
            status=_quote_status(quote),
            last=quote.last,
            bid=quote.bid,
            ask=quote.ask,
            change_pct=quote.change_pct,
            volume=quote.volume,
            quote_timestamp=_optional_utc(quote.timestamp),
            trade_timestamp=_optional_utc(quote.trade_timestamp),
            realtime=quote.realtime,
            retrieved_at=retrieved_at,
            age_seconds=age_seconds,
            freshness=freshness,
            field_evidence=_field_evidence(quote),
        )

    return router


def _quote_status(
    quote: QuoteSnapshot,
) -> Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]:
    timestamp = _optional_utc(quote.timestamp)
    if quote.last is not None and timestamp is not None:
        return "AVAILABLE"
    if any(
        value is not None
        for value in (
            quote.last,
            quote.bid,
            quote.ask,
            quote.change_pct,
            quote.volume,
            timestamp,
            _optional_utc(quote.trade_timestamp),
        )
    ):
        return "PARTIAL"
    return "UNAVAILABLE"


def _field_evidence(quote: QuoteSnapshot) -> MarketQuoteFieldEvidenceSet:
    return MarketQuoteFieldEvidenceSet(
        last=_field_state(quote, "last", quote.last),
        bid=_field_state(quote, "bid", quote.bid),
        ask=_field_state(quote, "ask", quote.ask),
        change_pct=_field_state(quote, "change_pct", quote.change_pct),
        volume=_field_state(quote, "volume", quote.volume),
    )


def _field_state(
    quote: QuoteSnapshot,
    field: str,
    value: float | None,
) -> MarketQuoteFieldEvidence:
    if value is not None:
        return MarketQuoteFieldEvidence(availability="AVAILABLE", source=quote.provider)
    if field in {"bid", "ask"} and (quote.asset_type or "").strip().upper() == "INDEX":
        return MarketQuoteFieldEvidence(
            availability="NOT_PUBLISHED",
            source=quote.provider,
            reason_code="INDEX_NO_EXECUTABLE_ORDER_BOOK",
        )
    return MarketQuoteFieldEvidence(
        availability="UNAVAILABLE",
        source=quote.provider,
        reason_code="SOURCE_FIELD_UNAVAILABLE",
    )


def _validate_quote_identity(quote: QuoteSnapshot, symbol: str) -> None:
    if quote.symbol.strip().upper() != symbol or not quote.provider.strip():
        raise ValueError("Market quote identity unavailable.")


def _quote_freshness(
    timestamp: datetime | None,
    retrieved_at: datetime,
    *,
    max_age_seconds: float,
) -> tuple[float | None, Literal["FRESH", "STALE", "UNAVAILABLE"]]:
    normalized_timestamp = _optional_utc(timestamp)
    if normalized_timestamp is None:
        return None, "UNAVAILABLE"
    age_seconds = (retrieved_at - normalized_timestamp).total_seconds()
    if age_seconds < 0:
        return None, "UNAVAILABLE"
    return (
        age_seconds,
        "FRESH" if age_seconds <= max_age_seconds else "STALE",
    )


def _optional_utc(value: datetime | None) -> datetime | None:
    if value is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    normalized = _optional_utc(value)
    if normalized is None:
        raise ValueError("Clock must return a timezone-aware timestamp.")
    return normalized


def _provider_unavailable(symbol: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"status": "UNAVAILABLE", "symbol": symbol},
    )
