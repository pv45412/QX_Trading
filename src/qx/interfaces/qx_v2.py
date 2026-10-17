"""Legacy-free FastAPI router for the canonical QX pipeline."""

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter

from qx.config.rules_config import load_rules_config
from qx.data.providers import MarketDataProvider
from qx.opportunities.publisher import OpportunityPublicationError, OpportunityPublisher
from qx.opportunities.repository import OpportunityRepositoryError, ReservationInProgress
from qx.pipeline import orchestrator
from qx.pipeline.market_data_quality import (
    BarLoadOutcome,
    INTRADAY_MINUTES,
    canonical_timeframe,
    exact_cache_candidates,
    load_audited_bars,
    load_live_audited_bars,
)
from qx.pipeline.models import QXEvaluationContext, QXEvaluationResult
from qx.pipeline.models import DataDependencyStatus, ExternalIOMetric
from qx.pipeline.multi_timeframe import (
    aggregate_daily_bars_to_weekly,
    resolve_horizon_for_timeframe,
    resolve_timeframes_for_horizon,
)
from qx.pipeline.point_in_time import (
    aware_utc,
    bar_timestamp,
    parse_timestamp,
)
from qx.pipeline.providers import (
    CanonicalAccountSnapshotProvider,
    CanonicalOptionChainSnapshotProvider,
)
from qx.pipeline.snapshot_store import (
    CanonicalSnapshotRepository,
    sanitize_account_snapshot,
)
from qx.options_expression.models import OptionsContext
from qx.portfolio.models import AccountRiskContext, FreshnessState
from qx.portfolio.workspace import (
    PortfolioWorkspaceResponse,
    build_portfolio_workspace_response,
)


logger = logging.getLogger(__name__)


def _cache_candidates(cache_dir: Path, symbol: str, timeframe: str) -> list[Path]:
    return exact_cache_candidates(cache_dir, symbol, timeframe)


def load_pipeline_bars(
    cache_dir: Path,
    symbol: str,
    timeframe: str,
    evaluation_timestamp: datetime,
    active_cache_dir: Optional[Path] = None,
) -> BarLoadOutcome:
    return load_audited_bars(
        cache_dir,
        symbol,
        timeframe,
        evaluation_timestamp,
        active_cache_dir,
    )


def _live_publication_run_id(timestamp: datetime, timeframe: str) -> str:
    normalized = canonical_timeframe(timeframe) or timeframe.strip().lower()
    current = aware_utc(timestamp).replace(second=0, microsecond=0)
    if normalized.endswith("m") and normalized[:-1].isdigit():
        minutes = max(1, int(normalized[:-1]))
        current = current.replace(minute=current.minute - (current.minute % minutes))
    elif normalized == "1h":
        current = current.replace(minute=0)
    elif normalized == "1d":
        current = current.replace(hour=0, minute=0)
    return f"live_mtf_v2:{normalized}:{current.isoformat()}"


def _opportunity_freshness_ttl(timeframe: str) -> timedelta:
    normalized = canonical_timeframe(timeframe)
    if normalized == "1d":
        return timedelta(hours=36)
    if normalized == "1h":
        return timedelta(hours=2)
    return timedelta(minutes=15)


def _context_bar_dependency(
    name: str,
    timeframe: str,
    bars: Any,
    outcome: BarLoadOutcome,
    *,
    derived_source: str | None = None,
) -> DataDependencyStatus:
    report = outcome.quality_report
    available = bars is not None and not getattr(bars, "empty", True)
    reason_code = None if available else (
        report.reason_codes[0] if report.reason_codes else "CONTEXT_BARS_UNAVAILABLE"
    )
    return DataDependencyStatus(
        name=name,
        available=available,
        source=derived_source or report.source_file or "live_market_data",
        data_as_of=report.data_as_of,
        freshness=(
            "POINT_IN_TIME"
            if available
            else "UNAVAILABLE"
        ),
        publication_state="RESEARCH_ONLY" if available else "BLOCKED",
        sync_status=report.status.value if available else "UNAVAILABLE",
        reason_code=reason_code,
        cache_status="BYPASS",
        quality_status=report.status.value,
        quality_reason_codes=report.reason_codes,
        requested_timeframe=timeframe,
        observed_timeframe=timeframe,
        bar_count=len(bars) if available else report.bar_count,
        usable_bar_count=len(bars) if available else report.usable_bar_count,
        incomplete_candle_count=report.incomplete_candle_count,
        retrieved_at=report.source_retrieved_at,
    )


def _load_live_context_bars(
    provider: MarketDataProvider,
    symbol: str,
    horizon: str,
    evaluation_timestamp: datetime,
    setup_timeframe: str,
    setup_outcome: BarLoadOutcome,
) -> tuple[Any, Any, dict[str, DataDependencyStatus], list[ExternalIOMetric], list[datetime]]:
    timeframe_map = resolve_timeframes_for_horizon(horizon)
    outcomes: dict[str, BarLoadOutcome] = {setup_timeframe: setup_outcome}
    metrics: list[ExternalIOMetric] = []
    retrieval_times: list[datetime] = []
    dependencies: dict[str, DataDependencyStatus] = {}
    weekly_bars = None

    def load(timeframe: str) -> tuple[Any, BarLoadOutcome, str | None]:
        nonlocal weekly_bars
        if timeframe == "1w":
            daily_bars, daily_outcome, _ = load("1d")
            if weekly_bars is None and daily_bars is not None:
                try:
                    weekly_bars = aggregate_daily_bars_to_weekly(daily_bars)
                except (TypeError, ValueError, KeyError):
                    weekly_bars = None
            source = daily_outcome.quality_report.source_file or "live_market_data"
            return weekly_bars, daily_outcome, f"{source}:1d->1w"

        normalized = canonical_timeframe(timeframe) or timeframe
        if normalized not in outcomes:
            outcome = load_live_audited_bars(
                provider,
                symbol,
                normalized,
                evaluation_timestamp,
            )
            outcomes[normalized] = outcome
            report = outcome.quality_report
            metrics.append(
                ExternalIOMetric(
                    operation=f"load_context_bars_{normalized}",
                    source=report.source_file or getattr(provider, "provider_name", "live_market_data"),
                    elapsed_ms=outcome.elapsed_ms,
                    calls=1,
                    cache_hits=outcome.cache_hits,
                    cache_misses=outcome.cache_misses,
                    status=report.status.value,
                )
            )
        outcome = outcomes[normalized]
        retrieved_at = outcome.quality_report.source_retrieved_at
        if retrieved_at is not None:
            retrieval_times.append(retrieved_at)
        return outcome.bars, outcome, None

    htf_timeframe = timeframe_map["htf"]
    macro_timeframe = timeframe_map["macro"]
    htf_bars, htf_outcome, htf_source = load(htf_timeframe)
    macro_bars, macro_outcome, macro_source = load(macro_timeframe)
    dependencies["htf_bars"] = _context_bar_dependency(
        "htf_bars", htf_timeframe, htf_bars, htf_outcome, derived_source=htf_source
    )
    dependencies["macro_bars"] = _context_bar_dependency(
        "macro_bars", macro_timeframe, macro_bars, macro_outcome, derived_source=macro_source
    )
    return htf_bars, macro_bars, dependencies, metrics, retrieval_times


def create_qx_v2_router(
    cache_dir: Path,
    active_cache_provider: Optional[Callable[[], Path]] = None,
    option_snapshot_provider: CanonicalOptionChainSnapshotProvider | None = None,
    account_snapshot_provider: CanonicalAccountSnapshotProvider | None = None,
    snapshot_repository: CanonicalSnapshotRepository | None = None,
    live_bar_provider: MarketDataProvider | None = None,
    opportunity_publisher: OpportunityPublisher | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v2/qx/evaluate/{symbol}", response_model=QXEvaluationResult)
    def evaluate_pipeline_v2(
        symbol: str,
        timeframe: str = "5m",
        evaluation_timestamp: datetime | None = None,
    ) -> QXEvaluationResult:
        request_started_at = datetime.now(timezone.utc)
        normalized_timeframe = canonical_timeframe(timeframe)
        publication_plan = None
        producer_id = "canonical_live_evaluation"
        producer_run_id = _live_publication_run_id(
            request_started_at,
            normalized_timeframe or timeframe,
        )
        if (
            evaluation_timestamp is None
            and opportunity_publisher is not None
            and normalized_timeframe is not None
        ):
            try:
                publication_plan = opportunity_publisher.reserve_publication(
                    producer_id=producer_id,
                    producer_run_id=producer_run_id,
                    symbol=symbol.upper(),
                    timeframe=normalized_timeframe,
                )
            except ReservationInProgress:
                logger.info(
                    "Canonical publication already running for %s %s",
                    symbol.upper(),
                    normalized_timeframe,
                )
            except OpportunityRepositoryError as exc:
                logger.warning(
                    "Canonical publication reservation unavailable: %s",
                    type(exc).__name__,
                )
            if publication_plan is not None and not publication_plan.should_execute:
                return QXEvaluationResult.model_validate(
                    publication_plan.existing_record.decision_payload
                )
        config = load_rules_config()
        io_metrics: list[ExternalIOMetric] = []
        dependencies: dict[str, DataDependencyStatus] = {}
        option_chain = None
        account_snapshot = None

        if evaluation_timestamp is not None:
            timestamp = aware_utc(evaluation_timestamp)
            option_chain, account_snapshot = _load_historical_snapshots(
                snapshot_repository,
                symbol,
                timestamp,
                dependencies,
                io_metrics,
            )
        else:
            option_chain, account_snapshot = _acquire_live_snapshots(
                snapshot_repository,
                option_snapshot_provider,
                account_snapshot_provider,
                symbol,
                dependencies,
                io_metrics,
            )
            timestamp = datetime.now(timezone.utc)
            visible_option = _visible_option(option_chain, timestamp)
            visible_account = _visible_account(account_snapshot, timestamp)
            if option_chain is not None and visible_option is None:
                dependencies["option_chain"] = _unavailable(
                    "option_chain", "OPTION_CHAIN_AFTER_EVALUATION_TIMESTAMP"
                )
            if account_snapshot is not None and visible_account is None:
                dependencies["account_snapshot"] = _unavailable(
                    "account_snapshot", "ACCOUNT_SNAPSHOT_AFTER_EVALUATION_TIMESTAMP"
                )
            option_chain = visible_option
            account_snapshot = visible_account
            option_chain = _age_option_snapshot(option_chain, timestamp)
            account_snapshot = _age_account_snapshot(account_snapshot, timestamp)
            if option_chain is not None:
                dependencies["option_chain"] = _option_dependency(option_chain, cache=False)
            if account_snapshot is not None:
                dependencies["account_snapshot"] = _account_dependency(
                    account_snapshot, cache=False
                )

        try:
            active_cache_dir = (
                active_cache_provider() if active_cache_provider is not None else None
            )
        except Exception:
            active_cache_dir = None
        if (
            evaluation_timestamp is None
            and live_bar_provider is not None
            and canonical_timeframe(timeframe) is not None
        ):
            bar_load = load_live_audited_bars(
                live_bar_provider,
                symbol,
                timeframe,
                timestamp,
            )
            if (
                bar_load.bars is None
                and "LIVE_BAR_PROVIDER_UNAVAILABLE" in bar_load.quality_report.reason_codes
            ):
                bar_load = load_pipeline_bars(
                    cache_dir,
                    symbol,
                    timeframe,
                    timestamp,
                    active_cache_dir,
                )
        else:
            bar_load = load_pipeline_bars(
                cache_dir,
                symbol,
                timeframe,
                timestamp,
                active_cache_dir,
            )
        bars, external_io_ms, cache_hits, cache_misses = bar_load
        quality_report = getattr(bar_load, "quality_report", None)
        if (
            evaluation_timestamp is None
            and quality_report is not None
            and quality_report.source_retrieved_at is not None
            and quality_report.source_retrieved_at > timestamp
        ):
            timestamp = quality_report.source_retrieved_at
        io_metrics.append(
            ExternalIOMetric(
                operation="load_bars",
                source=(
                    quality_report.source_file
                    if quality_report is not None and quality_report.source_file
                    else "local_bar_cache"
                ),
                elapsed_ms=external_io_ms,
                calls=1,
                cache_hits=cache_hits,
                cache_misses=cache_misses,
                status=(
                    quality_report.status.value
                    if quality_report is not None
                    else "OK"
                    if cache_hits
                    else "UNAVAILABLE"
                ),
            )
        )
        if quality_report is not None:
            reason_code = quality_report.reason_codes[0] if quality_report.reason_codes else None
            freshness = (
                "STALE"
                if "STALE_BARS" in quality_report.reason_codes
                else "UNAVAILABLE"
                if quality_report.status.value == "UNAVAILABLE"
                else "POINT_IN_TIME"
                if quality_report.publication_allowed
                else "INVALID"
            )
            dependencies["bars"] = DataDependencyStatus(
                name="bars",
                available=quality_report.publication_allowed,
                source=quality_report.source_file or "local_bar_cache",
                data_as_of=quality_report.data_as_of,
                freshness=freshness,
                publication_state=(
                    "RESEARCH_ONLY" if quality_report.publication_allowed else "BLOCKED"
                ),
                sync_status=(
                    "SYNCED"
                    if quality_report.status.value == "PASS"
                    else quality_report.status.value
                ),
                reason_code=reason_code,
                cache_status=(
                    "BYPASS"
                    if quality_report is not None
                    and quality_report.source_file == getattr(live_bar_provider, "provider_name", None)
                    else "HIT"
                    if cache_hits
                    else "MISS"
                ),
                quality_status=quality_report.status.value,
                quality_reason_codes=quality_report.reason_codes,
                requested_timeframe=quality_report.requested_timeframe,
                observed_timeframe=quality_report.observed_timeframe,
                bar_count=quality_report.bar_count,
                usable_bar_count=quality_report.usable_bar_count,
                incomplete_candle_count=quality_report.incomplete_candle_count,
                retrieved_at=quality_report.source_retrieved_at,
                content_sha256=quality_report.source_content_sha256,
            )
        else:
            latest_bar_timestamp = None
            if bars is not None and not getattr(bars, "empty", True):
                latest_bar_timestamp = bar_timestamp(bars.iloc[-1])
            dependencies["bars"] = DataDependencyStatus(
                name="bars",
                available=bars is not None and not getattr(bars, "empty", True),
                source="local_bar_cache",
                data_as_of=latest_bar_timestamp,
                freshness="POINT_IN_TIME",
                publication_state="RESEARCH_ONLY",
                sync_status="SYNCED" if cache_hits else "UNAVAILABLE",
                reason_code=(
                    None if cache_hits else "BARS_UNAVAILABLE_AT_EVALUATION_TIMESTAMP"
                ),
                cache_status="HIT" if cache_hits else "MISS",
            )
        horizon = resolve_horizon_for_timeframe(normalized_timeframe or timeframe)
        timeframe_map = resolve_timeframes_for_horizon(horizon)
        htf_bars = None
        macro_bars = None
        if (
            evaluation_timestamp is None
            and live_bar_provider is not None
            and normalized_timeframe is not None
        ):
            (
                htf_bars,
                macro_bars,
                context_dependencies,
                context_metrics,
                context_retrieval_times,
            ) = _load_live_context_bars(
                live_bar_provider,
                symbol,
                horizon,
                timestamp,
                normalized_timeframe,
                bar_load,
            )
            dependencies.update(context_dependencies)
            io_metrics.extend(context_metrics)
            if context_retrieval_times:
                timestamp = max([timestamp, *context_retrieval_times])
        total_external_io_ms = sum(metric.elapsed_ms for metric in io_metrics)
        total_cache_hits = sum(metric.cache_hits for metric in io_metrics)
        total_cache_misses = sum(metric.cache_misses for metric in io_metrics)
        context = QXEvaluationContext(
            symbol=symbol.upper(),
            timeframe=normalized_timeframe or timeframe,
            evaluation_timestamp=timestamp,
            request_started_at=request_started_at,
            bars=bars,
            option_chain=option_chain,
            account_snapshot=account_snapshot,
            external_io_ms=total_external_io_ms,
            cache_hits=total_cache_hits,
            cache_misses=total_cache_misses,
            data_dependencies=dependencies,
            io_metrics=io_metrics,
            horizon=horizon,
            htf_timeframe=timeframe_map["htf"],
            htf_bars=htf_bars,
            macro_timeframe=timeframe_map["macro"],
            macro_bars=macro_bars,
            config_version=config.version,
            config=config,
        )
        result = orchestrator.run_pipeline(context, config)
        if publication_plan is not None and publication_plan.should_execute:
            try:
                opportunity_publisher.publish_reserved(
                    plan=publication_plan,
                    result=result,
                    context=context,
                    producer_id=producer_id,
                    producer_run_id=producer_run_id,
                    expires_at=result.evaluation_timestamp
                    + _opportunity_freshness_ttl(context.timeframe),
                    freshness_policy_version="live_timeframe_v1",
                    horizon_context=context.horizon,
                )
            except (OpportunityPublicationError, OpportunityRepositoryError) as exc:
                opportunity_publisher.abandon_reserved(
                    publication_plan,
                    failure_code="PUBLICATION_VALIDATION_FAILED",
                )
                logger.warning(
                    "Canonical opportunity publication skipped for %s %s: %s",
                    context.symbol,
                    context.timeframe,
                    type(exc).__name__,
                )
        return result

    @router.get("/api/v2/qx/portfolio", response_model=PortfolioWorkspaceResponse)
    def get_portfolio_v2(
        evaluation_timestamp: datetime | None = None,
    ) -> PortfolioWorkspaceResponse:
        request_started_at = datetime.now(timezone.utc)
        dependencies: dict[str, DataDependencyStatus] = {}
        io_metrics: list[ExternalIOMetric] = []
        if evaluation_timestamp is not None:
            timestamp = aware_utc(evaluation_timestamp)
            if snapshot_repository is None:
                account_snapshot = None
                dependencies["account_snapshot"] = _unavailable(
                    "account_snapshot", "ACCOUNT_SNAPSHOT_STORE_UNAVAILABLE"
                )
            else:
                started = time.perf_counter()
                try:
                    account_snapshot = snapshot_repository.latest_account(timestamp)
                    status = "OK"
                except Exception as exc:
                    logger.warning(
                        "Canonical account snapshot history unavailable: %s",
                        type(exc).__name__,
                    )
                    account_snapshot = None
                    status = "ERROR"
                account_snapshot = _age_account_snapshot(account_snapshot, timestamp)
                elapsed = (time.perf_counter() - started) * 1000.0
                io_metrics.append(
                    ExternalIOMetric(
                        operation="load_point_in_time_account_snapshot",
                        source="sqlite_snapshot_store",
                        elapsed_ms=elapsed,
                        calls=1,
                        cache_hits=int(account_snapshot is not None),
                        cache_misses=int(account_snapshot is None),
                        status=status,
                    )
                )
                dependencies["account_snapshot"] = _account_dependency(
                    account_snapshot, cache=True
                )
        else:
            account_snapshot = _acquire_account(
                snapshot_repository,
                account_snapshot_provider,
                dependencies,
                io_metrics,
            )
            timestamp = datetime.now(timezone.utc)
            account_snapshot = _visible_account(account_snapshot, timestamp)
            account_snapshot = _age_account_snapshot(account_snapshot, timestamp)
            if account_snapshot is None:
                dependencies["account_snapshot"] = _unavailable(
                    "account_snapshot", "ACCOUNT_SNAPSHOT_UNAVAILABLE"
                )
            else:
                dependencies["account_snapshot"] = _account_dependency(
                    account_snapshot, cache=False
                )

        dependency = dependencies["account_snapshot"]
        provider_latency = sum(metric.elapsed_ms for metric in io_metrics) or None
        return build_portfolio_workspace_response(
            account_snapshot,
            request_started_at=request_started_at,
            evaluation_timestamp=timestamp,
            dependency=dependency,
            provider_latency_ms=provider_latency,
        )

    return router


def _acquire_live_snapshots(
    repository: CanonicalSnapshotRepository | None,
    option_provider: CanonicalOptionChainSnapshotProvider | None,
    account_provider: CanonicalAccountSnapshotProvider | None,
    symbol: str,
    dependencies: dict[str, DataDependencyStatus],
    io_metrics: list[ExternalIOMetric],
) -> tuple[Any, Any]:
    option_chain = _acquire_option_chain(
        repository, option_provider, symbol, dependencies, io_metrics
    )
    account_snapshot = _acquire_account(
        repository, account_provider, dependencies, io_metrics
    )
    return option_chain, account_snapshot


def _acquire_option_chain(
    repository: CanonicalSnapshotRepository | None,
    provider: CanonicalOptionChainSnapshotProvider | None,
    symbol: str,
    dependencies: dict[str, DataDependencyStatus],
    io_metrics: list[ExternalIOMetric],
) -> Any:
    name = "option_chain"
    if provider is None:
        dependencies[name] = _unavailable(name, "OPTION_CHAIN_PROVIDER_UNAVAILABLE")
        return None
    started = time.perf_counter()
    status = "UNAVAILABLE"
    snapshot = None
    try:
        snapshot = provider.get_option_chain_snapshot(symbol)
        if snapshot is not None and repository is not None:
            persisted_at = datetime.now(timezone.utc)
            snapshot_id = repository.save_option_chain(snapshot, persisted_at)
            snapshot = snapshot.model_copy(
                update={
                    "retrieved_at": snapshot.retrieved_at or persisted_at.isoformat(),
                    "snapshot_id": snapshot_id,
                }
            )
            status = "OK"
        elif snapshot is not None:
            snapshot = None
            status = "PERSISTENCE_UNAVAILABLE"
    except Exception as exc:
        logger.warning("Canonical option provider unavailable: %s", type(exc).__name__)
        snapshot = None
        status = "ERROR"
    elapsed = (time.perf_counter() - started) * 1000.0
    io_metrics.append(
        ExternalIOMetric(
            operation="acquire_option_chain",
            source=provider.provider_name,
            elapsed_ms=elapsed,
            calls=1,
            cache_misses=1,
            status=status,
        )
    )
    timestamp = parse_timestamp(getattr(snapshot, "data_as_of", None))
    dependencies[name] = DataDependencyStatus(
        name=name,
        available=snapshot is not None,
        source=getattr(snapshot, "source", provider.provider_name),
        data_as_of=timestamp,
        freshness=getattr(snapshot, "freshness", "UNAVAILABLE"),
        publication_state=getattr(snapshot, "publication_state", "BLOCKED"),
        sync_status=getattr(snapshot, "sync_status", "UNAVAILABLE"),
        reason_code=None if snapshot is not None else "OPTION_CHAIN_UNAVAILABLE",
        cache_status="MISS",
        snapshot_id=getattr(snapshot, "snapshot_id", None),
    )
    return snapshot


def _acquire_account(
    repository: CanonicalSnapshotRepository | None,
    provider: CanonicalAccountSnapshotProvider | None,
    dependencies: dict[str, DataDependencyStatus],
    io_metrics: list[ExternalIOMetric],
) -> Any:
    name = "account_snapshot"
    if provider is None:
        dependencies[name] = _unavailable(name, "ACCOUNT_PROVIDER_UNAVAILABLE")
        return None
    started = time.perf_counter()
    status = "UNAVAILABLE"
    snapshot = None
    try:
        acquired = provider.get_account_risk_snapshot()
        if acquired is not None and repository is not None:
            snapshot = sanitize_account_snapshot(acquired)
            persisted_at = datetime.now(timezone.utc)
            snapshot_id = repository.save_account(snapshot, persisted_at)
            snapshot = snapshot.model_copy(
                update={
                    "retrieved_at": snapshot.retrieved_at or persisted_at,
                    "snapshot_id": snapshot_id,
                }
            )
            status = "OK"
        elif acquired is not None:
            status = "PERSISTENCE_UNAVAILABLE"
    except Exception as exc:
        logger.warning("Canonical account provider unavailable: %s", type(exc).__name__)
        snapshot = None
        status = "ERROR"
    elapsed = (time.perf_counter() - started) * 1000.0
    io_metrics.append(
        ExternalIOMetric(
            operation="acquire_account_snapshot",
            source=provider.provider_name,
            elapsed_ms=elapsed,
            calls=1,
            cache_misses=1,
            status=status,
        )
    )
    dependencies[name] = DataDependencyStatus(
        name=name,
        available=snapshot is not None,
        source=getattr(snapshot, "broker_provenance", provider.provider_name),
        data_as_of=getattr(snapshot, "data_as_of", None),
        freshness=str(getattr(getattr(snapshot, "freshness", None), "value", "UNAVAILABLE")),
        publication_state=getattr(snapshot, "publication_state", "BLOCKED"),
        sync_status=getattr(snapshot, "sync_status", "UNAVAILABLE"),
        reason_code=None if snapshot is not None else "ACCOUNT_SNAPSHOT_UNAVAILABLE",
        cache_status="MISS",
        snapshot_id=getattr(snapshot, "snapshot_id", None),
    )
    return snapshot


def _load_historical_snapshots(
    repository: CanonicalSnapshotRepository | None,
    symbol: str,
    evaluation_timestamp: datetime,
    dependencies: dict[str, DataDependencyStatus],
    io_metrics: list[ExternalIOMetric],
) -> tuple[Any, Any]:
    if repository is None:
        dependencies["option_chain"] = _unavailable(
            "option_chain", "OPTION_SNAPSHOT_STORE_UNAVAILABLE"
        )
        dependencies["account_snapshot"] = _unavailable(
            "account_snapshot", "ACCOUNT_SNAPSHOT_STORE_UNAVAILABLE"
        )
        return None, None
    started = time.perf_counter()
    try:
        option_chain = repository.latest_option_chain(symbol, evaluation_timestamp)
        option_status = "OK"
    except Exception as exc:
        logger.warning("Canonical option snapshot history unavailable: %s", type(exc).__name__)
        option_chain = None
        option_status = "ERROR"
    try:
        account_snapshot = repository.latest_account(evaluation_timestamp)
        account_status = "OK"
    except Exception as exc:
        logger.warning("Canonical account snapshot history unavailable: %s", type(exc).__name__)
        account_snapshot = None
        account_status = "ERROR"
    option_chain = _age_option_snapshot(option_chain, evaluation_timestamp)
    account_snapshot = _age_account_snapshot(account_snapshot, evaluation_timestamp)
    elapsed = (time.perf_counter() - started) * 1000.0
    hits = int(option_chain is not None) + int(account_snapshot is not None)
    io_metrics.append(
        ExternalIOMetric(
            operation="load_point_in_time_snapshots",
            source="sqlite_snapshot_store",
            elapsed_ms=elapsed,
            calls=2,
            cache_hits=hits,
            cache_misses=2 - hits,
            status=(
                "ERROR"
                if "ERROR" in {option_status, account_status}
                else "OK"
            ),
        )
    )
    dependencies["option_chain"] = _option_dependency(option_chain, cache=True)
    dependencies["account_snapshot"] = _account_dependency(account_snapshot, cache=True)
    return option_chain, account_snapshot


def _option_dependency(snapshot: Any, *, cache: bool) -> DataDependencyStatus:
    if snapshot is None:
        return _unavailable("option_chain", "OPTION_CHAIN_UNAVAILABLE_AT_EVALUATION_TIMESTAMP")
    return DataDependencyStatus(
        name="option_chain",
        available=True,
        source=snapshot.source,
        data_as_of=parse_timestamp(snapshot.data_as_of),
        freshness=snapshot.freshness,
        publication_state=snapshot.publication_state,
        sync_status=snapshot.sync_status,
        cache_status="HIT" if cache else "MISS",
        snapshot_id=snapshot.snapshot_id,
    )


def _account_dependency(snapshot: Any, *, cache: bool) -> DataDependencyStatus:
    if snapshot is None:
        return _unavailable(
            "account_snapshot", "ACCOUNT_SNAPSHOT_UNAVAILABLE_AT_EVALUATION_TIMESTAMP"
        )
    return DataDependencyStatus(
        name="account_snapshot",
        available=True,
        source=snapshot.broker_provenance,
        data_as_of=snapshot.data_as_of,
        freshness=snapshot.freshness.value,
        publication_state=snapshot.publication_state,
        sync_status=snapshot.sync_status,
        cache_status="HIT" if cache else "MISS",
        snapshot_id=snapshot.snapshot_id,
    )


def _unavailable(name: str, reason_code: str) -> DataDependencyStatus:
    return DataDependencyStatus(name=name, reason_code=reason_code)


def _visible_option(snapshot: Any, evaluation_timestamp: datetime) -> Any:
    timestamp = parse_timestamp(getattr(snapshot, "data_as_of", None))
    retrieved_at = parse_timestamp(getattr(snapshot, "retrieved_at", None))
    return (
        snapshot
        if timestamp is not None
        and timestamp <= evaluation_timestamp
        and retrieved_at is not None
        and retrieved_at <= evaluation_timestamp
        else None
    )


def _visible_account(snapshot: Any, evaluation_timestamp: datetime) -> Any:
    timestamp = parse_timestamp(getattr(snapshot, "data_as_of", None))
    retrieved_at = parse_timestamp(getattr(snapshot, "retrieved_at", None))
    return (
        snapshot
        if timestamp is not None
        and timestamp <= evaluation_timestamp
        and retrieved_at is not None
        and retrieved_at <= evaluation_timestamp
        else None
    )


def _age_option_snapshot(
    snapshot: OptionsContext | None,
    evaluation_timestamp: datetime,
    max_age_seconds: float = 60.0,
) -> OptionsContext | None:
    if snapshot is None:
        return None
    oldest_age = 0.0
    aged_chain = {}
    original_contracts = 0
    visible_contracts = 0
    for expiration, strikes in snapshot.chain.items():
        aged_chain[expiration] = {}
        for strike, contracts in strikes.items():
            aged_chain[expiration][strike] = {}
            for option_type, contract in contracts.items():
                original_contracts += 1
                quote_timestamp = parse_timestamp(contract.quote_as_of)
                if quote_timestamp is None or quote_timestamp > evaluation_timestamp:
                    continue
                age = max(0.0, (evaluation_timestamp - quote_timestamp).total_seconds())
                oldest_age = max(oldest_age, age)
                visible_contracts += 1
                aged_chain[expiration][strike][option_type] = contract.model_copy(
                    update={"quote_age_seconds": age}
                )
    if original_contracts > 0 and visible_contracts == 0:
        return None
    freshness = "FRESH" if oldest_age <= max_age_seconds else "STALE"
    sync_status = (
        "PARTIAL" if visible_contracts < original_contracts else snapshot.sync_status
    )
    return snapshot.model_copy(
        update={"chain": aged_chain, "freshness": freshness, "sync_status": sync_status}
    )


def _age_account_snapshot(
    snapshot: AccountRiskContext | None,
    evaluation_timestamp: datetime,
    warn_after_seconds: float = 30.0,
) -> AccountRiskContext | None:
    if snapshot is None:
        return None
    age = max(0.0, (evaluation_timestamp - aware_utc(snapshot.data_as_of)).total_seconds())
    if age > warn_after_seconds * 2:
        freshness = FreshnessState.STALE_BLOCKED
    elif age > warn_after_seconds:
        freshness = FreshnessState.STALE_WARNED
    else:
        freshness = FreshnessState.FRESH
    return snapshot.model_copy(update={"freshness": freshness})
