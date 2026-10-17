"""Run the approved DQ2-DQ6 observational milestone without changing engine rules."""

from __future__ import annotations

import argparse
import json
import math
import time
import tracemalloc
from collections import Counter
from datetime import datetime, time as wall_time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from qx.brokers.schwab.auth import SchwabTokenManager
from qx.brokers.schwab.client import SchwabApiClient
from qx.brokers.schwab.health import check_schwab_health
from qx.brokers.schwab.market_data import SchwabMarketDataProvider
from qx.brokers.schwab.quotes import SchwabQuoteProvider
from qx.config.rules_config import load_rules_config
from qx.config.settings import get_settings
from qx.data.factory import (
    build_canonical_account_snapshot_provider,
    build_canonical_option_snapshot_provider,
)
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.pipeline import orchestrator
from qx.pipeline.adapters import HistoricalReplayAdapter
from qx.pipeline.data_quality_observation import (
    analyze_canonical_observations,
    build_structure_profile,
    evaluate_visibility,
    summarize_snapshot_coverage,
)
from qx.pipeline.models import DataDependencyStatus, LifecycleState, PIPELINE_VERSION
from qx.pipeline.point_in_time import aware_utc, parse_timestamp
from qx.pipeline.shadow_telemetry import (
    ShadowTelemetryRepository,
    build_shadow_record,
)
from qx.pipeline.snapshot_store import CanonicalSnapshotRepository
from qx.structure import smc_suite


SYMBOLS = ("SPY", "QQQ", "SPX", "NVDA", "AAPL", "MSFT", "TSLA", "AMD", "JPM", "XOM")
BAR_TIMEFRAMES = ("1m", "5m", "15m", "daily")
SHADOW_TIMEFRAMES = ("1m", "5m", "15m")
FRESHNESS_SECONDS = {
    "quotes": 60,
    "1m": 300,
    "5m": 1_200,
    "15m": 3_600,
    "daily": 259_200,
}
REQUIRED_TRANSITIONS = (
    "WATCH->ARMED",
    "ARMED->TRIGGERED",
    "TRIGGERED->TRADEABLE",
    "TRADEABLE->OPTIONS_SUITABLE",
    "OPTIONS_SUITABLE->PORTFOLIO_APPROVED",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/reports/data_quality_observation_report.json"),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/scanner_history.db"),
    )
    parser.add_argument("--target-observations", type=int, default=1000)
    parser.add_argument("--warmup-bars", type=int, default=50)
    parser.add_argument("--max-input-bars", type=int, default=160)
    args = parser.parse_args()

    settings = get_settings()
    token_manager = SchwabTokenManager(get_settings)
    client = SchwabApiClient(token_manager, base_url=settings.schwab_api_base_url)
    market_provider = SchwabMarketDataProvider(client)
    quote_provider = SchwabQuoteProvider(client)

    dq2 = _run_dq2(token_manager, client, market_provider, quote_provider)
    payload: dict[str, Any] = {
        "report_type": "QXDataQualityObservationMilestone",
        "generated_at": _now().isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "symbols": list(SYMBOLS),
        "dq2": dq2,
    }
    if dq2["status"] != "PASS":
        payload["status"] = "BLOCKED_DQ2"
        _write_report(args.output, payload)
        raise SystemExit(2)

    dq3_observations, replay_frames = _run_dq3(
        market_provider,
        quote_provider,
        build_canonical_option_snapshot_provider("schwab", settings=settings),
        build_canonical_account_snapshot_provider("schwab", settings=settings),
        CanonicalSnapshotRepository(args.database),
    )
    dq3 = summarize_snapshot_coverage(dq3_observations)
    dq3["observations"] = dq3_observations
    dq3["freshness_threshold_seconds"] = FRESHNESS_SECONDS
    payload["dq3"] = dq3
    payload["dq7"] = _summarize_stale_observations(dq3_observations)
    if dq3["status"] != "PASS":
        payload["status"] = "BLOCKED_DQ3_CAUSALITY"
        _write_report(args.output, payload)
        raise SystemExit(3)

    dq4_results, structure_samples, timings, memory_hotspots = _run_dq4(
        replay_frames,
        args.database,
        args.target_observations,
        args.warmup_bars,
        args.max_input_bars,
    )
    dq4 = analyze_canonical_observations(dq4_results)
    _complete_lifecycle_buckets(dq4)
    dq4["target_observations"] = args.target_observations
    dq4["target_met"] = len(dq4_results) >= args.target_observations
    dq4["observation_mode"] = "POINT_IN_TIME_INTRADAY_BAR_REPLAY"
    dq4["historical_options_account_policy"] = "UNAVAILABLE_NO_FABRICATION"
    observed_series = sorted(f"{symbol}:{timeframe}" for symbol, timeframe in replay_frames)
    requested_series = {
        f"{symbol}:{timeframe}" for symbol in SYMBOLS for timeframe in SHADOW_TIMEFRAMES
    }
    dq4["observed_series"] = observed_series
    dq4["unavailable_series"] = sorted(requested_series - set(observed_series))
    dq4["required_transition_counts"] = {
        name: dq4["transition_counts"].get(name, 0) for name in REQUIRED_TRANSITIONS
    }
    payload["dq4"] = dq4
    payload["dq5"] = {
        "status": "PASS",
        "diagnostic_only": True,
        "no_setup_reason_frequencies": dq4["no_setup_reason_frequencies"],
        "blocked_reason_frequencies": dq4["blocked_reason_frequencies"],
        "scarcity_categories": dq4["scarcity_categories"],
        "playbooks": dq4["playbooks"],
        "regime_distribution": dq4["regime_distribution"],
        "session_distribution": dq4["session_distribution"],
    }
    payload["dq6"] = {
        "status": "PASS",
        "profile_only": True,
        **build_structure_profile(structure_samples, timings["replay_seconds"]),
        "measurement_timing_seconds": timings,
        "memory_sample_count": sum(
            int(sample.get("peak_traced_bytes", 0) > 0) for sample in structure_samples
        ),
        "throughput_scope": "HISTORICAL_REPLAY_ADAPTER_ONLY",
        "allocation_hotspots": memory_hotspots,
        "optimization_candidates": [
            "Reduce repeated full-prefix structure scans while preserving point-in-time semantics.",
            (
                "Reuse immutable pivot calculations only after an independently "
                "approved equivalence design."
            ),
            "Profile pandas frame copying and record conversion before selecting an optimization.",
        ],
    }
    payload["status"] = "PASS" if dq4["target_met"] else "BLOCKED_DQ4_TARGET"
    payload["constraints"] = {
        "phase_11_started": False,
        "broker_writes_enabled": False,
        "trading_rules_changed": False,
        "qx_options_scanner": "HUMAN_REQUIRED",
    }
    _write_report(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "dq2": dq2["status"],
                "dq3": dq3["status"],
                "observations": len(dq4_results),
                "target_met": dq4["target_met"],
                "causality_violations": dq3["causality_violation_count"],
                "output": str(args.output),
            },
            indent=2,
        )
    )


def _run_dq2(
    token_manager: SchwabTokenManager,
    client: SchwabApiClient,
    market_provider: SchwabMarketDataProvider,
    quote_provider: SchwabQuoteProvider,
) -> dict[str, Any]:
    health = check_schwab_health(token_manager, client=client)
    status = token_manager.status()
    quote_probe = _quote_probe(quote_provider, "SPY")
    bar_probe, _ = _bar_probe(market_provider, "SPY", "5m")
    violations = list(quote_probe["causality_violations"]) + list(
        bar_probe["causality_violations"]
    )
    passed = all(
        (
            status.configured,
            status.refresh_token_valid,
            not status.restart_required,
            health.market_data_ok,
            quote_probe["available"],
            bar_probe["available"],
            not violations,
        )
    )
    return {
        "status": "PASS" if passed else "BLOCK",
        "authentication_status": (
            "AUTHENTICATED" if not status.restart_required else "UNAUTHENTICATED"
        ),
        "market_api_status": "HEALTHY" if health.market_data_ok else "UNAVAILABLE",
        "refresh_token_status": "VALID" if status.refresh_token_valid else "EXPIRED_OR_UNAVAILABLE",
        "access_token_valid": status.access_token_valid,
        "quote_retrieval": "PASS" if quote_probe["available"] else "FAIL",
        "bar_retrieval": "PASS" if bar_probe["available"] else "FAIL",
        "quote_data_as_of": quote_probe.get("data_as_of"),
        "bar_data_as_of": bar_probe.get("data_as_of"),
        "timestamp_causality_violations": violations,
        "sensitive_values_emitted": False,
    }


def _run_dq3(
    market_provider: SchwabMarketDataProvider,
    quote_provider: SchwabQuoteProvider,
    option_provider: Any,
    account_provider: Any,
    repository: CanonicalSnapshotRepository,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], pd.DataFrame]]:
    observations: list[dict[str, Any]] = []
    replay_frames: dict[tuple[str, str], pd.DataFrame] = {}
    for symbol in SYMBOLS:
        quote = _quote_probe(quote_provider, symbol)
        observations.append(quote)
        for timeframe in BAR_TIMEFRAMES:
            probe, frame = _bar_probe(market_provider, symbol, timeframe)
            observations.append(probe)
            if frame is not None and timeframe in SHADOW_TIMEFRAMES:
                replay_frames[(symbol, timeframe)] = frame
        option_probe, option_snapshot = _snapshot_probe(
            "options", symbol, option_provider.get_option_chain_snapshot
        )
        observations.append(option_probe)
        if option_snapshot is not None and not option_probe["causality_violations"]:
            repository.save_option_chain(
                option_snapshot,
                parse_timestamp(option_snapshot.retrieved_at) or _now(),
            )

    account_probe, account_snapshot = _snapshot_probe(
        "account", "ACCOUNT", lambda _symbol: account_provider.get_account_risk_snapshot()
    )
    observations.append(account_probe)
    if account_snapshot is not None and not account_probe["causality_violations"]:
        repository.save_account(account_snapshot, account_snapshot.retrieved_at or _now())
    return observations, replay_frames


def _quote_probe(provider: SchwabQuoteProvider, symbol: str) -> dict[str, Any]:
    request_started_at = _now()
    try:
        snapshot = provider.get_quote(symbol)
        provider_retrieved_at = _now()
        evaluation_timestamp = _now()
        available = snapshot.last is not None and snapshot.timestamp is not None
        violations = evaluate_visibility(
            snapshot.timestamp, provider_retrieved_at, evaluation_timestamp
        ) if available else []
        age = _age_seconds(snapshot.timestamp, evaluation_timestamp)
        return {
            "kind": "quotes",
            "symbol": symbol,
            "timeframe": None,
            "available": available,
            "stale": available and age is not None and age > FRESHNESS_SECONDS["quotes"],
            "provider_failure": False,
            "failure_code": None,
            "request_started_at": request_started_at.isoformat(),
            "provider_retrieved_at": provider_retrieved_at.isoformat(),
            "evaluation_timestamp": evaluation_timestamp.isoformat(),
            "data_as_of": _iso(snapshot.timestamp),
            "provider_timestamp": _iso(snapshot.timestamp),
            "cache_timestamp": None,
            "observed_age_seconds": age,
            "causality_violations": violations,
        }
    except Exception as exc:
        return _failed_probe("quotes", symbol, None, request_started_at, exc)


def _bar_probe(
    provider: SchwabMarketDataProvider,
    symbol: str,
    timeframe: str,
) -> tuple[dict[str, Any], pd.DataFrame | None]:
    request_started_at = _now()
    try:
        if timeframe == "daily":
            frame = provider.get_daily_bars(BarDataRequest(symbol=symbol, period="1y"))
        else:
            frame = provider.get_intraday_bars(
                IntradayBarDataRequest(
                    symbol=symbol,
                    period="5d",
                    interval_minutes=int(timeframe.removesuffix("m")),
                    include_extended_hours=False,
                )
            )
        provider_retrieved_at = _now()
        evaluation_timestamp = _now()
        data_as_of = _bar_data_as_of(frame, timeframe)
        available = not frame.empty and data_as_of is not None
        violations = evaluate_visibility(
            data_as_of, provider_retrieved_at, evaluation_timestamp
        ) if available else []
        age = _age_seconds(data_as_of, evaluation_timestamp)
        probe = {
            "kind": "bars",
            "symbol": symbol,
            "timeframe": timeframe,
            "available": available,
            "stale": available and age is not None and age > FRESHNESS_SECONDS[timeframe],
            "provider_failure": False,
            "failure_code": None,
            "rows": len(frame),
            "ordered": bool(frame.index.is_monotonic_increasing),
            "unique": bool(frame.index.is_unique),
            "request_started_at": request_started_at.isoformat(),
            "provider_retrieved_at": provider_retrieved_at.isoformat(),
            "evaluation_timestamp": evaluation_timestamp.isoformat(),
            "data_as_of": _iso(data_as_of),
            "provider_timestamp": _iso(data_as_of),
            "cache_timestamp": None,
            "observed_age_seconds": age,
            "causality_violations": violations,
        }
        return probe, frame if available and not violations else None
    except Exception as exc:
        return _failed_probe("bars", symbol, timeframe, request_started_at, exc), None


def _snapshot_probe(
    kind: str,
    symbol: str,
    acquire: Any,
) -> tuple[dict[str, Any], Any]:
    request_started_at = _now()
    try:
        snapshot = acquire(symbol)
        completed_at = _now()
        if snapshot is None:
            return {
                "kind": kind,
                "symbol": symbol,
                "timeframe": None,
                "available": False,
                "stale": False,
                "provider_failure": False,
                "failure_code": "SNAPSHOT_UNAVAILABLE",
                "request_started_at": request_started_at.isoformat(),
                "provider_retrieved_at": completed_at.isoformat(),
                "evaluation_timestamp": completed_at.isoformat(),
                "data_as_of": None,
                "sync_status": "UNAVAILABLE",
                "causality_violations": [],
            }, None
        retrieved_at = getattr(snapshot, "retrieved_at", None)
        evaluation_timestamp = _now()
        violations = evaluate_visibility(
            getattr(snapshot, "data_as_of", None),
            retrieved_at,
            evaluation_timestamp,
        )
        freshness = _value(getattr(snapshot, "freshness", "UNAVAILABLE"))
        age_evidence = _snapshot_age_evidence(snapshot, evaluation_timestamp)
        return {
            "kind": kind,
            "symbol": symbol,
            "timeframe": None,
            "available": True,
            "stale": freshness == "STALE",
            "provider_failure": False,
            "failure_code": None,
            "request_started_at": request_started_at.isoformat(),
            "provider_retrieved_at": _iso(retrieved_at),
            "evaluation_timestamp": evaluation_timestamp.isoformat(),
            "data_as_of": _iso(getattr(snapshot, "data_as_of", None)),
            "provider_timestamp": _iso(getattr(snapshot, "data_as_of", None)),
            "cache_timestamp": None,
            **age_evidence,
            "sync_status": _value(getattr(snapshot, "sync_status", "UNAVAILABLE")),
            "causality_violations": violations,
        }, snapshot
    except Exception as exc:
        return _failed_probe(kind, symbol, None, request_started_at, exc), None


def _run_dq4(
    replay_frames: dict[tuple[str, str], pd.DataFrame],
    database: Path,
    target_observations: int,
    warmup_bars: int,
    max_input_bars: int,
) -> tuple[
    list[Any],
    list[dict[str, Any]],
    dict[str, float],
    list[dict[str, Any]],
]:
    usable = {
        key: frame
        for key, frame in replay_frames.items()
        if len(frame) > warmup_bars
    }
    if not usable:
        return [], [], {
            "replay_seconds": 0.0,
            "allocation_profile_seconds": 0.0,
            "telemetry_persistence_seconds": 0.0,
        }, []
    observations_per_series = max(1, math.ceil(target_observations / len(usable)))
    config = load_rules_config()
    telemetry = ShadowTelemetryRepository(database)
    all_results = []
    structure_samples: list[dict[str, Any]] = []
    memory_hotspots: Counter[str] = Counter()
    replay_elapsed = 0.0
    allocation_elapsed = 0.0
    persistence_elapsed = 0.0

    original_analyze = orchestrator.analyze_smc_structure
    original_pivots = smc_suite.detect_structural_pivots
    original_pullback = smc_suite.find_qualified_pullback_low
    original_rally = smc_suite.find_qualified_rally_high
    helper_counts = Counter()
    profile_queue: list[dict[str, Any]] = []

    def counted_pivots(*args: Any, **kwargs: Any) -> Any:
        helper_counts["pivots"] += 1
        return original_pivots(*args, **kwargs)

    def counted_pullback(*args: Any, **kwargs: Any) -> Any:
        helper_counts["protected"] += 1
        return original_pullback(*args, **kwargs)

    def counted_rally(*args: Any, **kwargs: Any) -> Any:
        helper_counts["protected"] += 1
        return original_rally(*args, **kwargs)

    def profiled_analyze(*args: Any, **kwargs: Any) -> Any:
        symbol = str(kwargs.get("symbol", "UNKNOWN"))
        timeframe = str(kwargs.get("timeframe", "UNKNOWN"))
        pivot_before = helper_counts["pivots"]
        protected_before = helper_counts["protected"]
        result = original_analyze(*args, **kwargs)
        events = list(getattr(result, "events", ()) or ())
        profile_queue.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "bars_processed": len(kwargs.get("bars", ())),
                "pivot_calculation_calls": helper_counts["pivots"] - pivot_before,
                "protected_swing_calculation_calls": helper_counts["protected"] - protected_before,
                "confirmed_pivots": len(getattr(result, "confirmed_pivots", ()) or ()),
                "protected_swings": int(getattr(result, "protected_low", None) is not None)
                + int(getattr(result, "protected_high", None) is not None),
                "bos_events": sum("BOS" in str(event.event_type) for event in events),
                "choch_events": sum("CHOCH" in str(event.event_type) for event in events),
                "peak_traced_bytes": 0,
            }
        )
        return result

    smc_suite.detect_structural_pivots = counted_pivots
    smc_suite.find_qualified_pullback_low = counted_pullback
    smc_suite.find_qualified_rally_high = counted_rally
    orchestrator.analyze_smc_structure = profiled_analyze
    try:
        for (symbol, timeframe), source_frame in sorted(usable.items()):
            input_count = min(
                len(source_frame),
                max_input_bars,
                warmup_bars + observations_per_series,
            )
            frame = source_frame.iloc[-input_count:].copy()
            allocation_started = time.perf_counter()
            memory_sample = _sample_structure_allocations(
                original_analyze,
                frame,
                symbol,
                timeframe,
                memory_hotspots,
            )
            allocation_elapsed += time.perf_counter() - allocation_started
            queue_start = len(profile_queue)
            adapter = HistoricalReplayAdapter(config, symbol, timeframe)
            replay_started = time.perf_counter()
            series_results = adapter.replay(frame, warmup_bars=warmup_bars)
            replay_elapsed += time.perf_counter() - replay_started
            series_profiles = profile_queue[queue_start:]
            if series_profiles:
                series_profiles[0]["peak_traced_bytes"] = memory_sample
            persistence_started = time.perf_counter()
            for result, sample in zip(series_results, series_profiles):
                sample["structure_ms"] = result.stage_latencies.get("structure_ms")
                sample["source_bar_count"] = len(frame)
                _persist_shadow_observation(telemetry, result)
            persistence_elapsed += time.perf_counter() - persistence_started
            structure_samples.extend(series_profiles)
            all_results.extend(series_results)
    finally:
        orchestrator.analyze_smc_structure = original_analyze
        smc_suite.detect_structural_pivots = original_pivots
        smc_suite.find_qualified_pullback_low = original_pullback
        smc_suite.find_qualified_rally_high = original_rally

    hotspots = [
        {"location": location, "sampled_bytes": size}
        for location, size in memory_hotspots.most_common(10)
    ]
    return all_results, structure_samples, {
        "replay_seconds": replay_elapsed,
        "allocation_profile_seconds": allocation_elapsed,
        "telemetry_persistence_seconds": persistence_elapsed,
    }, hotspots


def _persist_shadow_observation(
    repository: ShadowTelemetryRepository,
    result: Any,
) -> None:
    record = build_shadow_record(
        symbol=result.symbol,
        timeframe=result.timeframe,
        evaluation_timestamp=result.evaluation_timestamp,
        legacy_result=None,
        legacy_latency_ms=None,
        v2_result=result,
        v2_latency_ms=_numeric_latency(result.stage_latencies.get("total_ms")),
        config_version=result.config_version,
    )
    record.data_as_of = result.evaluation_timestamp
    record.data_freshness["bars"] = DataDependencyStatus(
        name="bars",
        available=True,
        source="schwab_historical_price_history",
        data_as_of=result.evaluation_timestamp,
        freshness="POINT_IN_TIME",
        publication_state="RESEARCH_ONLY",
        sync_status="SYNCED",
        cache_status="MISS",
        requested_timeframe=result.timeframe,
        observed_timeframe=result.timeframe,
    ).model_dump(mode="json")
    repository.write(record)


def _sample_structure_allocations(
    analyze: Any,
    frame: pd.DataFrame,
    symbol: str,
    timeframe: str,
    hotspots: Counter[str],
) -> int:
    tracemalloc.start(10)
    try:
        analyze(
            bars=frame,
            is_fast_chart=False,
            symbol=symbol,
            timeframe=timeframe,
            break_confirmation_mode="CLOSE",
            evaluation_bar_index=len(frame) - 1,
        )
        _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        for statistic in tracemalloc.take_snapshot().statistics("lineno")[:10]:
            trace = statistic.traceback[0]
            hotspots[f"{Path(trace.filename).name}:{trace.lineno}"] += statistic.size
        return peak_bytes
    finally:
        tracemalloc.stop()


def _complete_lifecycle_buckets(analysis: dict[str, Any]) -> None:
    counts = analysis["lifecycle_distribution"]
    for state in LifecycleState:
        counts.setdefault(state.value, 0)
    analysis["lifecycle_distribution"] = dict(sorted(counts.items()))


def _snapshot_age_evidence(snapshot: Any, evaluation_timestamp: datetime) -> dict[str, Any]:
    observed_age = _age_seconds(getattr(snapshot, "data_as_of", None), evaluation_timestamp)
    contract_ages = [
        float(contract.quote_age_seconds)
        for strikes in getattr(snapshot, "chain", {}).values()
        for sides in strikes.values()
        for contract in sides.values()
        if getattr(contract, "quote_age_seconds", None) is not None
    ]
    if not contract_ages:
        return {
            "observed_age_seconds": observed_age,
            "freshness_basis_age_seconds": observed_age,
            "stale_contract_count": 0,
        }
    return {
        "observed_age_seconds": observed_age,
        "freshness_basis_age_seconds": max(contract_ages),
        "stale_contract_count": sum(age > FRESHNESS_SECONDS["quotes"] for age in contract_ages),
    }


def _summarize_stale_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    stale = [observation for observation in observations if observation.get("stale")]
    by_symbol = Counter(str(observation["symbol"]) for observation in stale)
    by_timeframe = Counter(
        str(observation.get("timeframe") or observation.get("kind")) for observation in stale
    )
    ages = [
        float(observation.get("freshness_basis_age_seconds", observation.get("observed_age_seconds")))
        for observation in stale
        if observation.get("freshness_basis_age_seconds", observation.get("observed_age_seconds"))
        is not None
    ]
    age_series = pd.Series(ages, dtype="float64")
    return {
        "status": "OBSERVATIONAL",
        "stale_count": len(stale),
        "stale_count_by_symbol": dict(sorted(by_symbol.items())),
        "stale_count_by_timeframe": dict(sorted(by_timeframe.items())),
        "age_distribution_seconds": {
            "min": float(age_series.min()) if not age_series.empty else None,
            "p50": float(age_series.quantile(0.50)) if not age_series.empty else None,
            "p95": float(age_series.quantile(0.95)) if not age_series.empty else None,
            "max": float(age_series.max()) if not age_series.empty else None,
        },
        "observations": [
            {
                "kind": observation.get("kind"),
                "symbol": observation.get("symbol"),
                "timeframe": observation.get("timeframe"),
                "observed_age_seconds": observation.get("observed_age_seconds"),
                "freshness_basis_age_seconds": observation.get(
                    "freshness_basis_age_seconds", observation.get("observed_age_seconds")
                ),
                "stale_contract_count": observation.get("stale_contract_count"),
                "provider_timestamp": observation.get("provider_timestamp"),
                "cache_timestamp": observation.get("cache_timestamp"),
                "evaluation_timestamp": observation.get("evaluation_timestamp"),
            }
            for observation in stale
        ],
        "cache_mode": "DIRECT_PROVIDER_NO_CACHE",
    }


def _failed_probe(
    kind: str,
    symbol: str,
    timeframe: str | None,
    request_started_at: datetime,
    exc: Exception,
) -> dict[str, Any]:
    completed_at = _now()
    return {
        "kind": kind,
        "symbol": symbol,
        "timeframe": timeframe,
        "available": False,
        "stale": False,
        "provider_failure": True,
        "failure_code": type(exc).__name__,
        "request_started_at": request_started_at.isoformat(),
        "provider_retrieved_at": completed_at.isoformat(),
        "evaluation_timestamp": completed_at.isoformat(),
        "data_as_of": None,
        "causality_violations": [],
    }


def _bar_data_as_of(frame: pd.DataFrame, timeframe: str) -> datetime | None:
    if frame.empty:
        return None
    index_value = frame.index[-1]
    timestamp = pd.Timestamp(index_value)
    if timeframe == "daily":
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("America/New_York").tz_localize(None)
        session_close = datetime.combine(
            timestamp.date(), wall_time(16, 0), tzinfo=ZoneInfo("America/New_York")
        )
        return session_close.astimezone(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC").to_pydatetime()


def _age_seconds(value: Any, evaluation_timestamp: datetime) -> float | None:
    timestamp = parse_timestamp(value)
    if timestamp is None:
        return None
    return max(0.0, (aware_utc(evaluation_timestamp) - timestamp).total_seconds())


def _numeric_latency(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _iso(value: Any) -> str | None:
    timestamp = parse_timestamp(value)
    return timestamp.isoformat() if timestamp is not None else None


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
