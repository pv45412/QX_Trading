"""OBS1 Sustained Shadow Validation v2 execution and analytics script.

Observes canonical core_v1 behavior over representative historical data,
collects persistent shadow telemetry, evaluates Market Driver stability,
persistence, flip frequency, coverage, and relationship to regime, direction,
and lifecycle states without modifying any rules or trading parameters.
Phase 11 remains strictly locked (no broker writes, no order submissions).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi.testclient import TestClient

from qx.config.rules_config import (
    MarketDriverConfig,
    MarketDriverFreshnessConfig,
    MarketDriverThresholdsConfig,
    load_rules_config,
)
from qx.data.cache import _read_cached_bars
from qx.interfaces.web import create_app
from qx.market_driver.engine import MarketDriverEngine
from qx.market_driver.models import DriverArchetype, PersistenceState
from qx.pipeline.adapters import HistoricalReplayAdapter
from qx.pipeline.models import PIPELINE_VERSION, QXEvaluationContext, QXEvaluationResult
from qx.pipeline.point_in_time import bar_timestamp
from qx.pipeline.replay_analysis import analyze_historical_replay
from qx.pipeline.replay_store import ReplayRepository
from qx.pipeline.shadow_analysis import analyze_shadow_records
from qx.pipeline.shadow_telemetry import (
    ShadowTelemetryRecord,
    ShadowTelemetryRepository,
    build_shadow_record,
)
from qx.pipeline.snapshot_store import CanonicalSnapshotRepository

DEFAULT_SYMBOLS = ("SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "JPM", "XOM")


def observe_symbol(
    client: TestClient,
    repository: ShadowTelemetryRepository,
    symbol: str,
    timeframe: str,
    config_version: str,
    eval_ts: Optional[datetime] = None,
) -> ShadowTelemetryRecord:
    started = time.perf_counter()
    params: dict[str, str] = {"timeframe": timeframe}
    if eval_ts is not None:
        params["evaluation_timestamp"] = eval_ts.isoformat()
    response = client.post(f"/api/v2/qx/evaluate/{symbol}", params=params)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    result = None
    error = None
    evaluation_timestamp = eval_ts or datetime.now(timezone.utc)
    if response.status_code == 200:
        result = QXEvaluationResult.model_validate(response.json())
        evaluation_timestamp = result.evaluation_timestamp
    else:
        error = f"HTTP_{response.status_code}: {response.text[:300]}"
    record = build_shadow_record(
        symbol=symbol,
        timeframe=timeframe,
        evaluation_timestamp=evaluation_timestamp,
        legacy_result=None,
        legacy_latency_ms=None,
        v2_result=result,
        v2_latency_ms=elapsed_ms,
        config_version=config_version,
        v2_error=error,
    )
    repository.write(record)
    return record


def simulate_session_driver_dynamics(
    engine: MarketDriverEngine,
    session_type: str,
    start_time: datetime,
    bars_count: int = 78,  # Standard 6.5-hour RTH session of 5m bars
) -> list[ShadowTelemetryRecord]:
    """Simulates realistic multi-factor market sessions to measure driver stability and flips."""
    records: list[ShadowTelemetryRecord] = []
    prev_result = None

    for b in range(bars_count):
        bar_time = start_time + timedelta(minutes=5 * b)
        # Default factors
        idx_score = 0.0
        sec_score = 0.0
        delta_val = 0.0
        delta_prov = "ESTIMATED_BID_ASK"
        gamma_val = 0.0
        gamma_prov = "ESTIMATED_LOCAL"
        trend_regime = "BALANCED"
        direction = "NEUTRAL"
        lifecycle = "NO_SETUP"

        if session_type == "TREND_UP":
            trend_regime = "TREND_UP"
            direction = "BULLISH"
            lifecycle = "WATCH" if b < 20 else "ARMED"
            # Strong index momentum with occasional sector surges
            idx_score = 65.0 + (5.0 if b % 10 < 5 else -5.0)
            sec_score = 45.0 + (25.0 if 30 <= b <= 45 else 0.0) # Sector surges mid-day
            delta_val = 35.0
        elif session_type == "CHOP_RANGE":
            trend_regime = "RANGE"
            direction = "NEUTRAL"
            lifecycle = "NO_SETUP"
            # Low conviction below primary activation hurdle (35.0)
            idx_score = 15.0 + (10.0 if b % 4 == 0 else -10.0)
            sec_score = 20.0 + (5.0 if b % 6 == 0 else -5.0)
            delta_val = 10.0
        elif session_type == "FAST_DOWNSIDE":
            trend_regime = "TREND_DOWN"
            direction = "BEARISH"
            lifecycle = "WATCH" if b < 10 else "ARMED"
            # Heavy risk-off and negative delta
            idx_score = -78.0
            sec_score = -60.0
            delta_val = -75.0
            delta_prov = "ACTUAL_TRADE_AGGRESSOR"
        elif session_type == "GAMMA_PIN":
            trend_regime = "RANGE"
            direction = "NEUTRAL"
            lifecycle = "NO_SETUP"
            gamma_val = 80.0
            gamma_prov = "ACTUAL_EXCHANGE"
            idx_score = 10.0
            sec_score = 15.0

        ctx = QXEvaluationContext(
            symbol="SPY",
            timeframe="5m",
            evaluation_timestamp=bar_time,
            bars=[{"open": 500.0, "high": 501.0, "low": 499.0, "close": 500.5, "volume": 1000}],
            market_alignment_score=idx_score,
            market_alignment_age_seconds=30,
            relative_strength_score=sec_score,
            sector_rs_age_seconds=30,
            delta_value=delta_val,
            delta_provenance=delta_prov,
            delta_age_seconds=30,
            gamma_value=gamma_val,
            gamma_provenance=gamma_prov,
        )
        res = engine.evaluate(ctx, previous_result=prev_result)
        prev_result = res

        primary = res.primary_driver
        primary_id = primary.driver_id if primary else "UNAVAILABLE"
        primary_str = primary.strength.value if primary else "UNAVAILABLE"
        pers = primary.persistence if primary else None
        pers_state = pers.state.value if pers else "UNAVAILABLE"
        duration_sec = pers.duration_seconds if pers else 0

        records.append(
            ShadowTelemetryRecord(
                symbol="SPY",
                timeframe="5m",
                evaluation_timestamp=bar_time,
                v2_lifecycle_state=lifecycle,
                trend_regime=trend_regime,
                direction_label=direction,
                agreement_status="AGREEMENT",
                publication_state="RESEARCH_ONLY",
                config_version="research_v1",
                pipeline_version="core_v1",
                market_driver_status=res.status.value,
                primary_driver=primary_id,
                driver_strength=primary_str,
                driver_persistence_state=pers_state,
                driver_duration_seconds=duration_sec,
                driver_coverage_status=res.coverage.status,
                confirming_evidence_count=len(res.confirming_evidence),
                conflicting_evidence_count=len(res.conflicting_evidence),
            )
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="OBS1 Sustained Shadow Validation v2")
    parser.add_argument("--database", type=Path, default=Path("data/scanner_history.db"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/bars"))
    parser.add_argument("--intraday-bars", type=Path, default=Path("data/cache/bars/intraday/SPY_10d_5m.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports/obs1_validation"))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--cycles", type=int, default=3)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = load_rules_config()
    approved_symbols = [
        symbol.upper() for symbol in args.symbols if config.shadow_mode.includes(symbol)
    ]
    repository = ShadowTelemetryRepository(args.database)
    app = create_app(database=args.database, cache_dir=args.cache_dir)
    batch_records: list[ShadowTelemetryRecord] = []
    started_at = datetime.now(timezone.utc)

    # 1. Live Shadow Observations (at now)
    print(f"Executing {args.cycles} live observation cycles across {len(approved_symbols)} symbols...")
    with TestClient(app) as client:
        for cycle in range(args.cycles):
            for symbol in approved_symbols:
                rec = observe_symbol(client, repository, symbol, "1d", config.version)
                batch_records.append(rec)

        # Point-in-time session observations (at latest completed daily close)
        pit_ts = datetime(2026, 9, 8, 19, 30, tzinfo=timezone.utc)
        print(f"Executing point-in-time observation cycles across {len(approved_symbols)} symbols...")
        for symbol in approved_symbols:
            rec = observe_symbol(client, repository, symbol, "1d", config.version, eval_ts=pit_ts)
            batch_records.append(rec)

    # 2. Historical Replay Observations (SPY 5m intraday)
    print("Executing historical replay for intraday driver dynamics...")
    historical_bars = _read_cached_bars(args.intraday_bars)
    replay_bars = historical_bars.iloc[-250:].copy() if len(historical_bars) > 250 else historical_bars.copy()
    last_timestamp = bar_timestamp(replay_bars.iloc[-1])
    snapshots = CanonicalSnapshotRepository(args.database)
    option_snapshots = snapshots.list_option_chains("SPY", last_timestamp) if last_timestamp else []
    account_snapshots = snapshots.list_accounts(last_timestamp) if last_timestamp else []
    adapter = HistoricalReplayAdapter(config, "SPY", "5m")
    replay_report = analyze_historical_replay(
        adapter,
        replay_bars,
        warmup_bars=50,
        option_chain_snapshots=option_snapshots,
        account_snapshots=account_snapshots,
    )
    run_id = ReplayRepository(args.database).save(replay_report)

    # Convert replay observations to shadow telemetry records
    replay_shadow_records: list[ShadowTelemetryRecord] = []
    for obs in replay_report.observations:
        replay_shadow_records.append(
            ShadowTelemetryRecord(
                symbol=obs.symbol,
                timeframe=obs.timeframe,
                evaluation_timestamp=obs.timestamp,
                v2_lifecycle_state=obs.lifecycle_state.value if hasattr(obs.lifecycle_state, "value") else str(obs.lifecycle_state),
                trend_regime=obs.trend_regime,
                volatility_regime=obs.volatility_regime,
                gamma_regime=obs.gamma_regime,
                session_regime=obs.session_regime,
                direction_label=obs.direction_label,
                v2_primary_playbook=obs.playbook,
                evidence_coverage=obs.direction_coverage,
                coverage_status=obs.coverage_status,
                agreement_status="AGREEMENT",
                publication_state=obs.publication_state,
                config_version=config.version,
                pipeline_version=obs.pipeline_version,
                market_driver_status=obs.market_driver_status,
                primary_driver=obs.primary_driver,
                driver_strength=obs.driver_strength,
                driver_persistence_state=obs.driver_persistence_state,
                driver_coverage_status=obs.driver_coverage_status,
            )
        )

    # 3. Representative Archetype Session Simulations (Trend, Chop, Downside, Pin)
    print("Executing representative market session simulations (78 bars each)...")
    driver_engine = MarketDriverEngine(config.market_driver)
    sim_base_time = datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc)
    trend_recs = simulate_session_driver_dynamics(driver_engine, "TREND_UP", sim_base_time, 78)
    chop_recs = simulate_session_driver_dynamics(driver_engine, "CHOP_RANGE", sim_base_time + timedelta(days=1), 78)
    downside_recs = simulate_session_driver_dynamics(driver_engine, "FAST_DOWNSIDE", sim_base_time + timedelta(days=2), 78)
    pin_recs = simulate_session_driver_dynamics(driver_engine, "GAMMA_PIN", sim_base_time + timedelta(days=3), 78)

    session_sim_records = trend_recs + chop_recs + downside_recs + pin_recs

    # 4. Analyze all datasets
    batch_analysis = analyze_shadow_records(batch_records)
    replay_analysis = analyze_shadow_records(replay_shadow_records)
    session_sim_analysis = analyze_shadow_records(session_sim_records)

    all_records = batch_records + replay_shadow_records + session_sim_records
    combined_analysis = analyze_shadow_records(all_records)

    # 5. Save JSON dataset
    telemetry_json_path = args.output_dir / "obs1_shadow_telemetry.json"
    dataset_payload = {
        "task_id": "OBS1",
        "title": "Sustained Shadow Validation v2",
        "timestamp": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "config_version": config.version,
        "execution_locked": True,
        "phase_11_locked": True,
        "live_observations_count": len(batch_records),
        "replay_observations_count": len(replay_shadow_records),
        "session_simulation_observations_count": len(session_sim_records),
        "total_observations": len(all_records),
        "live_analysis": batch_analysis.model_dump(mode="json"),
        "replay_analysis": replay_analysis.model_dump(mode="json"),
        "session_simulation_analysis": session_sim_analysis.model_dump(mode="json"),
        "combined_analysis": combined_analysis.model_dump(mode="json"),
        "replay_summary": {
            "run_id": run_id,
            "observations": len(replay_report.observations),
            "transitions": len(replay_report.transitions),
            "outcomes": len(replay_report.outcomes),
            "segments": [s.model_dump(mode="json") for s in replay_report.segments],
        },
        "session_metrics": {
            "trend_up": {
                "observations": len(trend_recs),
                "flips": analyze_shadow_records(trend_recs).driver_flips_count,
                "transitions": analyze_shadow_records(trend_recs).driver_transitions,
                "driver_counts": analyze_shadow_records(trend_recs).driver_counts,
            },
            "chop_range": {
                "observations": len(chop_recs),
                "flips": analyze_shadow_records(chop_recs).driver_flips_count,
                "driver_counts": analyze_shadow_records(chop_recs).driver_counts,
            },
            "fast_downside": {
                "observations": len(downside_recs),
                "flips": analyze_shadow_records(downside_recs).driver_flips_count,
                "driver_counts": analyze_shadow_records(downside_recs).driver_counts,
            },
            "gamma_pin": {
                "observations": len(pin_recs),
                "flips": analyze_shadow_records(pin_recs).driver_flips_count,
                "driver_counts": analyze_shadow_records(pin_recs).driver_counts,
            },
        },
    }
    telemetry_json_path.write_text(json.dumps(dataset_payload, indent=2), encoding="utf-8")
    print(f"Telemetry dataset written to: {telemetry_json_path}")
    print(f"Total observations analyzed: {len(all_records)}")


if __name__ == "__main__":
    main()
