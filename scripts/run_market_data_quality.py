"""Generate the approved-symbol canonical market-data quality report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from qx.data.dashboard_refresh import DashboardRefresh
from qx.pipeline.market_data_quality import load_audited_bars


SYMBOLS = ("SPY", "QQQ", "SPX", "NVDA", "AAPL", "MSFT", "TSLA", "AMD", "JPM", "XOM")
TIMEFRAMES = ("1m", "5m", "15m", "daily")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/bars"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/reports/market_data_quality_report.json"),
    )
    args = parser.parse_args()
    evaluation_timestamp = datetime.now(timezone.utc)
    try:
        active_cache = DashboardRefresh(args.cache_dir, lambda: None).active_cache()
    except (OSError, ValueError, FileNotFoundError):
        active_cache = None

    observations = []
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            result = load_audited_bars(
                args.cache_dir,
                symbol,
                timeframe,
                evaluation_timestamp,
                active_cache,
            )
            observations.append(result.quality_report.model_dump(mode="json"))

    status_counts = Counter(item["status"] for item in observations)
    reason_counts = Counter(
        reason for item in observations for reason in item.get("reason_codes", [])
    )
    payload = {
        "report_type": "MarketDataQualityReport",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_timestamp": evaluation_timestamp.isoformat(),
        "symbols": list(SYMBOLS),
        "timeframes": list(TIMEFRAMES),
        "observation_count": len(observations),
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "observations": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "observations"}, indent=2))


if __name__ == "__main__":
    main()
