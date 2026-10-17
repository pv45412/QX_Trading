"""Run a bounded canonical bar replay and persist observational Track 2 metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qx.config.rules_config import load_rules_config
from qx.data.cache import _read_cached_bars
from qx.pipeline.adapters import HistoricalReplayAdapter
from qx.pipeline.point_in_time import bar_timestamp
from qx.pipeline.replay_analysis import analyze_historical_replay
from qx.pipeline.replay_store import ReplayRepository
from qx.pipeline.snapshot_store import CanonicalSnapshotRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--bars", type=Path, default=Path("data/cache/bars/intraday/SPY_10d_5m.csv"))
    parser.add_argument("--database", type=Path, default=Path("data/scanner_history.db"))
    parser.add_argument("--output", type=Path, default=Path("data/reports/track2_replay_spy.json"))
    parser.add_argument("--warmup-bars", type=int, default=50)
    parser.add_argument("--max-bars", type=int, default=250)
    args = parser.parse_args()

    historical_bars = _read_cached_bars(args.bars)
    if args.max_bars > 0 and len(historical_bars) > args.max_bars:
        historical_bars = historical_bars.iloc[-args.max_bars:].copy()
    last_timestamp = bar_timestamp(historical_bars.iloc[-1])
    if last_timestamp is None:
        raise ValueError("Replay bars require timestamped rows")
    snapshots = CanonicalSnapshotRepository(args.database)
    option_snapshots = snapshots.list_option_chains(args.symbol, last_timestamp)
    account_snapshots = snapshots.list_accounts(last_timestamp)
    adapter = HistoricalReplayAdapter(load_rules_config(), args.symbol, args.timeframe)
    report = analyze_historical_replay(
        adapter,
        historical_bars,
        warmup_bars=args.warmup_bars,
        option_chain_snapshots=option_snapshots,
        account_snapshots=account_snapshots,
    )
    run_id = ReplayRepository(args.database).save(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    payload["replay_run_id"] = run_id
    payload["source_bars"] = str(args.bars)
    payload["option_snapshot_count"] = len(option_snapshots)
    payload["account_snapshot_count"] = len(account_snapshots)
    payload["input_bar_count"] = len(historical_bars)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "replay_run_id": run_id,
                "observations": len(report.observations),
                "transitions": len(report.transitions),
                "outcomes": len(report.outcomes),
                "option_snapshots": len(option_snapshots),
                "account_snapshots": len(account_snapshots),
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
