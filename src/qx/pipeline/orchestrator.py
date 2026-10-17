import time
from datetime import datetime
from typing import Any, Dict, Optional

from qx.config.rules_config import RulesEngineConfig
from qx.direction.direction_engine import evaluate_direction_engine
from qx.market_driver.engine import MarketDriverEngine
from qx.models.rules import DeltaProvenance, PublicationState, SignalState
from qx.options_expression.engine import OptionsExpressionEngine
from qx.options_expression.models import OptionsExpressionState
from qx.pipeline.models import (
    PIPELINE_VERSION,
    SKIPPED,
    DataDependencyStatus,
    LifecycleState,
    QXEvaluationContext,
    QXEvaluationResult,
)
from qx.pipeline.multi_timeframe import (
    evaluate_htf_structure,
    resolve_horizon_for_timeframe,
    resolve_timeframes_for_horizon,
)
from qx.pipeline.point_in_time import (
    aware_utc,
    bar_timestamp,
    evaluated_bar_window_sha256,
    filter_bars_at_or_before,
    parse_timestamp,
)
from qx.playbooks.context import QXEvaluationContext as PlaybookContext
from qx.playbooks.engine import PlaybookEngine
from qx.portfolio.models import PortfolioRiskState
from qx.portfolio.portfolio_risk_engine import PortfolioRiskEngine
from qx.regime.market_regime import evaluate_market_regime
from qx.structure.smc_suite import analyze_smc_structure
from qx.tradeability.engine import TradeabilityEngine
from qx.tradeability.models import (
    LiquidityApplicability,
    TradeabilityMarketEvidence,
    TradeabilityState,
)
from qx.triggers.engine import EntryTriggerEngine


_STAGE_KEYS = (
    "structure_ms",
    "regime_ms",
    "direction_ms",
    "market_driver_ms",
    "playbooks_ms",
    "trigger_ms",
    "tradeability_ms",
    "options_expression_ms",
    "portfolio_risk_ms",
)


def _bar_timestamp(bar: Any) -> Optional[datetime]:
    return bar_timestamp(bar)


def _value(item: Any) -> str:
    value = getattr(item, "value", item)
    return str(value)


def _engine_version(output: Any, fallback: str) -> str:
    return str(getattr(output, "engine_version", fallback))


def _structure_liquidity_levels(structure: Any) -> list[Any]:
    levels: list[Any] = []
    protected_high = getattr(structure, "protected_high", None)
    protected_low = getattr(structure, "protected_low", None)
    if protected_high is not None:
        levels.append(protected_high)
    if protected_low is not None:
        levels.append(protected_low)
    levels.extend(getattr(structure, "liquidity_pools", []))
    return levels


def _snapshot_is_visible(data_as_of: Any, evaluation_timestamp: datetime) -> bool:
    timestamp = parse_timestamp(data_as_of)
    return timestamp is not None and timestamp <= evaluation_timestamp


def _current_atr(ctx: QXEvaluationContext, bar: Dict[str, Any]) -> float:
    if ctx.atr > 0:
        return ctx.atr
    high = float(bar.get("high", 0.0) or 0.0)
    low = float(bar.get("low", 0.0) or 0.0)
    return max(0.0, high - low)


def run_pipeline(ctx: QXEvaluationContext, config: RulesEngineConfig) -> QXEvaluationResult:
    evaluation_timestamp = aware_utc(ctx.evaluation_timestamp)
    total_started = time.perf_counter()
    stage_latencies: Dict[str, float | int | str] = {key: SKIPPED for key in _STAGE_KEYS}
    stage_latencies["external_io_ms"] = (
        ctx.external_io_ms if ctx.external_io_ms is not None else SKIPPED
    )
    stage_latencies["cache_hits"] = ctx.cache_hits if ctx.cache_hits is not None else SKIPPED
    stage_latencies["cache_misses"] = ctx.cache_misses if ctx.cache_misses is not None else SKIPPED

    horizon = (ctx.horizon or resolve_horizon_for_timeframe(ctx.timeframe)).upper()
    timeframe_map = resolve_timeframes_for_horizon(horizon)
    htf_timeframe = (ctx.htf_timeframe or timeframe_map.get("htf", "1h")).lower()
    macro_timeframe = (ctx.macro_timeframe or timeframe_map.get("macro", "1d")).lower()

    result = QXEvaluationResult(
        symbol=ctx.symbol.upper(),
        timeframe=ctx.timeframe,
        evaluation_timestamp=evaluation_timestamp,
        request_started_at=ctx.request_started_at,
        publication_state=ctx.publication_state,
        current_lifecycle_state=LifecycleState.NO_SETUP,
        config_version=config.version,
        pipeline_version=PIPELINE_VERSION,
        stage_latencies=stage_latencies,
        data_dependencies=dict(ctx.data_dependencies),
        io_metrics=list(ctx.io_metrics),
        horizon=horizon,
        htf_timeframe=htf_timeframe,
        macro_timeframe=macro_timeframe,
    )

    def finish() -> QXEvaluationResult:
        stage_latencies["total_ms"] = (time.perf_counter() - total_started) * 1000.0
        result.stage_latencies = stage_latencies
        return result

    visible_bars = filter_bars_at_or_before(ctx.bars, evaluation_timestamp)
    if visible_bars.empty:
        result.current_lifecycle_state = LifecycleState.BLOCKED
        result.publication_state = PublicationState.BLOCKED
        result.reason_codes.append("NO_BARS_AT_OR_BEFORE_EVALUATION_TIMESTAMP")
        return finish()
    try:
        result.evaluated_bar_window_sha256 = evaluated_bar_window_sha256(
            visible_bars,
            ctx.timeframe,
        )
    except ValueError:
        result.evaluated_bar_window_sha256 = None

    current_bar_series = visible_bars.iloc[-1]
    current_bar = current_bar_series.to_dict()
    evaluation_bar_index = len(visible_bars) - 1
    current_price = float(current_bar.get("close", 0.0) or 0.0)
    current_atr = _current_atr(ctx, current_bar)
    evaluation_iso = evaluation_timestamp.isoformat()

    started = time.perf_counter()
    structure = analyze_smc_structure(
        bars=visible_bars,
        is_fast_chart=False,
        symbol=ctx.symbol,
        timeframe=ctx.timeframe,
        break_confirmation_mode="CLOSE",
        evaluation_bar_index=evaluation_bar_index,
    )
    stage_latencies["structure_ms"] = (time.perf_counter() - started) * 1000.0
    result.structure = structure
    result.engine_versions["structure"] = _engine_version(structure, "v3")

    structure_state = _value(getattr(structure, "regime", "UNKNOWN"))
    latest_structure_event = getattr(structure, "latest_event", None)
    last_event_type = getattr(latest_structure_event, "event_type", None)
    started = time.perf_counter()
    market_regime = evaluate_market_regime(
        structure_result=structure,
        structure_state=structure_state,
        invalidated=False,
        alternating_breaks=0,
        atr_percentile=50.0,
        current_atr=current_atr,
        baseline_atr=current_atr,
        gex_data=ctx.gex_data or {},
        gamma_value=ctx.gamma_value,
        gamma_provenance=ctx.gamma_provenance,
        timestamp_str=evaluation_iso,
        session_open_str=ctx.session_open_str,
        session_close_str=ctx.session_close_str,
        has_directional_auction=False,
        data_as_of=evaluation_iso,
        rules_config=config,
    )
    stage_latencies["regime_ms"] = (time.perf_counter() - started) * 1000.0
    result.market_regime = market_regime
    result.engine_versions["regime"] = _engine_version(market_regime, "v5.0.0")

    htf_structure_state: Optional[str] = None
    htf_age_bars: Optional[int] = 9999

    if ctx.htf_bars is not None:
        acquired_htf = result.data_dependencies.get("htf_bars")
        htf_eval = evaluate_htf_structure(
            bars=ctx.htf_bars,
            evaluation_timestamp=evaluation_timestamp,
            timeframe=htf_timeframe,
            symbol=ctx.symbol,
        )
        if htf_eval.available:
            htf_structure_state = htf_eval.structure_state
            htf_age_bars = htf_eval.age_bars
            result.htf_structure = htf_eval.structure_result
            result.data_dependencies["htf_bars"] = DataDependencyStatus(
                name="htf_bars",
                available=True,
                source=(acquired_htf.source if acquired_htf else "CANONICAL_HTF_FEED"),
                data_as_of=(acquired_htf.data_as_of if acquired_htf else evaluation_timestamp),
                freshness="FRESH" if htf_eval.age_bars <= 25 else "STALE",
                publication_state="COMMITTED",
                sync_status="SYNCHRONIZED",
                cache_status=acquired_htf.cache_status if acquired_htf else "MISS",
                quality_status=acquired_htf.quality_status if acquired_htf else None,
                quality_reason_codes=(
                    acquired_htf.quality_reason_codes if acquired_htf else []
                ),
                requested_timeframe=htf_timeframe,
                observed_timeframe=htf_timeframe,
                bar_count=htf_eval.bar_count,
                usable_bar_count=htf_eval.usable_bar_count,
                incomplete_candle_count=htf_eval.incomplete_candle_count,
                retrieved_at=acquired_htf.retrieved_at if acquired_htf else None,
                content_sha256=htf_eval.content_sha256,
            )
        else:
            htf_structure_state = None
            htf_age_bars = 9999
            result.data_dependencies["htf_bars"] = DataDependencyStatus(
                name="htf_bars",
                available=False,
                source=acquired_htf.source if acquired_htf else "UNAVAILABLE",
                data_as_of=acquired_htf.data_as_of if acquired_htf else None,
                freshness="UNAVAILABLE",
                publication_state="BLOCKED",
                sync_status="UNAVAILABLE",
                reason_code=htf_eval.reason_code or "HTF_BARS_UNAVAILABLE",
                cache_status=acquired_htf.cache_status if acquired_htf else "MISS",
                quality_status=acquired_htf.quality_status if acquired_htf else None,
                quality_reason_codes=(
                    acquired_htf.quality_reason_codes if acquired_htf else []
                ),
                requested_timeframe=htf_timeframe,
                observed_timeframe=htf_timeframe,
                bar_count=htf_eval.bar_count,
                usable_bar_count=htf_eval.usable_bar_count,
                incomplete_candle_count=htf_eval.incomplete_candle_count,
                retrieved_at=acquired_htf.retrieved_at if acquired_htf else None,
            )
    elif ctx.htf_structure is not None:
        result.htf_structure = ctx.htf_structure
        regime_val = getattr(ctx.htf_structure, "regime", "NEUTRAL")
        htf_structure_state = str(regime_val.value if hasattr(regime_val, "value") else regime_val).upper()
        htf_age_bars = getattr(ctx.htf_structure, "age_bars", 0)
    elif ctx.htf_structure_state and str(ctx.htf_structure_state).upper() not in ("UNKNOWN", "UNAVAILABLE", "NONE", ""):
        htf_structure_state = str(ctx.htf_structure_state).upper()
        htf_age_bars = ctx.htf_age_bars
    else:
        htf_structure_state = None
        htf_age_bars = 9999
        if "htf_bars" not in result.data_dependencies:
            result.data_dependencies["htf_bars"] = DataDependencyStatus(
                name="htf_bars",
                available=False,
                source="UNAVAILABLE",
                freshness="UNAVAILABLE",
                publication_state="BLOCKED",
                sync_status="UNAVAILABLE",
                reason_code="HTF_NOT_PROVIDED",
                requested_timeframe=htf_timeframe,
            )

    if ctx.macro_bars is not None:
        acquired_macro = result.data_dependencies.get("macro_bars")
        result.data_dependencies["macro_bars"] = DataDependencyStatus(
            name="macro_bars",
            available=True,
            source=(
                acquired_macro.source if acquired_macro else "CANONICAL_MACRO_FEED"
            ),
            data_as_of=(
                acquired_macro.data_as_of if acquired_macro else evaluation_timestamp
            ),
            freshness=acquired_macro.freshness if acquired_macro else "POINT_IN_TIME",
            publication_state="COMMITTED",
            sync_status="SYNCHRONIZED",
            cache_status=acquired_macro.cache_status if acquired_macro else "MISS",
            quality_status=acquired_macro.quality_status if acquired_macro else None,
            quality_reason_codes=(
                acquired_macro.quality_reason_codes if acquired_macro else []
            ),
            requested_timeframe=macro_timeframe,
            observed_timeframe=macro_timeframe,
            bar_count=len(ctx.macro_bars),
            usable_bar_count=len(ctx.macro_bars),
            retrieved_at=acquired_macro.retrieved_at if acquired_macro else None,
        )

    started = time.perf_counter()
    direction = evaluate_direction_engine(
        symbol=ctx.symbol,
        timeframe=ctx.timeframe,
        structure_result=structure,
        structure_state=structure_state,
        last_event_type=str(last_event_type or "NONE"),
        structure_age_bars=0,
        price=current_price,
        vwap=ctx.vwap,
        vwap_slope=ctx.vwap_slope,
        vwap_age_seconds=ctx.vwap_age_seconds,
        fast_ema=ctx.fast_ema,
        medium_ema=ctx.medium_ema,
        slow_ema=ctx.slow_ema,
        fast_slope=ctx.fast_slope,
        medium_slope=ctx.medium_slope,
        slow_slope=ctx.slow_slope,
        ema_age_seconds=ctx.ema_age_seconds,
        delta_value=ctx.delta_value,
        delta_provenance=ctx.delta_provenance,
        delta_age_seconds=ctx.delta_age_seconds,
        relative_strength_score=ctx.relative_strength_score,
        sector_rs_age_seconds=ctx.sector_rs_age_seconds,
        market_alignment_score=ctx.market_alignment_score,
        market_alignment_age_seconds=ctx.market_alignment_age_seconds,
        is_index_future=ctx.is_index_future,
        htf_structure_state=htf_structure_state,
        htf_age_bars=htf_age_bars,
        rules_config=config,
        market_regime=market_regime,
    )
    stage_latencies["direction_ms"] = (time.perf_counter() - started) * 1000.0
    result.direction = direction
    result.engine_versions["direction"] = _engine_version(direction, "v5.1.0")

    started = time.perf_counter()
    market_driver = MarketDriverEngine(config.market_driver).evaluate(
        ctx=ctx,
        previous_result=ctx.previous_market_driver,
        rules_config=config,
    )
    stage_latencies["market_driver_ms"] = (time.perf_counter() - started) * 1000.0
    result.market_driver = market_driver
    result.engine_versions["market_driver"] = market_driver.engine_version

    started = time.perf_counter()
    playbook_context = PlaybookContext(
        symbol=ctx.symbol,
        timeframe=ctx.timeframe,
        bars=visible_bars.to_dict("records"),
        latest_bar=current_bar,
        market_regime=market_regime,
        direction=direction,
        structure_result=structure,
        order_blocks=list(getattr(structure, "order_blocks", [])),
        liquidity_levels=_structure_liquidity_levels(structure),
        vwap=ctx.vwap,
        atr=current_atr,
        publication_state=ctx.publication_state,
        event_timestamp=evaluation_iso,
        knowledge_timestamp=evaluation_iso,
        rules_config=config,
    )
    playbooks, primary_candidate = PlaybookEngine().evaluate_all(playbook_context)
    stage_latencies["playbooks_ms"] = (time.perf_counter() - started) * 1000.0
    result.playbooks = playbooks
    result.primary_playbook_candidate = primary_candidate
    result.engine_versions["playbooks"] = (
        _engine_version(primary_candidate, "v6.1.0") if primary_candidate is not None else "v6.1.0"
    )

    if primary_candidate is None or primary_candidate.state == SignalState.NO_SETUP:
        result.current_lifecycle_state = LifecycleState.NO_SETUP
        return finish()
    if primary_candidate.state == SignalState.WATCH:
        result.current_lifecycle_state = LifecycleState.WATCH
        return finish()

    result.current_lifecycle_state = LifecycleState.ARMED
    armed_candidate = ctx.armed_playbook or primary_candidate
    started = time.perf_counter()
    trigger = EntryTriggerEngine(config).evaluate_trigger(
        armed_eval=armed_candidate,
        bar=current_bar,
        bar_idx=evaluation_bar_index,
        armed_bar_idx=max(0, evaluation_bar_index - 1),
        source_order_block=None,
        source_fvg=None,
        source_session_level_valid=True,
        atr=current_atr,
    )
    stage_latencies["trigger_ms"] = (time.perf_counter() - started) * 1000.0
    result.trigger = trigger
    result.engine_versions["trigger"] = _engine_version(trigger, "v7.0.0")
    if trigger.state != SignalState.TRIGGERED:
        return finish()

    result.current_lifecycle_state = LifecycleState.TRIGGERED
    quote = ctx.quote
    if quote is not None and not _snapshot_is_visible(quote.timestamp, evaluation_timestamp):
        quote = None
    quote_timestamp = (
        parse_timestamp(quote.timestamp)
        if quote is not None
        else _bar_timestamp(current_bar_series)
    )
    quote_age_seconds = (
        max(0.0, (evaluation_timestamp - quote_timestamp).total_seconds())
        if quote_timestamp is not None
        else 0.0
    )
    try:
        delta_provenance = DeltaProvenance(ctx.delta_provenance)
    except ValueError:
        delta_provenance = DeltaProvenance.UNAVAILABLE
    trigger_timestamp = parse_timestamp(
        trigger.trigger_confirmed_at or trigger.trigger_event_timestamp
    )
    seconds_since_trigger = (
        max(0.0, (evaluation_timestamp - trigger_timestamp).total_seconds())
        if trigger_timestamp is not None
        else 0.0
    )
    targets = ctx.structural_target_candidates or list(armed_candidate.structural_target_candidates)
    evidence = TradeabilityMarketEvidence(
        current_price=current_price,
        atr=current_atr,
        evaluation_timestamp=evaluation_iso,
        data_as_of=(quote_timestamp or evaluation_timestamp).isoformat(),
        evaluation_session_date=evaluation_timestamp.date().isoformat(),
        liquidity_applicability=(
            LiquidityApplicability.AVAILABLE
            if quote is not None
            else LiquidityApplicability.UNKNOWN
        ),
        quote_age_seconds=quote_age_seconds,
        bid=quote.bid if quote is not None else None,
        ask=quote.ask if quote is not None else None,
        current_volume=float(current_bar.get("volume", 0.0) or 0.0),
        current_time_slot=evaluation_timestamp.strftime("%H:%M"),
        delta_value=ctx.delta_value,
        delta_provenance=delta_provenance,
        delta_age_seconds=ctx.delta_age_seconds,
        structural_target_candidates=targets,
        bars_since_trigger=0,
        seconds_since_trigger=seconds_since_trigger,
    )
    started = time.perf_counter()
    tradeability = TradeabilityEngine(config).evaluate_triggered_setup(
        trigger,
        evidence,
        delta_reliability_map=ctx.delta_reliability_map or None,
    )
    stage_latencies["tradeability_ms"] = (time.perf_counter() - started) * 1000.0
    result.tradeability = tradeability
    result.engine_versions["tradeability"] = _engine_version(tradeability, "v8.1.0")
    result.reason_codes = list(tradeability.reason_codes)
    if tradeability.state != TradeabilityState.TRADEABLE:
        if tradeability.state == TradeabilityState.BLOCKED:
            result.current_lifecycle_state = LifecycleState.BLOCKED
            result.publication_state = PublicationState.BLOCKED
        elif tradeability.state == TradeabilityState.EXPIRED:
            result.current_lifecycle_state = LifecycleState.EXPIRED
        else:
            result.current_lifecycle_state = LifecycleState.NOT_TRADEABLE
        return finish()

    result.current_lifecycle_state = LifecycleState.TRADEABLE
    options_context = ctx.option_chain
    if options_context is not None and not _snapshot_is_visible(
        options_context.data_as_of, evaluation_timestamp
    ):
        options_context = None
    if options_context is None:
        result.current_lifecycle_state = LifecycleState.BLOCKED
        result.publication_state = PublicationState.BLOCKED
        result.reason_codes = ["OPTION_CHAIN_UNAVAILABLE_AT_EVALUATION_TIMESTAMP"]
        return finish()

    started = time.perf_counter()
    options_expression = OptionsExpressionEngine(config).evaluate_options_expression(
        tradeability,
        options_context,
        evaluation_timestamp=evaluation_timestamp,
    )
    stage_latencies["options_expression_ms"] = (time.perf_counter() - started) * 1000.0
    result.options_expression = options_expression
    result.engine_versions["options_expression"] = _engine_version(options_expression, "v9.0.0")
    result.reason_codes = list(options_expression.reason_codes)
    if options_expression.state != OptionsExpressionState.SUITABLE:
        result.current_lifecycle_state = (
            LifecycleState.BLOCKED
            if options_expression.state == OptionsExpressionState.BLOCKED
            else LifecycleState.OPTIONS_NOT_SUITABLE
        )
        if options_expression.state == OptionsExpressionState.BLOCKED:
            result.publication_state = PublicationState.BLOCKED
        return finish()

    result.current_lifecycle_state = LifecycleState.OPTIONS_SUITABLE
    primary_candidate = next(
        (
            candidate
            for candidate in options_expression.candidate_strategies
            if candidate.candidate_id == options_expression.primary_candidate_id
        ),
        options_expression.candidate_strategies[0]
        if options_expression.candidate_strategies
        else None,
    )
    account_snapshot = ctx.account_snapshot
    if account_snapshot is not None and not _snapshot_is_visible(
        account_snapshot.data_as_of, evaluation_timestamp
    ):
        account_snapshot = None
    if primary_candidate is None or account_snapshot is None:
        result.current_lifecycle_state = LifecycleState.BLOCKED
        result.publication_state = PublicationState.BLOCKED
        result.reason_codes = [
            "PRIMARY_OPTIONS_CANDIDATE_UNAVAILABLE"
            if primary_candidate is None
            else "ACCOUNT_SNAPSHOT_UNAVAILABLE_AT_EVALUATION_TIMESTAMP"
        ]
        return finish()

    started = time.perf_counter()
    portfolio_risk = PortfolioRiskEngine(config).evaluate_portfolio_risk(
        primary_candidate,
        options_expression,
        account_snapshot,
        evaluation_timestamp=evaluation_timestamp,
    )
    stage_latencies["portfolio_risk_ms"] = (time.perf_counter() - started) * 1000.0
    result.portfolio_risk = portfolio_risk
    result.engine_versions["portfolio_risk"] = _engine_version(portfolio_risk, "v10.0.0")
    result.reason_codes = list(portfolio_risk.reason_codes)
    if portfolio_risk.state == PortfolioRiskState.PORTFOLIO_APPROVED:
        result.current_lifecycle_state = LifecycleState.PORTFOLIO_APPROVED
    elif portfolio_risk.state == PortfolioRiskState.PORTFOLIO_VETOED:
        result.current_lifecycle_state = LifecycleState.PORTFOLIO_VETOED
    else:
        result.current_lifecycle_state = LifecycleState.BLOCKED
        result.publication_state = PublicationState.BLOCKED
    return finish()
