import json
from pathlib import Path
from collections.abc import Sequence

import pandas as pd
import typer

from qx.automation.morning import get_task_status, log_file_status, overnight_log_path
from qx.backtesting.engine import (
    backtest_rectangle_breakouts,
    backtest_rectangle_universe,
    sweep_backtest_parameters,
)
from qx.brokers.schwab.auth import SchwabAuthError, SchwabTokenManager
from qx.brokers.schwab.health import check_schwab_health
from qx.charts.rectangle import write_rectangle_chart
from qx.config.settings import get_settings
from qx.core.engine import ScannerEngine
from qx.core.session import ScanSession
from qx.data.cache import CachedMarketDataProvider
from qx.data.cache_status import assess_cache_health, summarize_bar_cache, universe_cache_coverage
from qx.data.factory import build_fallback_market_data_provider
from qx.data.metadata import SymbolMetadataStore
from qx.data.providers import CsvMarketDataProvider, YFinanceMarketDataProvider
from qx.data.universe import UNIVERSE_OPTIONS, UniverseLoader
from qx.exports.scanner_results import write_scanner_results_csv
from qx.market.sector_rotation import sector_rotation_frame
from qx.models.backtest import BacktestParameters
from qx.models.market import BarDataRequest
from qx.patterns.profiles import PROFILE_OPTIONS, build_rectangle_parameters
from qx.processing.data_pipeline import refresh_bar_cache
from qx.processing.overnight_workflow import run_overnight_workflow
from qx.reports.command_center import build_command_center
from qx.reports.daily_workflow import build_daily_workflow_report
from qx.reports.morning import build_morning_report, morning_report_frame, sector_summary_frame
from qx.storage.command_center import (
    CommandCenterSnapshotMetadata,
    SQLiteCommandCenterSnapshotRepository,
)
from qx.storage.feature_cache import SQLiteFeatureCache
from qx.storage.options import SQLiteOptionIdeaRepository
from qx.storage.pipeline import PipelineRunMetadata, SQLitePipelineRepository
from qx.storage.sqlite import SQLiteScanRepository
from qx.storage.workflow import SQLiteWorkflowRepository

app = typer.Typer(help="Run scanner workflows.")


@app.command()
def scan_csv(
    symbol: str,
    data_dir: Path = typer.Option(Path("data/raw"), help="Directory containing SYMBOL.csv files."),
) -> None:
    """Analyze one symbol from a local OHLCV CSV file."""
    provider = CsvMarketDataProvider(data_dir)
    result = ScanSession(provider=provider).run([symbol])
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def scan_yfinance(
    symbols: list[str] = typer.Argument(..., help="One or more ticker symbols."),
    period: str = typer.Option("1y", help="History period passed to yfinance."),
    profile: str = typer.Option("Strict institutional", help=f"Rule profile: {', '.join(PROFILE_OPTIONS)}."),
    lookback: int = typer.Option(40, min=30, max=60, help="Rectangle window in daily bars."),
    max_range_pct: float = typer.Option(0.10, help="Maximum rectangle height as support percent."),
    output_csv: Path | None = typer.Option(None, help="Optional CSV output path."),
    output_scanner_results: Path | None = typer.Option(
        None,
        help="Optional QuantX scanner_results.csv export path.",
    ),
    output_json: Path | None = typer.Option(None, help="Optional JSON output path."),
    chart_dir: Path | None = typer.Option(None, help="Optional directory for HTML charts."),
    database: Path | None = typer.Option(None, help="Optional SQLite database path."),
) -> None:
    """Analyze one or more symbols using yfinance daily data."""
    provider = CachedMarketDataProvider(YFinanceMarketDataProvider())
    parameters = build_rectangle_parameters(profile, lookback=lookback, max_range_pct=max_range_pct)
    result = ScannerEngine(
        provider=provider,
        parameters=parameters,
        feature_cache=SQLiteFeatureCache(),
    ).scan_symbols(symbols, period=period)
    _write_outputs(result.model_dump(), output_json=output_json)
    if output_csv:
        _candidate_frame(result).to_csv(output_csv, index=False)
    if output_scanner_results:
        write_scanner_results_csv(result, output_scanner_results)
    if database:
        run_id = SQLiteScanRepository(database).save_scan_run(result)
        typer.echo(f"Saved scan run {run_id} to {database}")
    if chart_dir:
        for candidate in result.candidates:
            bars = provider.get_daily_bars(request=_bar_request(candidate.symbol, period))
            write_rectangle_chart(chart_dir / f"{candidate.symbol}.html", bars, candidate)
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def scan_universe(
    universe: str = typer.Option(
        "sp500",
        help="Universe to scan: dow_jones, nasdaq_100, russell_2000, sp100, sp500.",
    ),
    period: str = typer.Option("1y", help="History period passed to the market data provider."),
    data_source: str = typer.Option("schwab", help="Market data provider: schwab or yfinance."),
    profile: str = typer.Option("Strict institutional", help=f"Rule profile: {', '.join(PROFILE_OPTIONS)}."),
    lookback: int = typer.Option(40, min=30, max=60, help="Rectangle window in daily bars."),
    max_range_pct: float = typer.Option(0.10, help="Maximum rectangle height as support percent."),
    min_score: float = typer.Option(0.70, help="Only print candidates at or above this score."),
    limit: int = typer.Option(50, help="Maximum candidates to print."),
    output_csv: Path | None = typer.Option(None, help="Optional CSV output path."),
    output_scanner_results: Path | None = typer.Option(
        None,
        help="Optional QuantX scanner_results.csv export path.",
    ),
    output_json: Path | None = typer.Option(None, help="Optional JSON output path."),
    database: Path | None = typer.Option(None, help="Optional SQLite database path."),
) -> None:
    """Scan a full symbol universe such as the S&P 500."""
    symbols = UniverseLoader().load(universe)
    provider = _cached_provider(data_source)
    parameters = build_rectangle_parameters(profile, lookback=lookback, max_range_pct=max_range_pct)
    result = ScannerEngine(
        provider=provider,
        parameters=parameters,
        feature_cache=SQLiteFeatureCache(),
    ).scan_symbols(symbols, period=period)
    filtered = [candidate for candidate in result.candidates if candidate.setup_score >= min_score][:limit]

    if output_csv:
        _candidate_frame(result).to_csv(output_csv, index=False)
    if output_scanner_results:
        write_scanner_results_csv(result, output_scanner_results)
    _write_outputs(result.model_dump(), output_json=output_json)
    if database:
        run_id = SQLiteScanRepository(database).save_scan_run(result)
        typer.echo(f"Saved scan run {run_id} to {database}")

    typer.echo(f"Scanned {result.total_symbols} symbols; {result.failed_symbols} failed.")
    typer.echo(pd.DataFrame(_summary_rows(filtered)).to_string(index=False))


@app.command()
def warm_cache(
    universe: str = typer.Option(
        "sp500",
        help="Universe to preload: all, dow_jones, nasdaq_100, russell_2000, sp100, sp500.",
    ),
    period: str = typer.Option("2y", help="History period to cache."),
    data_source: str = typer.Option("schwab", help="Market data provider: schwab or yfinance."),
    refresh: bool = typer.Option(False, help="Force re-download even when a local cache file exists."),
    limit: int | None = typer.Option(None, help="Optional symbol limit for testing."),
) -> None:
    """Preload daily OHLCV data into the local cache for faster later scans."""
    symbols = _warm_cache_symbols(universe)
    if limit is not None:
        symbols = symbols[:limit]

    provider = _cached_provider(data_source, refresh=refresh)
    failures: list[dict[str, str]] = []
    for index, symbol in enumerate(symbols, start=1):
        try:
            provider.get_daily_bars(_bar_request(symbol, period))
        except Exception as exc:
            failures.append({"symbol": symbol, "message": str(exc)})
        if index == 1 or index % 25 == 0 or index == len(symbols):
            typer.echo(f"Cached {index}/{len(symbols)} symbols; failures={len(failures)}")

    typer.echo(
        f"Warm cache complete: symbols={len(symbols)}, period={period}, failures={len(failures)}"
    )
    if failures:
        typer.echo(pd.DataFrame(failures).head(25).to_string(index=False))


@app.command()
def overnight_refresh(
    period: str = typer.Option("2y", help="History period to cache."),
    data_source: str = typer.Option("schwab", help="Market data provider: schwab or yfinance."),
    refresh: bool = typer.Option(False, help="Force re-download even when a local cache file exists."),
) -> None:
    """Refresh every configured index universe for a fast next-day local scan."""
    symbols = _warm_cache_symbols("all")
    result = refresh_bar_cache(
        symbols,
        build_fallback_market_data_provider(data_source),
        period=period,
        refresh=refresh,
    )
    typer.echo(
        f"Overnight refresh complete: symbols={result.total_symbols}, "
        f"cached={result.refreshed_symbols}, failures={result.failed_symbols}"
    )
    if result.failures:
        typer.echo(pd.DataFrame([failure.__dict__ for failure in result.failures]).head(25).to_string(index=False))


@app.command()
def nightly_scan(
    universe: str = typer.Option(
        "all",
        help="Universe to refresh and scan: all, dow_jones, nasdaq_100, russell_2000, sp100, sp500.",
    ),
    period: str = typer.Option("2y", help="History period to cache and scan."),
    profile: str = typer.Option("Classic rectangle", help=f"Rule profile: {', '.join(PROFILE_OPTIONS)}."),
    lookback: int = typer.Option(40, min=30, max=60, help="Rectangle window in daily bars."),
    max_range_pct: float = typer.Option(0.25, help="Maximum rectangle height as support percent."),
    data_source: str = typer.Option("schwab", help="Market data provider: schwab or yfinance."),
    refresh: bool = typer.Option(False, help="Force bar re-download before scanning."),
    database: Path = typer.Option(Path("data/scanner_history.db"), help="Scan-history SQLite path."),
) -> None:
    """Refresh local data, compute cached features, and save a scan-history run."""
    symbols = _warm_cache_symbols(universe)
    provider = _cached_provider(data_source, refresh=refresh)
    parameters = build_rectangle_parameters(profile, lookback=lookback, max_range_pct=max_range_pct)
    result = ScannerEngine(
        provider=provider,
        parameters=parameters,
        feature_cache=SQLiteFeatureCache(),
    ).scan_symbols(symbols, period=period)
    run_id = SQLiteScanRepository(database).save_scan_run(result)
    typer.echo(
        f"Nightly scan saved run {run_id}: symbols={result.total_symbols}, "
        f"candidates={len(result.candidates)}, passed={result.passed_symbols}, "
        f"data_failures={result.failed_symbols}"
    )


@app.command()
def morning_report(
    database: Path = typer.Option(Path("data/scanner_history.db"), help="Scan-history SQLite path."),
    min_rank_score: float = typer.Option(0.55, help="Minimum composite rank score."),
    limit: int = typer.Option(25, help="Maximum rows per bucket."),
    output_dir: Path | None = typer.Option(None, help="Optional directory for report CSV files."),
) -> None:
    """Print watchlist buckets from the latest saved scan run."""
    report = build_morning_report(
        SQLiteScanRepository(database),
        min_rank_score=min_rank_score,
        limit=limit,
    )
    if report.run is None:
        typer.echo("No saved scan runs found.")
        raise typer.Exit(code=1)

    typer.echo(f"Morning report from run {report.run.id} ({report.run.created_at})")
    sector_frame = sector_summary_frame(report.top_candidates)
    typer.echo("\nSector Summary")
    typer.echo(sector_frame.to_string(index=False) if not sector_frame.empty else "No sectors.")
    sections = {
        "top_candidates": report.top_candidates,
        "new_candidates": report.new_candidates,
        "improving_candidates": report.improving_candidates,
        "near_breakout_candidates": report.near_breakout_candidates,
        "extended_leaders": report.extended_leaders,
    }
    for name, candidates in sections.items():
        frame = morning_report_frame(candidates)
        typer.echo(f"\n{name.replace('_', ' ').title()} ({len(candidates)})")
        typer.echo(frame.to_string(index=False) if not frame.empty else "No symbols.")
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            frame.to_csv(output_dir / f"{name}.csv", index=False)


@app.command()
def daily_workflow(
    database: Path = typer.Option(Path("data/scanner_history.db"), help="Scan-history SQLite path."),
    period: str = typer.Option("2y", help="Market history period for regime and sector rotation."),
    data_source: str = typer.Option("schwab", help="Market data provider: schwab or yfinance."),
    min_rank_score: float = typer.Option(0.55, help="Minimum composite rank score."),
    limit: int = typer.Option(25, help="Maximum watchlist rows."),
) -> None:
    """Print the daily workflow: regime, sectors, watchlist, and action plan."""
    report = build_daily_workflow_report(
        provider=_cached_provider(data_source),
        repository=SQLiteScanRepository(database),
        period=period,
        min_rank_score=min_rank_score,
        limit=limit,
    )
    workflow_run_id = SQLiteWorkflowRepository(database).save(report)
    typer.echo(f"Market Regime: {report.regime.label} | Risk: {report.regime.risk_level}")
    typer.echo(f"Saved workflow run {workflow_run_id} to {database}")
    typer.echo(
        f"SPY 20D={report.regime.spy_return_20d:.1%}, "
        f"QQQ 20D={format(report.regime.qqq_return_20d, '.1%') if report.regime.qqq_return_20d is not None else 'unavailable'}, "
        f"IWM 20D={format(report.regime.iwm_return_20d, '.1%') if report.regime.iwm_return_20d is not None else 'unavailable'}"
    )
    typer.echo("\nSector Leadership")
    typer.echo(sector_rotation_frame(report.sector_rotation).to_string(index=False))
    typer.echo("\nAction Plan")
    for item in report.action_plan:
        typer.echo(f"- {item}")
    typer.echo("\nTop Watchlist")
    frame = morning_report_frame(report.morning_report.top_candidates)
    typer.echo(frame.to_string(index=False) if not frame.empty else "No saved candidates.")


@app.command()
def overnight_workflow(
    universe: str = typer.Option(
        "sp500",
        help="Universe to refresh and scan: all, dow_jones, nasdaq_100, russell_2000, sp100, sp500.",
    ),
    period: str = typer.Option("2y", help="History period to cache and scan."),
    profile: str = typer.Option("Classic rectangle", help=f"Rule profile: {', '.join(PROFILE_OPTIONS)}."),
    lookback: int = typer.Option(40, min=30, max=60, help="Rectangle window in daily bars."),
    max_range_pct: float = typer.Option(0.25, help="Maximum rectangle height as support percent."),
    data_source: str = typer.Option("schwab", help="Market data provider: schwab or yfinance."),
    refresh: bool = typer.Option(False, help="Force bar re-download before scanning."),
    database: Path = typer.Option(Path("data/scanner_history.db"), help="SQLite storage path."),
) -> None:
    """Warm local data, scan, save workflow, and prepare the app for fast morning use."""
    metadata = PipelineRunMetadata(
        universe=universe,
        period=period,
        profile=profile,
        data_source=data_source,
        lookback=lookback,
        max_range_pct=max_range_pct,
        refresh=refresh,
    )
    result = run_overnight_workflow(
        provider=build_fallback_market_data_provider(data_source),
        universe=metadata.universe,
        period=metadata.period,
        profile=metadata.profile,
        lookback=metadata.lookback,
        max_range_pct=metadata.max_range_pct,
        refresh=metadata.refresh,
        database=database,
        token_manager=SchwabTokenManager(get_settings()),
    )
    pipeline_run_id = SQLitePipelineRepository(database).save(result, metadata)
    command_center = build_command_center(
        provider=_cached_provider(data_source),
        repository=SQLiteScanRepository(database),
        period=period,
        min_rank_score=0.55,
        limit=25,
        option_repository=SQLiteOptionIdeaRepository(database),
    )
    snapshot_id = SQLiteCommandCenterSnapshotRepository(database).save(
        command_center,
        CommandCenterSnapshotMetadata(
            source="overnight_workflow",
            period=period,
            data_source=data_source,
            universe=universe,
        ),
    )
    typer.echo(
        f"Overnight workflow complete: pipeline_run={pipeline_run_id}, cache={result.cache_refresh.refreshed_symbols}/"
        f"{result.cache_refresh.total_symbols}, scan_run={result.scan_run_id}, "
        f"workflow_run={result.workflow_run_id}, candidates={len(result.scan_result.candidates)}, "
        f"failures={result.scan_result.failed_symbols}, command_center_snapshot={snapshot_id}"
    )
    typer.echo(f"Regime: {result.workflow_report.regime.label} | Risk: {result.workflow_report.regime.risk_level}")
    if result.auth_warning:
        typer.echo(f"Schwab auth warning: {result.auth_warning}")


@app.command()
def pipeline_history(
    database: Path = typer.Option(Path("data/scanner_history.db"), help="SQLite storage path."),
    limit: int = typer.Option(10, help="Maximum pipeline runs to print."),
) -> None:
    """Print recent operational pipeline runs."""
    runs = SQLitePipelineRepository(database).list_runs(limit=limit)
    if not runs:
        typer.echo("No pipeline runs saved.")
        return
    typer.echo(
        pd.DataFrame(
            [
                {
                    "id": run.id,
                    "created_at": run.created_at,
                    "universe": run.universe,
                    "period": run.period,
                    "profile": run.profile,
                    "data_source": run.data_source,
                    "scan_run_id": run.scan_run_id,
                    "workflow_run_id": run.workflow_run_id,
                    "cached": run.cached_symbols,
                    "cache_failures": run.cache_failures,
                    "scanned": run.scanned_symbols,
                    "candidates": run.candidates,
                    "scan_failures": run.scan_failures,
                    "regime": run.regime_label,
                    "risk": run.risk_level,
                    "auth_warning": run.auth_warning,
                }
                for run in runs
            ]
        ).to_string(index=False)
    )


@app.command()
def cache_status(
    universe: str = typer.Option("sp500", help="Universe coverage to check."),
    period: str = typer.Option("2y", help="Cached period to check."),
    max_age_hours: int = typer.Option(36, help="Freshness threshold for cache health."),
) -> None:
    """Show local bar-cache, coverage, schedule, and overnight-log readiness."""
    summary = summarize_bar_cache()
    symbols = _warm_cache_symbols(universe)
    coverage = universe_cache_coverage(symbols, period=period)
    health = assess_cache_health(symbols, period=period, max_age_hours=max_age_hours)
    task = get_task_status()
    overnight_log = log_file_status(overnight_log_path())
    typer.echo(
        f"Cache files={summary.total_files}, symbols={summary.total_symbols}, "
        f"size_mb={summary.total_size_mb}, periods={summary.periods}"
    )
    typer.echo(
        f"Coverage {universe}/{period}: {coverage.cached}/{coverage.total} "
        f"({coverage.coverage:.1%}); missing={coverage.missing}"
    )
    typer.echo(
        f"Health: {health.label}; ready={health.ready}; stale={health.stale}; "
        f"latest={health.latest_modified_at or 'n/a'}"
    )
    typer.echo(f"Health note: {health.message}")
    typer.echo(
        f"Scheduled task: {task.state}; last_result={task.last_task_result_label}; "
        f"next_run={task.next_run_time or 'n/a'}"
    )
    typer.echo(
        f"Overnight log: exists={overnight_log.exists}; empty={overnight_log.empty}; "
        f"size_bytes={overnight_log.size_bytes}; updated={overnight_log.last_write_time or 'n/a'}"
    )
    if coverage.missing_symbols:
        typer.echo("Missing sample: " + ", ".join(coverage.missing_symbols[:25]))


@app.command()
def refresh_metadata() -> None:
    """Refresh cached S&P 500 sector and industry metadata."""
    count = SymbolMetadataStore().refresh_sp500()
    typer.echo(f"Refreshed metadata for {count} S&P 500 symbols.")


@app.command()
def schwab_status() -> None:
    """Show Schwab auth configuration and token refresh readiness."""
    status = SchwabTokenManager(get_settings()).status()
    typer.echo(f"Configured: {status.configured}")
    typer.echo(f"Has token: {status.has_token}")
    typer.echo(f"Access token valid: {status.access_token_valid}")
    typer.echo(f"Refresh token valid: {status.refresh_token_valid}")
    typer.echo(f"OAuth restart required: {status.restart_required}")
    typer.echo(status.message)
    if status.authorization_url:
        typer.echo(f"Authorization URL: {status.authorization_url}")


@app.command()
def schwab_health() -> None:
    """Run a Schwab auth and SPY market-data smoke check."""
    health = check_schwab_health(SchwabTokenManager(get_settings()))
    typer.echo(health.message)
    raise typer.Exit(code=0 if health.market_data_ok else 1)


@app.command()
def schwab_exchange_code(authorization_code_or_callback_url: str) -> None:
    """Exchange a one-time Schwab authorization code or callback URL and save local tokens."""
    try:
        SchwabTokenManager(get_settings()).exchange_authorization_code(authorization_code_or_callback_url)
    except SchwabAuthError as exc:
        typer.echo(f"Schwab authorization failed: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo("Saved Schwab token file.")


@app.command()
def backtest_yfinance(
    symbol: str,
    period: str = typer.Option("2y", help="History period passed to yfinance."),
    profile: str = typer.Option("Strict institutional", help=f"Rule profile: {', '.join(PROFILE_OPTIONS)}."),
    lookback: int = typer.Option(40, min=30, max=60, help="Rectangle window in daily bars."),
    max_range_pct: float = typer.Option(0.10, help="Maximum rectangle height as support percent."),
    profit_target_pct: float = typer.Option(0.03, help="Profit target as decimal percent."),
    stop_loss_pct: float = typer.Option(0.03, help="Stop loss as decimal percent."),
    max_holding_bars: int = typer.Option(20, help="Maximum bars to hold after entry."),
    min_setup_score: float = typer.Option(0.70, help="Minimum setup score before waiting for breakout."),
    entry_window_bars: int = typer.Option(5, help="Bars after setup to wait for breakout trigger."),
    require_breakout_trigger: bool = typer.Option(True, help="Require price to touch breakout level before entry."),
) -> None:
    """Run a basic historical rectangle breakout backtest for one symbol."""
    provider = CachedMarketDataProvider(YFinanceMarketDataProvider())
    bars = provider.get_daily_bars(request=_bar_request(symbol, period))
    result = backtest_rectangle_breakouts(
        symbol,
        bars,
        scan_parameters=build_rectangle_parameters(
            profile,
            lookback=lookback,
            max_range_pct=max_range_pct,
        ),
        backtest_parameters=BacktestParameters(
            profit_target_pct=profit_target_pct,
            stop_loss_pct=stop_loss_pct,
            max_holding_bars=max_holding_bars,
            min_setup_score=min_setup_score,
            entry_window_bars=entry_window_bars,
            require_breakout_trigger=require_breakout_trigger,
        ),
    )
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def backtest_universe(
    universe: str = typer.Option("sp100", help="Universe to backtest."),
    period: str = typer.Option("2y", help="History period passed to yfinance."),
    profile: str = typer.Option("Classic rectangle", help=f"Rule profile: {', '.join(PROFILE_OPTIONS)}."),
    lookback: int = typer.Option(40, min=30, max=60, help="Rectangle window in daily bars."),
    max_range_pct: float = typer.Option(0.25, help="Maximum rectangle height as support percent."),
    limit: int | None = typer.Option(None, help="Optional symbol limit for testing."),
    profit_target_pct: float = typer.Option(0.03, help="Profit target as decimal percent."),
    stop_loss_pct: float = typer.Option(0.03, help="Stop loss as decimal percent."),
    max_holding_bars: int = typer.Option(20, help="Maximum bars to hold after entry."),
    min_setup_score: float = typer.Option(0.70, help="Minimum setup score before waiting for breakout."),
    entry_window_bars: int = typer.Option(5, help="Bars after setup to wait for breakout trigger."),
    require_breakout_trigger: bool = typer.Option(True, help="Require price to touch breakout level before entry."),
) -> None:
    """Backtest scanner behavior across a symbol universe."""
    symbols = _warm_cache_symbols(universe)
    if limit is not None:
        symbols = symbols[:limit]
    result = backtest_rectangle_universe(
        symbols,
        CachedMarketDataProvider(YFinanceMarketDataProvider()),
        period=period,
        scan_parameters=build_rectangle_parameters(
            profile,
            lookback=lookback,
            max_range_pct=max_range_pct,
        ),
        backtest_parameters=BacktestParameters(
            profit_target_pct=profit_target_pct,
            stop_loss_pct=stop_loss_pct,
            max_holding_bars=max_holding_bars,
            min_setup_score=min_setup_score,
            entry_window_bars=entry_window_bars,
            require_breakout_trigger=require_breakout_trigger,
        ),
    )
    typer.echo(
        f"Backtested {result.total_symbols} symbols; trades={result.total_trades}; "
        f"win_rate={result.win_rate:.1%}; avg_return={result.average_return_pct:.2%}"
    )
    typer.echo(
        pd.DataFrame(
            [
                {
                    "symbol": item.symbol,
                    "trades": item.total_trades,
                    "win_rate": round(item.win_rate, 4),
                    "average_return_pct": round(item.average_return_pct, 4),
                }
                for item in result.results
            ]
        ).to_string(index=False)
    )


@app.command()
def backtest_sweep(
    universe: str = typer.Option("sp100", help="Universe to backtest."),
    period: str = typer.Option("2y", help="History period passed to yfinance."),
    profile: str = typer.Option("Classic rectangle", help=f"Rule profile: {', '.join(PROFILE_OPTIONS)}."),
    lookback: int = typer.Option(40, min=30, max=60, help="Rectangle window in daily bars."),
    max_range_pct: float = typer.Option(0.25, help="Maximum rectangle height as support percent."),
    limit: int | None = typer.Option(25, help="Optional symbol limit for testing."),
) -> None:
    """Compare a small grid of setup score and breakout-window settings."""
    symbols = _warm_cache_symbols(universe)
    if limit is not None:
        symbols = symbols[:limit]
    rows = sweep_backtest_parameters(
        symbols,
        CachedMarketDataProvider(YFinanceMarketDataProvider()),
        period=period,
        scan_parameters=build_rectangle_parameters(
            profile,
            lookback=lookback,
            max_range_pct=max_range_pct,
        ),
    )
    typer.echo(pd.DataFrame(rows).to_string(index=False))


def _cached_provider(data_source: str, *, refresh: bool = False) -> CachedMarketDataProvider:
    return CachedMarketDataProvider(
        build_fallback_market_data_provider(data_source),
        refresh=refresh,
    )


def _bar_request(symbol: str, period: str) -> BarDataRequest:
    return BarDataRequest(symbol=symbol, period=period)


def _warm_cache_symbols(universe: str) -> list[str]:
    loader = UniverseLoader()
    if universe.strip().lower() == "all":
        symbols: list[str] = []
        for universe_id in UNIVERSE_OPTIONS.values():
            symbols.extend(loader.load(universe_id))
        return sorted(set(symbols))
    return loader.load(universe)


def _candidate_frame(result: object) -> pd.DataFrame:
    from qx.models.scan import ScanRunResult

    typed_result = result if isinstance(result, ScanRunResult) else ScanRunResult.model_validate(result)
    return pd.DataFrame(
        [
            {
                "symbol": candidate.symbol,
                "quality": candidate.quality_label,
                "setup_status": candidate.setup_status,
                "passed": candidate.passed,
                "setup_score": candidate.setup_score,
                "pattern_score": candidate.pattern_score,
                "readiness_score": candidate.readiness_score,
                "rule_score": candidate.score,
                "support": candidate.metrics.support,
                "resistance": candidate.metrics.resistance,
                "range_pct": candidate.metrics.range_pct,
                "position_in_range": candidate.metrics.position_in_range,
                "resistance_distance_pct": candidate.metrics.resistance_distance_pct,
                "support_touches": candidate.metrics.support_touches,
                "resistance_touches": candidate.metrics.resistance_touches,
                "pivot_support_touches": candidate.metrics.pivot_support_touches,
                "pivot_resistance_touches": candidate.metrics.pivot_resistance_touches,
                "support_slope_pct": candidate.metrics.support_slope_pct,
                "resistance_slope_pct": candidate.metrics.resistance_slope_pct,
                "close_range_ratio": candidate.metrics.close_range_ratio,
                "inside_close_pct": candidate.metrics.inside_close_pct,
                "breakout_level": candidate.metrics.breakout_level,
                "failure_level": candidate.metrics.failure_level,
                "relative_volume_20d": candidate.metrics.relative_volume_20d,
                "down_volume_ratio_10_to_20": candidate.metrics.down_volume_ratio_10_to_20,
            }
            for candidate in typed_result.candidates
        ]
    )


def _summary_rows(candidates: Sequence[object]) -> list[dict[str, object]]:
    from qx.models.scan import ScanCandidate

    rows: list[dict[str, object]] = []
    for raw_candidate in candidates:
        candidate = (
            raw_candidate
            if isinstance(raw_candidate, ScanCandidate)
            else ScanCandidate.model_validate(raw_candidate)
        )
        rows.append(
            {
                "symbol": candidate.symbol,
                "quality": candidate.quality_label,
                "setup_status": candidate.setup_status,
                "setup_score": round(candidate.setup_score, 3),
                "pattern_score": round(candidate.pattern_score, 3),
                "readiness_score": round(candidate.readiness_score, 3),
                "mtf_score": round(candidate.multi_timeframe_score, 3),
                "weekly_status": candidate.weekly_context.status if candidate.weekly_context else "Unknown",
                "rule_score": round(candidate.score, 3),
                "range_pct": round(candidate.metrics.range_pct, 4),
                "position": round(candidate.metrics.position_in_range, 4),
                "resistance_distance_pct": round(candidate.metrics.resistance_distance_pct, 4),
                "relative_volume_20d": round(candidate.metrics.relative_volume_20d, 3),
                "pivot_support_touches": candidate.metrics.pivot_support_touches,
                "pivot_resistance_touches": candidate.metrics.pivot_resistance_touches,
                "support_slope_pct": round(candidate.metrics.support_slope_pct, 4),
                "resistance_slope_pct": round(candidate.metrics.resistance_slope_pct, 4),
                "inside_close_pct": round(candidate.metrics.inside_close_pct, 4),
                "breakout_level": round(candidate.metrics.breakout_level, 2),
                "failure_level": round(candidate.metrics.failure_level, 2),
                "support": round(candidate.metrics.support, 2),
                "resistance": round(candidate.metrics.resistance, 2),
                "missing": ", ".join(candidate.failed_rule_names[:3]),
            }
        )
    return rows


def _write_outputs(payload: dict[str, object], output_json: Path | None) -> None:
    if not output_json:
        return
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    app()
