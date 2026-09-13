from pathlib import Path
from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo
import json

import pandas as pd

from qx.charts.rectangle import build_rectangle_chart, build_weekly_context_chart
from qx.core.engine import ScannerEngine
from qx.data.cache import CachedMarketDataProvider
from qx.data.cache_status import assess_cache_health
from qx.data.factory import build_fallback_market_data_provider, build_fundamental_provider
from qx.data.metadata import SymbolMetadata
from qx.data.universe import UNIVERSE_OPTIONS, UniverseLoader
from qx.exports.scanner_results import qx_results_frame
from qx.market.regime import MarketRegimeResult, analyze_market_regime, market_regime_frame
from qx.market.movers import MarketMoverResult, market_movers_frame, scan_market_movers
from qx.market.mover_briefing import mover_briefing
from qx.models.market import BarDataRequest
from qx.models.scan import ScanCandidate, ScanRunResult
from qx.patterns.profiles import PROFILE_OPTIONS, build_rectangle_parameters, default_max_range_pct
from qx.storage.sqlite import SQLiteScanRepository
from qx.storage.feature_cache import SQLiteFeatureCache
from qx.storage.watchlist import SQLiteWatchlistRepository, StoredWatchlistSymbol
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame
from qx.ui.status import friendly_iso_time
from qx.ui.workspace_context import read_context, render_context_links, sync_context, workspace_url
from qx.ui.tables import (
    candidate_metadata,
    candidate_table,
    rectangle_dashboard_columns,
    rectangle_detail_columns,
    rules_table,
)


SCAN_HISTORY_DB = Path("data/scanner_history.db")
MARKET_TIMEZONE = ZoneInfo("America/New_York")
SCAN_TYPE_OPTIONS = (
    "Rectangle",
    "Market Movers / Accumulation",
)
SCAN_TYPE_GUIDE = {
    "Rectangle": {
        "best_use": "Clean base / box breakout research",
        "prioritizes": "Box height, support/resistance touches, volume contraction, trend, breakout proximity",
        "avoid": "Daily movers or momentum-only names",
        "help": (
            "Pure rectangle setup qx: support/resistance box, repeated touches, controlled range, "
            "volume behavior, trend context, and breakout proximity."
        ),
    },
    "Market Movers / Accumulation": {
        "best_use": "Tape and money-flow lens",
        "prioritizes": (
            "Top daily movers, RVOL, dollar volume, candle close location, accumulation score, "
            "rectangle/options overlap"
        ),
        "avoid": "Replacing rectangle rules",
        "help": (
            "Separate tape lens: top movers by universe with relative volume, dollar volume, candle close location, "
            "accumulation/distribution read, rectangle overlap, and options-quality context."
        ),
    },
}


def render_scan_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)

    default_max_range = default_max_range_pct(PROFILE_OPTIONS[0])
    navigation_context = read_context(getattr(streamlit, "query_params", {}))
    universe_options = ["Custom", *UNIVERSE_OPTIONS.keys()]
    preferred_universe = next((name for name, code in UNIVERSE_OPTIONS.items() if code == navigation_context.get("universe")), "Custom")

    with streamlit.container(border=True):
        control_cols = streamlit.columns([1.15, 1.35, 1.35])
        universe_mode = control_cols[0].selectbox(
            "Universe",
            universe_options,
            index=universe_options.index(preferred_universe),
        )
        scan_type = control_cols[1].selectbox(
            "Scan Type",
            list(SCAN_TYPE_OPTIONS),
            index=0,
        )
        rule_profile = control_cols[2].selectbox(
            "Rule Profile",
            PROFILE_OPTIONS,
            index=0,
            disabled=scan_type != "Rectangle",
        )
        timeframe = "Daily"

        symbols_text = ""
        if universe_mode == "Custom":
            symbols_text = streamlit.text_area(
                "Symbols / Custom Watchlist", value=navigation_context.get("symbol", "AAPL\nMSFT\nNVDA"), height=82,
                key="scanner_custom_symbols",
            )
        with streamlit.expander("Advanced Settings", expanded=False):
            period_options = ["2y", "3y", "5y"]
            period = streamlit.selectbox("History", period_options, index=period_options.index(navigation_context["period"]) if navigation_context.get("period") in period_options else 0)
            advanced_cols = streamlit.columns([1.0, 1.0, 1.0, 1.0, 1.15])
            data_source = advanced_cols[0].selectbox(
                "Market Data",
                MARKET_DATA_PROVIDER_OPTIONS,
                index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
                key="scan_market_data_source",
            )
            lookback = advanced_cols[1].slider(
                "Pattern Bars",
                30,
                60,
                40,
                5,
                key="scan_pattern_bars",
                disabled=scan_type != "Rectangle",
            )
            max_range_pct = advanced_cols[2].slider(
                "Max Range",
                0.05,
                0.25,
                default_max_range,
                0.01,
                format="%.2f",
                key="scan_max_range_pct",
                disabled=scan_type != "Rectangle",
            )
            min_score = advanced_cols[3].slider(
                "Minimum Score",
                0.0,
                1.0,
                0.70,
                0.05,
                key="scan_min_score",
                disabled=scan_type != "Rectangle",
            )
            max_results = advanced_cols[4].slider(
                "Max Results",
                5,
                100,
                25,
                5,
                key="scan_max_results",
            )
            scan_mode = streamlit.selectbox(
                "Result Mode",
                ["Closest matches", "Strict pass only"],
                index=0,
                key="scan_result_mode",
                disabled=scan_type != "Rectangle",
            )
            refresh_live = streamlit.checkbox(
                "Refresh live bars",
                value=False,
                help="Refresh stale or cached bars from the selected provider before scanning."
                " Leave off for the fastest local-cache scan.",
                key="scan_refresh_live",
            )
            streamlit.caption("The scanner fetches enough history for 200-bar rules.")
        streamlit.caption("Completed NYSE sessions; daily bars become eligible 30 minutes after the scheduled close." if scan_type != "Rectangle" else "Daily bars")
        run_scan = streamlit.button("Run Scan", type="primary", width="stretch", disabled=bool(navigation_context.get("as_of")))

    sync_context(streamlit, universe="custom" if universe_mode == "Custom" else UNIVERSE_OPTIONS[str(universe_mode)], period=str(period))
    if navigation_context.get("as_of"):
        streamlit.warning(f"Historical navigation date: {navigation_context['as_of']}. A new scan uses current completed sessions, not historical replay.")
        streamlit.link_button("Use current sessions", workspace_url("scan", navigation_context, as_of="", snapshot=""))

    cache_label = "Not checked"
    current_scan_label = f"{scan_type} / {timeframe}"
    request_context = (str(universe_mode), symbols_text, str(scan_type), str(rule_profile),
                       str(period), str(data_source), lookback, max_range_pct, min_score,
                       max_results, scan_mode, refresh_live)

    if not run_scan:
        saved = streamlit.session_state.get("scanner_display_result")
        if saved is not None and saved[0] == request_context:
            _render_scan_result(streamlit, **saved[1])
            return
        movers = streamlit.session_state.get("scanner_mover_display")
        if movers is not None and movers[0] == request_context:
            _render_market_movers_results(streamlit, **movers[1])
            return
        with streamlit.expander("Data readiness"):
            if streamlit.button("Check selected data", key="scan_check_data"):
                _render_cache_warning(streamlit, str(universe_mode), symbols_text, str(period), str(data_source))
        _render_status_bar(
            streamlit,
            last_scan_at=streamlit.session_state.get("last_scan_at"),
            data_source=str(data_source),
            regime_label=streamlit.session_state.get("last_regime_label", "Not scanned"),
            universe=str(universe_mode),
            cache_label=cache_label,
            scan_type=current_scan_label,
        )
        streamlit.info("No compatible result is loaded for these settings. No scan or market-data request has started.")
        streamlit.link_button("Saved scan history", workspace_url("run_history", navigation_context, history_view="Scans"))
        return

    symbols = _selected_symbols(universe_mode, symbols_text)
    if not symbols:
        streamlit.warning("Enter at least one symbol before scanning.")
        return
    parameters = build_rectangle_parameters(
        rule_profile,
        lookback=lookback,
        max_range_pct=max_range_pct,
    )
    provider = CachedMarketDataProvider(
        build_fallback_market_data_provider(str(data_source)),
        refresh=bool(refresh_live),
    )
    regime: MarketRegimeResult | None = None

    if scan_type == "Market Movers / Accumulation":
        with streamlit.spinner(f"Scanning movers across {len(symbols)} symbols..."):
            try:
                regime = analyze_market_regime(provider, period=period)
                mover_result = scan_market_movers(
                    symbols,
                    provider,
                    period=period,
                    limit=max_results,
                    rectangle_candidates=SQLiteScanRepository(SCAN_HISTORY_DB).latest_candidates(),
                    fundamental_provider=build_fundamental_provider(str(data_source)),
                    as_of=datetime.now(MARKET_TIMEZONE),
                )
            except Exception as exc:
                streamlit.error(f"Market movers scan failed: {exc}")
                streamlit.stop()

        scan_time = datetime.now(MARKET_TIMEZONE)
        streamlit.session_state["last_scan_at"] = scan_time.isoformat()
        streamlit.session_state["last_regime_label"] = regime.label if regime else "Unavailable"
        mover_args: dict[str, Any] = dict(
            result=mover_result,
            scan_time=scan_time,
            data_source=str(data_source),
            regime=regime,
            universe=str(universe_mode),
            cache_label=cache_label,
            scan_type=current_scan_label,
        )
        streamlit.session_state["scanner_mover_display"] = (request_context, mover_args)
        _render_market_movers_results(streamlit, **mover_args)
        return

    engine = ScannerEngine(provider, parameters, feature_cache=SQLiteFeatureCache(),
                           as_of=datetime.now(MARKET_TIMEZONE),
                           failure_cache_scope=f"qx-page:{data_source}:fallback-v1")

    with streamlit.spinner(f"Scanning {len(symbols)} symbols..."):
        try:
            regime = analyze_market_regime(provider, period=period)
            result = engine.scan_symbols(symbols, period=period, retry_failed=refresh_live)
        except Exception as exc:
            streamlit.error(f"Scan failed: {exc}")
            streamlit.stop()

    run_id = SQLiteScanRepository(SCAN_HISTORY_DB).save_scan_run(result)
    scan_time = datetime.now(MARKET_TIMEZONE)
    streamlit.session_state["last_scan_at"] = scan_time.isoformat()
    streamlit.session_state["last_regime_label"] = regime.label if regime else "Unavailable"
    filtered_candidates = filter_candidates(
        result.candidates,
        min_score=min_score,
        strict_only=scan_mode == "Strict pass only",
        max_results=max_results,
    )

    render_args: dict[str, Any] = dict(engine=engine, result=result, filtered_candidates=filtered_candidates,
                       run_id=run_id, scan_time=scan_time, data_source=str(data_source), regime=regime,
                       universe=str(universe_mode), cache_label=cache_label,
                       current_scan_label=current_scan_label, period=str(period))
    streamlit.session_state["scanner_display_result"] = (request_context, render_args)
    _render_scan_result(streamlit, **render_args)


def _render_scan_result(
    streamlit: Any, *, engine: ScannerEngine, result: ScanRunResult,
    filtered_candidates: list[ScanCandidate], run_id: int, scan_time: datetime,
    data_source: str, regime: MarketRegimeResult | None, universe: str,
    cache_label: str, current_scan_label: str, period: str,
) -> None:

    _render_status_bar(
        streamlit,
        last_scan_at=scan_time.isoformat(),
        data_source=str(data_source),
        regime_label=regime.label if regime else "Unavailable",
        universe=universe,
        cache_label=cache_label,
        scan_type=current_scan_label,
    )
    streamlit.subheader("QX Scanner Results")
    streamlit.caption(_scan_summary_text(result, filtered_candidates, run_id))
    _render_data_quality_notice(streamlit, result)
    _render_kpis(streamlit, result, filtered_candidates)

    if filtered_candidates:
        metadata_by_symbol = candidate_metadata(filtered_candidates)
        table = candidate_table(filtered_candidates, metadata_by_symbol=metadata_by_symbol)
        scanner_results = scanner_results_frame(filtered_candidates)
        _render_result_tabs(
            streamlit,
            engine=engine,
            candidates=filtered_candidates,
            table=table,
            scanner_results=scanner_results,
            result=result,
            regime=regime,
            period=period,
            metadata_by_symbol=metadata_by_symbol,
        )
    else:
        streamlit.info("No candidates met the current minimum score. Lower Min score or scan 2y/3y.")


def _scan_summary_text(result: ScanRunResult, candidates: list[ScanCandidate], run_id: int) -> str:
    return (
        f"Scanned {result.total_symbols} symbols. "
        f"Showing {len(candidates)} candidates. "
        f"Saved run: {run_id}."
    )


def _render_data_quality_notice(streamlit: Any, result: ScanRunResult) -> None:
    if result.total_symbols <= 0 or result.failed_symbols <= 0:
        return
    failure_rate = result.failed_symbols / result.total_symbols
    message = (
        f"Data quality: {result.failed_symbols} of {result.total_symbols} symbols failed "
        f"({failure_rate:.1%}). Results may be incomplete."
    )
    if failure_rate >= 0.10:
        streamlit.warning(message)
    else:
        streamlit.caption(message)


def filter_candidates(
    candidates: list[ScanCandidate],
    min_score: float,
    strict_only: bool,
    max_results: int,
) -> list[ScanCandidate]:
    filtered = [
        candidate
        for candidate in candidates
        if candidate.setup_score >= min_score and (candidate.passed or not strict_only)
    ]
    return filtered[:max_results]


def _render_market_movers_results(
    streamlit: Any,
    *,
    result: MarketMoverResult,
    scan_time: datetime,
    data_source: str,
    regime: MarketRegimeResult | None,
    universe: str,
    cache_label: str,
    scan_type: str,
) -> None:
    streamlit.subheader("Market Movers / Accumulation")
    streamlit.caption(
        "Separate tape lens: daily movers ranked by strength, relative volume, dollar liquidity, "
        "candle close quality, and up-volume accumulation. Rectangle rules are not modified."
    )
    _render_status_bar(
        streamlit,
        last_scan_at=scan_time.isoformat(),
        data_source=data_source,
        regime_label=regime.label if regime else "Unavailable",
        universe=universe,
        cache_label=cache_label,
        scan_type=scan_type,
    )
    _render_market_mover_kpis(streamlit, result)
    if not result.candidates:
        streamlit.info("No market movers were available for this universe. Check data failures or cache health.")
        if result.failures:
            streamlit.dataframe(pd.DataFrame([{"symbol": symbol, "error": error}
                                              for symbol, error in sorted(result.failures.items())]), hide_index=True)
        return
    _render_market_mover_tabs(streamlit, result)


def _render_market_mover_kpis(streamlit: Any, result: MarketMoverResult) -> None:
    frame = market_movers_frame(result.candidates)
    accumulation_count = int(frame["tape_status"].isin(["Accumulation Surge", "Constructive Accumulation"]).sum())
    options_count = int(frame["options_quality"].isin(["Underlying Liquid", "Underlying Review"]).sum())
    rectangle_count = int((frame["rectangle_score"] > 0).sum())
    review_count = int(frame["mover_action"].isin(["Review Now", "Rectangle Overlap"]).sum())
    avg_rvol = float(frame["relative_volume_20d"].mean()) if not frame.empty else 0.0
    cols = streamlit.columns(7)
    cols[0].metric("Valid / Requested", f"{result.total_symbols - result.failed_symbols} / {result.total_symbols}")
    cols[1].metric("Displayed", len(result.candidates))
    cols[2].metric("Review Now (overlap)", review_count)
    cols[3].metric("Accumulation (overlap)", accumulation_count)
    cols[4].metric("Underlying Liquidity", options_count)
    cols[5].metric("Saved Rectangle Context", rectangle_count)
    cols[6].metric("Avg RVOL", f"{avg_rvol:.2f}x")
    streamlit.caption("Counts apply to displayed movers and may overlap. Saved rectangle context is historical, not confirmation. Accumulation scores are heuristic, not probabilities.")
    if result.failed_symbols:
        streamlit.warning(f"{result.failed_symbols} symbols excluded due to data failures. See Data Issues.")


def _render_market_mover_tabs(streamlit: Any, result: MarketMoverResult) -> None:
    frame = market_movers_frame(result.candidates)
    tabs = streamlit.tabs(
        [
            "Mover Board",
            "Accumulation",
            "Underlying Liquidity",
            "Rectangle Crosscheck",
            "Sector Summary",
            "Data Issues",
        ]
    )
    tabs[0].dataframe(
        market_mover_display_frame(frame),
        width="stretch",
        hide_index=True,
    )
    tabs[0].download_button(
        "Export Market Movers CSV",
        frame.to_csv(index=False),
        file_name="market_movers_accumulation.csv",
        mime="text/csv",
    )

    accumulation = frame[frame["tape_status"].isin(["Accumulation Surge", "Constructive Accumulation"])]
    if accumulation.empty:
        tabs[1].info("No constructive accumulation names in the displayed movers.")
    else:
        tabs[1].dataframe(
            display_frame(
                accumulation,
                columns=[
                    "symbol",
                    "price",
                    "sector",
                    "mover_action",
                    "return_1d",
                    "relative_volume_20d",
                    "dollar_volume",
                    "close_location",
                    "accumulation_ratio",
                    "accumulation_score",
                    "tape_status",
                    "notes",
                ],
            ),
            width="stretch",
            hide_index=True,
        )

    options = frame[frame["options_quality"].isin(["Underlying Liquid", "Underlying Review"])]
    tabs[2].caption(
        "Underlying liquidity context only. Validate contract spread, IV, delta, open interest, expiry, and event risk."
    )
    if options.empty:
        tabs[2].info("No displayed movers met the options liquidity filter.")
    else:
        tabs[2].dataframe(
            display_frame(
                options,
                columns=[
                    "symbol",
                    "price",
                    "name",
                    "sector",
                    "market_cap",
                    "dollar_volume",
                    "relative_volume_20d",
                    "mover_action",
                    "options_quality",
                    "tape_status",
                ],
            ),
            width="stretch",
            hide_index=True,
        )

    rectangle_overlap = frame[frame["rectangle_score"] > 0]
    if rectangle_overlap.empty:
        tabs[3].info("No saved rectangle context for the displayed movers.")
    else:
        tabs[3].dataframe(
            display_frame(
                rectangle_overlap,
                columns=[
                    "symbol",
                    "price",
                    "sector",
                    "return_1d",
                    "relative_volume_20d",
                    "mover_action",
                    "rectangle_signal",
                    "rectangle_score",
                    "options_quality",
                    "notes",
                ],
            ),
            width="stretch",
            hide_index=True,
        )
    tabs[3].caption("Historical annotations only. Scan date, rule-profile compatibility, and current validity are not verified; these do not promote mover actions.")

    sector = market_mover_sector_frame(frame)
    if sector.empty:
        tabs[4].info("No sector data available for displayed movers.")
    else:
        tabs[4].dataframe(sector, width="stretch", hide_index=True)

    if result.failures:
        failures = pd.DataFrame(
            [{"symbol": symbol, "error": error} for symbol, error in sorted(result.failures.items())]
        )
        tabs[5].dataframe(display_frame(failures), width="stretch", hide_index=True)
    else:
        tabs[5].success("No data failures in this market movers scan.")

    _render_market_mover_detail(streamlit, result)


def _render_market_mover_detail(streamlit: Any, result: MarketMoverResult) -> None:
    symbols = [candidate.symbol for candidate in result.candidates]
    selected_symbol = streamlit.selectbox("Review Mover", symbols)
    selected = next(candidate for candidate in result.candidates if candidate.symbol == selected_symbol)
    with streamlit.container(border=True):
        cols = streamlit.columns(6)
        cols[0].metric("1D Move", f"{selected.return_1d:.1%}")
        cols[1].metric("RVOL", f"{selected.relative_volume_20d:.2f}x")
        cols[2].metric("Prior 20D Avg $ Vol", display_frame(pd.DataFrame([{"dollar_volume": selected.dollar_volume}])).iloc[0, 0])
        cols[3].metric("Close Location", f"{selected.close_location:.1%}")
        cols[4].metric("Tape", selected.tape_status)
        cols[5].metric("Action", selected.mover_action)
        streamlit.caption(
            f"{selected.name} | {selected.sector} | rectangle: {selected.rectangle_signal} "
            f"({selected.rectangle_score:.2f}) | options: {selected.options_quality} | notes: {selected.notes}"
        )
        streamlit.caption(f"Bar date: {selected.bar_date} | Actual source: {selected.actual_source} | Calendar check: {selected.freshness}")
        with streamlit.expander("Interpretation evidence"):
            briefing = mover_briefing(selected)
            for warning in briefing["warnings"]:
                streamlit.write(warning)
            streamlit.download_button("Export AI evidence snapshot", json.dumps(briefing, indent=2),
                                      file_name=f"{selected.symbol}_evidence.json", mime="application/json")
        streamlit.caption("Review Now requires a positive day, accumulation score >= 0.78, RVOL >= 1.5, close location >= 65%, and prior 20-session averages of >= 500,000 shares and >= $10M traded value. Ranking score is not a probability.")


def market_mover_display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "symbol",
        "mover_score",
        "bar_date",
        "actual_source",
        "price",
        "sector",
        "market_cap",
        "return_1d",
        "relative_volume_20d",
        "dollar_volume",
        "close_location",
        "accumulation_score",
        "tape_status",
        "mover_action",
        "rectangle_signal",
        "options_quality",
        "notes",
    ]
    return display_frame(frame, columns=[column for column in columns if column in frame.columns]).rename(
        columns={"Dollar Vol": "Prior 20D Avg $ Vol", "Options Quality": "Underlying Liquidity"}
    )


def market_mover_sector_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "sector" not in frame:
        return pd.DataFrame()
    grouped = (
        frame.groupby("sector", dropna=False)
        .agg(
            movers=("symbol", "count"),
            avg_move=("return_1d", "mean"),
            avg_rvol=("relative_volume_20d", "mean"),
            dollar_volume=("dollar_volume", "sum"),
            accumulation=("accumulation_score", "mean"),
            review_now=("mover_action", lambda values: int(pd.Series(values).isin(["Review Now", "Rectangle Overlap"]).sum())),
            options_fit=("options_quality", lambda values: int(pd.Series(values).isin(["Underlying Liquid", "Underlying Review"]).sum())),
        )
        .reset_index()
        .sort_values(["review_now", "accumulation", "avg_rvol"], ascending=False)
    )
    return display_frame(grouped)


def scanner_kpis(result: ScanRunResult, candidates: list[ScanCandidate]) -> dict[str, float | int]:
    table = candidate_table(candidates) if candidates else pd.DataFrame()
    ready_now = _count_actions(table, {"A+ Ready", "Ready", "Breakout"})
    ready_watch = _count_actions(table, {"Watch", "Retest"})
    base_building = _count_actions(table, {"Early Base"})
    broad_breakouts = _count_broad_breakout_lens(table)
    failed_breakouts = _count_status(table, "breakout_status", {"Below Support"}) + _count_actions(
        table,
        {"Reject"},
    )
    distribution_risk = _count_status(table, "vol_status", {"Distribution Risk"})
    avg_score = float(table["qx_rect_score"].mean()) if "qx_rect_score" in table and not table.empty else 0.0
    return {
        "total_scanned": result.total_symbols,
        "ready_now": ready_now,
        "ready_watch": ready_watch,
        "base_building": base_building,
        "rectangle_setups": len(candidates),
        "broad_breakouts": broad_breakouts,
        "failed_breakouts": failed_breakouts,
        "distribution_risk": distribution_risk,
        "average_qx_score": round(avg_score, 3),
    }


def ready_list_frame(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    table = table[_ready_candidate_mask(table)]
    if table.empty:
        return pd.DataFrame(columns=ready_list_columns())
    frame = pd.DataFrame(
        {
            "ticker": table["ticker"],
            "price": table["price"],
            "sector": table["sector"],
            "setup_type": table["breakout_status"].map(_setup_type_from_breakout),
            "pattern_type": table["pattern_type"],
            "directional_bias": table["directional_bias"],
            "bias_ready_pct": table["bias_ready_pct"],
            "breakout_quality_label": table["breakout_quality_label"],
            "breakout_quality_pct": table["breakout_quality_pct"],
            "qx_action": table["qx_action"],
            "trade_posture": table["trade_posture"],
            "qx_ready_score": table["qx_rect_score"],
            "trend_label": table["trend_status"],
            "rs_label": table["rs_status"],
            "volume_label": table["vol_status"],
            "timing_read": table["timing_read"],
            "trigger_status": table["breakout_status"],
            "distance_to_trigger_pct": table["resistance_distance_pct"],
            "target_label": table["target_label"],
            "target_upside_pct": table["target_upside_pct"],
            "breakout_level": table["breakout_level"],
            "entry_zone": table["box_high"],
            "stop_level": table["stop_level"],
            "target_1": table["target_1"],
            "risk_reward": table["risk_reward"],
            "options_action": table["qx_action"].map(_options_action_from_qx),
            "notes": table.apply(_ready_note, axis=1),
        }
    )
    return frame


def _ready_candidate_mask(table: pd.DataFrame) -> pd.Series:
    qx_action = table["qx_action"].astype(str) if "qx_action" in table else pd.Series("", index=table.index)
    trade_posture = (
        table["trade_posture"].astype(str) if "trade_posture" in table else pd.Series("", index=table.index)
    )
    return ~qx_action.isin({"Reject", "Avoid"}) & ~trade_posture.isin({"Avoid"})


def ready_list_columns() -> list[str]:
    return [
        "ticker",
        "price",
        "sector",
        "setup_type",
        "pattern_type",
        "directional_bias",
        "bias_ready_pct",
        "breakout_quality_label",
        "breakout_quality_pct",
        "qx_action",
        "trade_posture",
        "qx_ready_score",
        "trend_label",
        "rs_label",
        "volume_label",
        "timing_read",
        "trigger_status",
        "distance_to_trigger_pct",
        "target_label",
        "target_upside_pct",
        "breakout_level",
        "entry_zone",
        "stop_level",
        "target_1",
        "risk_reward",
        "options_action",
        "notes",
    ]


def selected_symbols(universe_mode: str, symbols_text: str) -> list[str]:
    return _selected_symbols(universe_mode, symbols_text)


def scan_type_help(scan_type: str) -> str:
    guide = SCAN_TYPE_GUIDE.get(scan_type)
    return guide["help"] if guide else "Select a scan lens to see the rules and decision focus."


def scan_type_guide_markdown() -> str:
    rows = "\n".join(
        f"| {scan_type} | {guide['best_use']} | {guide['prioritizes']} | {guide['avoid']} |"
        for scan_type, guide in SCAN_TYPE_GUIDE.items()
    )
    return f"""
| Scan Type | Best Use | What It Prioritizes | Avoid Using It For |
| --- | --- | --- | --- |
| Ready / Actionable | Daily operating view after a scan | Actionable candidates only; rejects stay in Failed / Rejects and Diagnostics | Pure pattern research |
{rows}
"""


def _selected_symbols(universe_mode: str, symbols_text: str) -> list[str]:
    if universe_mode in UNIVERSE_OPTIONS:
        return UniverseLoader().load(UNIVERSE_OPTIONS[universe_mode])
    return [symbol.strip().upper() for symbol in symbols_text.splitlines() if symbol.strip()]


def _render_status_bar(
    streamlit: Any,
    *,
    last_scan_at: object,
    data_source: str,
    regime_label: str,
    universe: str,
    cache_label: str,
    scan_type: str,
) -> None:
    with streamlit.container(border=True):
        cols = streamlit.columns([1.4, 1.0, 1.1, 1.0, 1.0, 1.2])
        cols[0].metric("Last Scan", _format_scan_time(last_scan_at))
        cols[1].metric("Data Source", data_source)
        cols[2].metric("Regime", regime_label)
        cols[3].metric("Universe", universe)
        cols[4].metric("Cache", cache_label)
        cols[5].metric("Scan", scan_type)


def _render_kpis(streamlit: Any, result: ScanRunResult, candidates: list[ScanCandidate]) -> None:
    kpis = scanner_kpis(result, candidates)
    cols = streamlit.columns(8)
    cols[0].metric("Total Scanned", kpis["total_scanned"])
    cols[1].metric("Ready Now", kpis["ready_now"])
    cols[2].metric("Ready Watch", kpis["ready_watch"])
    cols[3].metric("Base Building", kpis["base_building"])
    cols[4].metric("Rectangles", kpis["rectangle_setups"])
    cols[5].metric("Broad BO", kpis["broad_breakouts"])
    cols[6].metric("Failed", kpis["failed_breakouts"])
    cols[7].metric("Avg QX", f"{kpis['average_qx_score']:.2f}")


def _render_result_tabs(
    streamlit: Any,
    *,
    engine: ScannerEngine,
    candidates: list[ScanCandidate],
    table: pd.DataFrame,
    scanner_results: pd.DataFrame,
    result: ScanRunResult,
    regime: MarketRegimeResult | None,
    period: str,
    metadata_by_symbol: dict[str, SymbolMetadata] | None = None,
) -> None:
    tabs = streamlit.tabs(
        [
            "Ready / Actionable",
            "Rectangle",
            "Broad Breakout",
            "Sector / Regime",
            "Options Fit",
            "Failed / Rejects",
            "Diagnostics",
        ],
    )
    ready_frame = ready_list_frame(table)
    selected_symbol = _render_selectable_ready_list(tabs[0], ready_frame)
    _render_exports(tabs[0], table, scanner_results)
    ready_symbols = set(ready_frame["ticker"].astype(str)) if not ready_frame.empty else set()
    ready_candidates = [candidate for candidate in candidates if candidate.symbol in ready_symbols]
    if ready_candidates:
        _render_selected_candidate_detail(
            tabs[0],
            engine,
            ready_candidates,
            period,
            selected_symbol=selected_symbol,
            metadata_by_symbol=metadata_by_symbol,
        )
    else:
        tabs[0].info("No actionable candidates. Review Failed / Rejects and Diagnostics for high-scoring names that failed decision gates.")

    rectangle_frame = table.loc[
        :,
        [column for column in rectangle_dashboard_columns() if column in table.columns],
    ]
    tabs[1].dataframe(display_frame(rectangle_frame), width="stretch", hide_index=True)

    broad_frame = broad_breakout_lens_frame(table)
    tabs[2].dataframe(display_frame(broad_frame), width="stretch", hide_index=True)
    tabs[2].caption("Broad breakout lens uses the current scan's trend, RS, RVOL, and trigger fields. The broader watchlist engine remains separate.")

    if regime:
        tabs[3].dataframe(display_frame(market_regime_frame(regime)), width="stretch", hide_index=True)
        for note in regime.notes:
            tabs[3].caption(note)
    else:
        tabs[3].info("Market regime was unavailable for this scan.")

    options_frame = ready_frame.loc[
        :,
        [
            "ticker",
            "directional_bias",
            "breakout_quality_label",
            "target_label",
            "target_upside_pct",
            "timing_read",
            "trade_posture",
            "qx_action",
            "qx_ready_score",
            "volume_label",
            "trigger_status",
            "options_action",
            "notes",
        ],
    ]
    tabs[4].dataframe(display_frame(options_frame), width="stretch", hide_index=True)

    reject_frame = table[
        table["qx_action"].isin(["Reject"])
        | table["breakout_status"].isin(["Below Support"])
        | table["vol_status"].isin(["Distribution Risk"])
    ]
    if reject_frame.empty:
        tabs[5].success("No filtered candidates are currently in Failed / Rejects.")
    else:
        tabs[5].dataframe(
            display_frame(reject_frame, columns=rectangle_dashboard_columns() + ["missing"]),
            width="stretch",
            hide_index=True,
        )

    if result.errors:
        tabs[6].subheader("Data Failures")
        tabs[6].dataframe(
            display_frame(pd.DataFrame([error.model_dump() for error in result.errors])),
            width="stretch",
            hide_index=True,
        )
    tabs[6].subheader("Rule Diagnostics")
    for candidate in candidates:
        with tabs[6].expander(f"{candidate.symbol} Rules"):
            tabs[6].dataframe(display_frame(rules_table(candidate)), width="stretch", hide_index=True)


def _render_exports(streamlit: Any, table: pd.DataFrame, scanner_results: pd.DataFrame) -> None:
    cols = streamlit.columns(2)
    cols[0].download_button(
        "Export CSV",
        table.to_csv(index=False),
        file_name="scanner_detailed_results.csv",
        mime="text/csv",
    )
    cols[1].download_button(
        "Export QuantX CSV",
        scanner_results.to_csv(index=False),
        file_name="scanner_results.csv",
        mime="text/csv",
    )


def _render_selectable_ready_list(streamlit: Any, ready_frame: pd.DataFrame) -> str | None:
    display = display_frame(ready_frame, columns=ready_list_columns())
    try:
        event = streamlit.dataframe(
            display,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
    except TypeError:
        streamlit.dataframe(display, width="stretch", hide_index=True)
        streamlit.caption("Row selection is unavailable in this Streamlit runtime; use Review Ticker below.")
        return None
    selected_symbol = _selected_symbol_from_table_event(event, ready_frame)
    if selected_symbol:
        streamlit.caption(f"Selected row: {selected_symbol}")
    else:
        streamlit.caption("Select a row to drive the ticker detail panel.")
    return selected_symbol


def _selected_symbol_from_table_event(event: object, ready_frame: pd.DataFrame) -> str | None:
    if ready_frame.empty:
        return None
    rows = _event_selected_rows(event)
    if not rows:
        return None
    selected_index = rows[0]
    if selected_index < 0 or selected_index >= len(ready_frame):
        return None
    return str(ready_frame.iloc[selected_index]["ticker"])


def _event_selected_rows(event: object) -> list[int]:
    if event is None:
        return []
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return []
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows")
    if not isinstance(rows, list):
        return []
    return [int(row) for row in rows if isinstance(row, int)]


def broad_breakout_lens_frame(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    frame = pd.DataFrame(
        {
            "ticker": table["ticker"],
            "price": table["price"],
            "sector": table["sector"],
            "pattern_type": table["pattern_type"],
            "directional_bias": table["directional_bias"],
            "bias_ready_pct": table["bias_ready_pct"],
            "breakout_quality_label": table["breakout_quality_label"],
            "breakout_quality_pct": table["breakout_quality_pct"],
            "trend_status": table["trend_status"],
            "rs_status": table["rs_status"],
            "vol_status": table["vol_status"],
            "rvol": table["rvol"],
            "breakout_status": table["breakout_status"],
            "timing_read": table["timing_read"],
            "breakout_level": table["breakout_level"],
            "distance_to_trigger_pct": table["resistance_distance_pct"],
            "target_label": table["target_label"],
            "target_upside_pct": table["target_upside_pct"],
            "risk_reward": table["risk_reward"],
            "qx_action": table["qx_action"],
            "trade_posture": table["trade_posture"],
            "notes": table.apply(_broad_breakout_note, axis=1),
        }
    )
    return frame


def _broad_breakout_note(row: pd.Series) -> str:
    signals = []
    if str(row.get("trend_status", "")).lower().startswith("up"):
        signals.append("trend aligned")
    if str(row.get("rs_status", "")).lower() not in {"weak", "lagging"}:
        signals.append("RS acceptable")
    if float(row.get("rvol", 0.0) or 0.0) >= 1.2:
        signals.append("volume active")
    if str(row.get("breakout_status", "")) in {"Breakout", "Ready", "Near Breakout"}:
        signals.append("near trigger")
    return ", ".join(signals) if signals else "needs confirmation"


def _render_selected_candidate_detail(
    streamlit: Any,
    engine: ScannerEngine,
    candidates: list[ScanCandidate],
    period: str,
    *,
    selected_symbol: str | None = None,
    metadata_by_symbol: dict[str, SymbolMetadata] | None = None,
) -> None:
    symbols = [candidate.symbol for candidate in candidates]
    default_index = symbols.index(selected_symbol) if selected_symbol in symbols else 0
    selected_symbol = streamlit.selectbox(
        "Review Ticker",
        symbols,
        index=default_index,
    )
    selected = next(candidate for candidate in candidates if candidate.symbol == selected_symbol)
    selected_table = candidate_table(
        [selected],
        metadata_by_symbol=metadata_by_symbol,
    )
    with streamlit.container(border=True):
        metric_cols = streamlit.columns(6)
        metric_cols[0].metric("Action", selected_table.loc[0, "qx_action"])
        metric_cols[1].metric("Bias", selected_table.loc[0, "directional_bias"])
        metric_cols[2].metric("BO Grade", selected_table.loc[0, "breakout_quality_label"])
        metric_cols[3].metric("Timing", selected_table.loc[0, "timing_read"])
        metric_cols[4].metric("Target Upside", f"{selected_table.loc[0, 'target_upside_pct']:.1%}")
        metric_cols[5].metric("R/R", f"{selected.metrics.risk_reward:.2f}")
        streamlit.caption(_candidate_summary(selected))
        sync_context(streamlit, symbol=selected.symbol)
        render_context_links(streamlit, selected.symbol)
        detail_tabs = streamlit.tabs(["Chart", "Plan", "Rectangle Details"])
        bars = engine.provider.get_daily_bars(BarDataRequest(symbol=selected.symbol, period=period))
        detail_tabs[0].plotly_chart(build_rectangle_chart(bars, selected), width="stretch")
        detail_tabs[1].markdown(_trade_plan_markdown(selected))
        save_cols = detail_tabs[1].columns([1.0, 3.0])
        if save_cols[0].button("Add to Watchlist", key=f"save-watchlist-{selected.symbol}"):
            selected_row = selected_table.iloc[0]
            SQLiteWatchlistRepository(SCAN_HISTORY_DB).add_symbol(
                selected.symbol,
                source="rectangle_scanner",
                status=str(selected_row["qx_action"]),
                notes=_candidate_summary(selected),
                context=_watchlist_context(selected, selected_row),
            )
            save_cols[1].success(f"Saved {selected.symbol} to scanner_review watchlist.")
        detail_tabs[1].dataframe(display_frame(pd.DataFrame(_detail_reason_rows(selected))), width="stretch", hide_index=True)
        saved_entries = SQLiteWatchlistRepository(SCAN_HISTORY_DB).list_entries(limit=25)
        if saved_entries:
            with detail_tabs[1].expander("Saved Scanner Review Watchlist"):
                detail_tabs[1].dataframe(
                    display_frame(_saved_watchlist_frame(saved_entries)),
                    width="stretch",
                    hide_index=True,
                )
        detail_tabs[2].dataframe(
            display_frame(selected_table, columns=rectangle_detail_columns()),
            width="stretch",
            hide_index=True,
        )
        if selected.weekly_context:
            detail_tabs[2].plotly_chart(build_weekly_context_chart(bars, selected), width="stretch")


def _count_actions(table: pd.DataFrame, actions: set[str]) -> int:
    if table.empty or "qx_action" not in table:
        return 0
    return int(table["qx_action"].isin(actions).sum())


def _count_status(table: pd.DataFrame, column: str, values: set[str]) -> int:
    if table.empty or column not in table:
        return 0
    return int(table[column].isin(values).sum())


def _count_broad_breakout_lens(table: pd.DataFrame) -> int:
    required = {"trend_status", "rs_status", "rvol", "breakout_status", "qx_action"}
    if table.empty or not required.issubset(table.columns):
        return 0
    count = 0
    for _, row in table.iterrows():
        trend_aligned = str(row.get("trend_status", "")).lower().startswith("up")
        rs_ok = str(row.get("rs_status", "")).lower() not in {"weak", "lagging"}
        volume_active = float(row.get("rvol", 0.0) or 0.0) >= 1.0
        near_trigger = str(row.get("breakout_status", "")) in {"Breakout", "Ready", "Near Breakout"}
        actionable = str(row.get("qx_action", "")) not in {"Reject", "Avoid"}
        if trend_aligned and rs_ok and volume_active and near_trigger and actionable:
            count += 1
    return count


def _setup_type_from_breakout(status: str) -> str:
    if status in {"Breakout", "Ready", "Near Breakout"}:
        return "RectangleBreakout"
    if status == "Inside Box":
        return "NoCleanSetup"
    if status == "Below Support":
        return "FailedBreakout"
    return "RectangleBreakout"


def _options_action_from_qx(action: str) -> str:
    if action in {"A+ Ready", "Ready", "Breakout", "Retest"}:
        return "Review Contracts"
    if action == "Watch":
        return "Watch Options"
    if action == "Reject":
        return "Avoid"
    return "Wait"


def _ready_note(row: pd.Series) -> str:
    parts = [
        str(row.get("box_status", "")),
        str(row.get("vol_status", "")),
        str(row.get("trend_status", "")),
        str(row.get("breakout_status", "")),
    ]
    return " | ".join(part for part in parts if part and part != "nan")


def _candidate_summary(candidate: ScanCandidate) -> str:
    failed = ", ".join(candidate.failed_rule_names[:4]) or "none"
    return (
        f"{candidate.symbol}: {candidate.setup_status}; "
        f"box {candidate.metrics.box_status}; volume {candidate.metrics.volume_status}; "
        f"trend {candidate.metrics.trend_status}; failed gates: {failed}."
    )


def _trade_plan_markdown(candidate: ScanCandidate) -> str:
    table = candidate_table([candidate])
    return f"""
**Setup Summary**

- Setup type: `{candidate.metrics.breakout_status}`
- Pattern type: `{table.loc[0, "pattern_type"]}`
- Directional bias: `{table.loc[0, "directional_bias"]}`
- Breakout quality: `{table.loc[0, "breakout_quality_label"]}` ({table.loc[0, "breakout_quality_pct"]:.0%})
- Timing read: `{table.loc[0, "timing_read"]}`
- Trade posture: `{table.loc[0, "trade_posture"]}`
- Target read: `{table.loc[0, "target_label"]}` ({table.loc[0, "target_upside_pct"]:.1%})
- Action: `{table.loc[0, "qx_action"]}`
- Why it passed: {_passed_reason_text(candidate)}
- Failed gates: {", ".join(candidate.failed_rule_names[:5]) or "None"}
- Options fit: {_options_fit_text(candidate)}

**Trade Plan**

- Entry zone: `{candidate.metrics.resistance:.2f}` to `{candidate.metrics.breakout_level:.2f}`
- Stop level: `{candidate.metrics.stop_level:.2f}`
- Target 1: `{candidate.metrics.target_1:.2f}`
- Risk/reward: `{candidate.metrics.risk_reward:.2f}`
"""


def _detail_reason_rows(candidate: ScanCandidate) -> list[dict[str, str]]:
    passed = [rule for rule in candidate.rules if rule.passed]
    failed = [rule for rule in candidate.rules if not rule.passed]
    return [
        {
            "section": "Why it passed",
            "detail": ", ".join(rule.name for rule in passed[:8]) or "No passed rules recorded.",
        },
        {
            "section": "Failed gates",
            "detail": ", ".join(rule.name for rule in failed[:8]) or "None",
        },
        {
            "section": "Options fit",
            "detail": _options_fit_text(candidate),
        },
        {
            "section": "Plan",
            "detail": (
                f"Entry {candidate.metrics.resistance:.2f}-{candidate.metrics.breakout_level:.2f}; "
                f"stop {candidate.metrics.stop_level:.2f}; target {candidate.metrics.target_1:.2f}."
            ),
        },
    ]


def _watchlist_context(candidate: ScanCandidate, row: pd.Series) -> dict[str, object]:
    return {
        "saved_status": candidate.setup_status,
        "quality": candidate.quality_label,
        "qx_action": str(row.get("qx_action", "")),
        "trade_posture": str(row.get("trade_posture", "")),
        "timing_read": str(row.get("timing_read", "")),
        "setup_score": round(candidate.setup_score, 3),
        "rank_score": float(row.get("qx_rect_score", 0.0) or 0.0),
        "breakout_level": round(candidate.metrics.breakout_level, 2),
        "stop_level": round(candidate.metrics.stop_level, 2),
        "target_1": round(candidate.metrics.target_1, 2),
        "risk_reward": round(candidate.metrics.risk_reward, 2),
        "missing_rules": candidate.failed_rule_names[:5],
    }


def _saved_watchlist_frame(entries: list[StoredWatchlistSymbol]) -> pd.DataFrame:
    rows = []
    for entry in entries:
        context = getattr(entry, "context", {}) or {}
        rows.append(
            {
                "symbol": entry.symbol,
                "saved_status": context.get("saved_status") or entry.status or "Saved",
                "qx_action": context.get("qx_action") or entry.status,
                "trade_posture": context.get("trade_posture", ""),
                "setup_score": context.get("setup_score"),
                "breakout_level": context.get("breakout_level"),
                "updated_at": entry.updated_at,
                "source": entry.source,
            }
        )
    return pd.DataFrame(rows)


def _passed_reason_text(candidate: ScanCandidate) -> str:
    reasons = [
        candidate.metrics.box_status,
        candidate.metrics.volume_status,
        candidate.metrics.trend_status,
        candidate.metrics.breakout_status,
    ]
    return ", ".join(reason for reason in reasons if reason and reason != "Unknown")


def _options_fit_text(candidate: ScanCandidate) -> str:
    if candidate.metrics.avg_dollar_volume_20d < 50_000_000:
        return "Avoid options until liquidity improves."
    action = candidate_table([candidate]).loc[0, "qx_action"]
    if action in {"A+ Ready", "Ready", "Breakout", "Retest"}:
        return "Review liquid call/LEAPS contracts; validate spreads and IV first."
    if action == "Watch":
        return "Watch options only; wait for trigger confirmation."
    return "No options action yet."


def _format_scan_time(value: object) -> str:
    if not value:
        return "Not run"
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return str(value)
    return parsed.astimezone(MARKET_TIMEZONE).strftime("%b %d %I:%M %p")


def _cache_health_label(universe_mode: str, symbols_text: str, period: str) -> str:
    try:
        symbols = _selected_symbols(universe_mode, symbols_text)
        health = assess_cache_health(symbols, period=period)
    except Exception:
        return "Unknown"
    if health.latest_modified_at:
        return f"{health.label} ({friendly_iso_time(health.latest_modified_at)})"
    return health.label


def _render_cache_warning(
    streamlit: Any,
    universe_mode: str,
    symbols_text: str,
    period: str,
    data_source: str,
) -> None:
    try:
        health = assess_cache_health(_selected_symbols(universe_mode, symbols_text), period=period)
    except Exception:
        return
    if health.stale:
        streamlit.warning(
            f"{data_source} is currently backed by stale local bars. {health.message} "
            "Enable 'Refresh live bars' before trusting a current-data scan."
        )
    elif not health.ready:
        streamlit.info(f"Cache status: {health.message}")


run_standalone_page(
    "Scanner",
    "Find rectangle breakout candidates across custom symbols or index universes.",
    render_scan_page,
)
