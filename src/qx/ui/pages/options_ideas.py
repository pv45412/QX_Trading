from pathlib import Path
from typing import Any

import pandas as pd

from qx.data.cache import CachedMarketDataProvider
from qx.data.factory import build_ema_timing_provider
from qx.data.factory import build_fundamental_provider
from qx.data.factory import build_options_chain_provider
from qx.data.factory import build_fallback_market_data_provider
from qx.data.universe import UNIVERSE_OPTIONS
from qx.options.ideas import (
    OptionIdea,
    build_option_trade_plan,
    generate_directional_option_ideas,
    generate_option_ideas,
    option_ideas_frame,
)
from qx.storage.options import (
    SQLiteOptionIdeaRepository,
    option_idea_performance_frame,
    stored_option_ideas_frame,
)
from qx.storage.sqlite import SQLiteScanRepository
from qx.ui.app_shell import ensure_app_styles, render_bullet_list, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, OPTION_CHAIN_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame
from qx.ui.pages.scan import selected_symbols
from qx.watchlist.engine import build_broad_watchlist
from qx.ui.workspace_context import read_context, sync_context, workspace_url


SCAN_HISTORY_DB = Path("data/scanner_history.db")
IDEAS_STATE_KEY = "options_ideas_frame"
IDEAS_CONTEXT_KEY = "options_ideas_context"

IDEA_COLUMNS = [
    "symbol",
    "action",
    "direction",
    "strategy",
    "regime_bucket",
    "strategy_reason",
    "exit_plan",
    "bucket",
    "idea_score",
    "source",
    "underlying_quality",
    "underlying_quality_score",
    "income_suitability",
    "leaps_suitability",
    "quality_gate",
    "quality_breakdown",
    "quality_missing",
    "timing_label",
    "timing_score",
    "timing_trigger",
    "ema_alignment",
    "market_cap",
    "eps_growth",
    "revenue_growth",
    "roe",
    "debt_to_equity",
    "profit_margin",
    "free_cash_flow_positive",
    "setup_quality",
    "options_bias",
    "setup_type",
    "technical_timing",
    "underlying_price",
    "underlying_score",
    "directional_score",
    "contract_score",
    "liquidity_score",
    "contract_symbol",
    "expiration",
    "dte",
    "strike",
    "bid",
    "ask",
    "spread_pct",
    "volume",
    "open_interest",
    "implied_volatility",
    "liquidity_note",
    "volatility_note",
    "risk_note",
    "rationale",
]


def render_options_ideas_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    context = read_context(getattr(streamlit, "query_params", {}))
    universe_options = ["Custom", *UNIVERSE_OPTIONS.keys()]
    preferred_universe = "Custom" if context.get("universe") == "custom" else next((name for name, code in UNIVERSE_OPTIONS.items() if code == context.get("universe")), "S&P 500")
    streamlit.subheader("Options Ideas")
    streamlit.caption(
        "First-pass options idea generation from rectangle candidates or the broader directional watchlist. "
        "Use these as research prompts, not automatic trades."
    )

    with streamlit.container(border=True):
        control_cols = streamlit.columns([1.35, 1.0, 0.85, 0.95, 0.85])
        idea_source = control_cols[0].selectbox(
            "Idea Source",
            ["Rectangle scanner history", "Broad directional watchlist"],
            index=1,
            key="options_idea_source",
        )
        universe_mode = control_cols[1].selectbox(
            "Universe",
            universe_options,
            index=universe_options.index(preferred_universe),
            key="options_universe",
        )
        period = control_cols[2].selectbox(
            "History",
            ["6mo", "1y", "2y", "3y", "5y"],
            index=["6mo", "1y", "2y", "3y", "5y"].index(context["period"]) if context.get("period") in {"6mo", "1y", "2y", "3y", "5y"} else 2,
            key="options_history",
        )
        limit = control_cols[3].slider(
            "Idea Limit",
            5,
            100,
            25,
            5,
            key="options_idea_limit",
        )
        build_clicked = control_cols[4].button(
            "Build Ideas",
            type="primary",
            width="stretch",
            disabled=bool(context.get("as_of")),
        )
        symbols_text = streamlit.text_area(
            "Options Symbols",
            value=context.get("symbol", "AAPL\nMSFT\nNVDA"),
            height=82,
            help="Used only when Universe is Custom.",
            key="options_symbols",
            disabled=universe_mode != "Custom",
        )
        with streamlit.expander("Data, fundamentals, and timing filters", expanded=False):
            settings_cols = streamlit.columns([1.0, 1.0, 1.0, 1.0, 1.0])
            chain_source = settings_cols[0].selectbox(
                "Option Chain",
                OPTION_CHAIN_PROVIDER_OPTIONS,
                index=provider_index(OPTION_CHAIN_PROVIDER_OPTIONS),
                key="options_chain_source",
            )
            data_source = settings_cols[1].selectbox(
                "Underlying Data",
                MARKET_DATA_PROVIDER_OPTIONS,
                index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
                key="options_underlying_data",
            )
            fundamental_source = settings_cols[2].selectbox(
                "Fundamentals",
                ["yfinance", "none"],
                index=0,
                key="options_fundamental_source",
            )
            timing_source = settings_cols[3].selectbox(
                "EMA Timing",
                ["schwab", "yfinance", "none"],
                index=0,
                key="options_timing_source",
            )
            min_directional_score = settings_cols[4].slider(
                "Directional Floor",
                0.0,
                1.0,
                0.50,
                0.05,
                key="options_min_directional_score",
            )

    sync_context(streamlit, universe="custom" if universe_mode == "Custom" else UNIVERSE_OPTIONS[str(universe_mode)], period=str(period))
    if context.get("as_of"):
        streamlit.warning(f"Requested date: {context['as_of']}. Historical option chains are not available in this workflow.")
        streamlit.link_button("Use current evidence", workspace_url("options_ideas", context, as_of="", snapshot=""))
        return
    request_context = {
        "source": idea_source, "chain_source": chain_source, "data_source": data_source,
        "fundamental_source": fundamental_source, "timing_source": timing_source, "period": period,
        "universe": universe_mode, "symbols": symbols_text if universe_mode == "Custom" else "",
        "limit": limit, "minimum": min_directional_score,
    }
    if build_clicked:
        try:
            frame = _build_ideas_frame(
                idea_source=str(idea_source),
                chain_source=str(chain_source),
                data_source=str(data_source),
                fundamental_source=str(fundamental_source),
                timing_source=str(timing_source),
                period=str(period),
                universe_mode=str(universe_mode),
                symbols_text=str(symbols_text),
                limit=int(limit),
                min_directional_score=float(min_directional_score),
                streamlit=streamlit,
            )
        except Exception:
            streamlit.session_state.pop(IDEAS_STATE_KEY, None)
            streamlit.session_state.pop(IDEAS_CONTEXT_KEY, None)
            streamlit.error("Ideas could not be built from the selected sources. No previous result is substituted.")
            return
        streamlit.session_state[IDEAS_STATE_KEY] = frame
        streamlit.session_state[IDEAS_CONTEXT_KEY] = request_context

    frame = streamlit.session_state.get(IDEAS_STATE_KEY)
    if frame is not None and streamlit.session_state.get(IDEAS_CONTEXT_KEY) != request_context:
        streamlit.info("Settings changed. The previous ideas are not compatible with this selection; no rebuild has started.")
        return
    if frame is None:
        streamlit.info("Choose a source, then build ideas. Rectangle scanner history remains separate from broad directional ideas.")
        return
    if frame.empty:
        streamlit.info("No option ideas met the current filters.")
        return

    context = streamlit.session_state.get(IDEAS_CONTEXT_KEY, {})
    streamlit.caption(
        "Current run: "
        f"{context.get('source', 'unknown')} | chains: {context.get('chain_source', 'none')} | "
        f"data: {context.get('data_source', 'unknown')} | fundamentals: "
        f"{context.get('fundamental_source', 'unknown')} | timing: {context.get('timing_source', 'none')} | "
        f"history: {context.get('period', 'unknown')}"
    )

    _render_score_strip(streamlit, frame)
    _render_save_and_validation(streamlit, frame, str(chain_source), str(data_source))

    selected_view = streamlit.selectbox(
        "Options view",
        [
            "Ideas Table",
            "Quality Triage",
            "Trade Plan",
            "Strategy Buckets",
            "Contract Detail",
            "Risk Review",
            "Saved Ideas",
        ]
    )
    if selected_view == "Ideas Table":
        filtered = _render_filters(streamlit, frame)
        _render_ideas_table(streamlit, filtered)
        streamlit.download_button(
            "Download filtered ideas CSV",
            filtered.to_csv(index=False),
            file_name="options_ideas.csv",
            mime="text/csv",
        )
    elif selected_view == "Quality Triage":
        _render_quality_triage(streamlit, frame)
    elif selected_view == "Trade Plan":
        _render_trade_plan(streamlit, frame)
    elif selected_view == "Strategy Buckets":
        _render_bucket_view(streamlit, frame)
    elif selected_view == "Contract Detail":
        _render_contract_view(streamlit, frame)
    elif selected_view == "Risk Review":
        _render_risk_view(streamlit, frame)
    elif selected_view == "Saved Ideas":
        _render_saved_ideas(streamlit, str(data_source))


def _build_ideas_frame(
    *,
    idea_source: str,
    chain_source: str,
    data_source: str,
    fundamental_source: str,
    timing_source: str,
    period: str,
    universe_mode: str,
    symbols_text: str,
    limit: int,
    min_directional_score: float,
    streamlit: Any,
) -> pd.DataFrame:
    try:
        chain_provider = build_options_chain_provider(chain_source)
    except Exception as exc:
        streamlit.warning(f"Option chain source unavailable: {exc}")
        chain_provider = None
    try:
        fundamental_provider = build_fundamental_provider(fundamental_source)
    except Exception as exc:
        streamlit.warning(f"Fundamentals source unavailable: {exc}")
        fundamental_provider = None
    try:
        timing_provider = build_ema_timing_provider(timing_source)
    except Exception as exc:
        streamlit.warning(f"EMA timing source unavailable: {exc}")
        timing_provider = None

    if idea_source == "Rectangle scanner history":
        candidates = SQLiteScanRepository(SCAN_HISTORY_DB).latest_candidates()
        ideas = generate_option_ideas(candidates, limit=limit, chain_provider=chain_provider)
    else:
        symbols = selected_symbols(universe_mode, symbols_text)
        provider = CachedMarketDataProvider(build_fallback_market_data_provider(data_source))
        with streamlit.spinner(f"Ranking {len(symbols)} underlyings for directional ideas..."):
            watchlist = build_broad_watchlist(
                symbols,
                provider,
                repository=SQLiteScanRepository(SCAN_HISTORY_DB),
                period=period,
                limit=max(limit * 3, limit),
            )
        if watchlist.failures:
            with streamlit.expander("Underlying data failures"):
                streamlit.json(watchlist.failures)
        ideas = generate_directional_option_ideas(
            watchlist.candidates,
            limit=limit,
            min_directional_score=min_directional_score,
            chain_provider=chain_provider,
            fundamental_provider=fundamental_provider,
            timing_provider=timing_provider,
        )
    return _ordered_frame(option_ideas_frame(ideas))


def _render_score_strip(streamlit: Any, frame: pd.DataFrame) -> None:
    summary = summarize_options_frame(frame)
    cols = streamlit.columns(8)
    cols[0].metric("Ideas", summary["ideas"])
    cols[1].metric("Trade candidates", summary["trade_candidates"])
    cols[2].metric("Watch", summary["watch"])
    cols[3].metric("Bull / Bear", f"{summary['bullish']} / {summary['bearish']}")
    cols[4].metric("Avg idea score", f"{summary['avg_idea_score']:.2f}")
    cols[5].metric("Liquid contracts", summary["liquid_contracts"])
    cols[6].metric("Institutional/Core", summary["core_quality"])
    cols[7].metric("Income eligible", summary["income_eligible"])
    timing_cols = streamlit.columns(3)
    timing_cols[0].metric("Timing aligned", summary["timing_aligned"])
    timing_cols[1].metric("Real fundamentals", summary["fundamental_coverage"])
    timing_cols[2].metric("Wait timing", summary["wait_timing"])


def _render_save_and_validation(
    streamlit: Any,
    frame: pd.DataFrame,
    chain_source: str,
    data_source: str,
) -> None:
    cols = streamlit.columns([1, 1, 2])
    if cols[0].button("Save current ideas"):
        saved = SQLiteOptionIdeaRepository(SCAN_HISTORY_DB).save_ideas(_ideas_from_frame(frame))
        streamlit.success(f"Saved {saved} option ideas.")
    if cols[1].button("Update underlying returns"):
        provider = CachedMarketDataProvider(build_fallback_market_data_provider(data_source))
        updated = SQLiteOptionIdeaRepository(SCAN_HISTORY_DB).update_performance(provider)
        streamlit.success(f"Updated {updated} saved ideas.")

    validation = validate_option_chain_frame(frame, chain_source=chain_source)
    if validation["source"] == "schwab" and validation["attached_contracts"] == 0:
        cols[2].warning("Schwab selected, but no validated contracts attached to these ideas.")
    elif validation["source"] == "schwab":
        cols[2].success(
            f"Schwab contracts attached: {validation['attached_contracts']} | "
            f"liquid: {validation['liquid_contracts']}"
        )
    elif validation["source"] == "none":
        cols[2].info("No chain source selected; contract fields use underlying setup only.")
    else:
        cols[2].info(
            f"{validation['source']} contracts attached: {validation['attached_contracts']} | "
            f"liquid: {validation['liquid_contracts']}"
        )


def _render_filters(streamlit: Any, frame: pd.DataFrame) -> pd.DataFrame:
    actions = _sorted_values(frame, "action")
    directions = _sorted_values(frame, "direction")
    sources = _sorted_values(frame, "source")
    buckets = _sorted_values(frame, "bucket")

    cols = streamlit.columns([1.2, 1.2, 1.4, 1.4])
    selected_actions = cols[0].multiselect("Action", actions, default=actions)
    selected_directions = cols[1].multiselect("Direction", directions, default=directions)
    selected_sources = cols[2].multiselect("Source", sources, default=sources)
    selected_buckets = cols[3].multiselect("DTE bucket", buckets, default=buckets)

    score_cols = streamlit.columns([1, 1, 1, 2])
    min_score = score_cols[0].slider("Min idea score", 0.0, 1.0, 0.0, 0.05)
    max_spread = score_cols[1].slider("Max spread %", 0.0, 1.0, 1.0, 0.05)
    min_oi = score_cols[2].number_input("Min OI", min_value=0, value=0, step=50)
    ticker_query = score_cols[3].text_input("Ticker contains", value="")

    return filter_options_frame(
        frame,
        actions=selected_actions,
        directions=selected_directions,
        sources=selected_sources,
        buckets=selected_buckets,
        min_score=float(min_score),
        max_spread=float(max_spread),
        min_open_interest=int(min_oi),
        ticker_query=ticker_query,
    )


def _render_ideas_table(streamlit: Any, frame: pd.DataFrame) -> None:
    if frame.empty:
        streamlit.info("No rows match the current table filters.")
        return
    view = streamlit.segmented_control("Table fields", ["Summary", "Full evidence"], default="Summary", key="options_table_fields")
    summary = ["symbol", "action", "strategy", "bucket", "idea_score", "quality_gate", "timing_label", "contract_symbol"]
    columns = IDEA_COLUMNS if view == "Full evidence" else summary
    streamlit.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_order=[column for column in columns if column in frame.columns],
        column_config={
            "idea_score": streamlit.column_config.ProgressColumn("idea", min_value=0.0, max_value=1.0),
            "underlying_score": streamlit.column_config.ProgressColumn("underlying", min_value=0.0, max_value=1.0),
            "underlying_quality_score": streamlit.column_config.ProgressColumn("quality", min_value=0.0, max_value=1.0),
            "timing_score": streamlit.column_config.ProgressColumn("timing", min_value=0.0, max_value=1.0),
            "directional_score": streamlit.column_config.ProgressColumn("directional", min_value=0.0, max_value=1.0),
            "contract_score": streamlit.column_config.ProgressColumn("contract", min_value=0.0, max_value=1.0),
            "liquidity_score": streamlit.column_config.ProgressColumn("liquidity", min_value=0.0, max_value=1.0),
            "spread_pct": streamlit.column_config.NumberColumn("spread", format="%.1%%"),
            "implied_volatility": streamlit.column_config.NumberColumn("IV", format="%.1%%"),
        },
    )


def _render_trade_plan(streamlit: Any, frame: pd.DataFrame) -> None:
    streamlit.subheader("Options Detail / Trade Plan")
    symbols = [str(symbol) for symbol in frame["symbol"].dropna().unique()]
    selected_symbol = streamlit.selectbox("Select idea", symbols)
    symbol_rows = frame[frame["symbol"] == selected_symbol].sort_values("idea_score", ascending=False)
    if symbol_rows.empty:
        streamlit.info("No detail available for the selected idea.")
        return

    idea = _idea_from_row(symbol_rows.iloc[0])
    plan = build_option_trade_plan(idea)
    cols = streamlit.columns(4)
    cols[0].metric("Action", idea.action)
    cols[1].metric("Direction", idea.direction)
    cols[2].metric("Idea score", f"{idea.idea_score:.2f}")
    cols[3].metric("Underlying", f"{idea.underlying_price:.2f}" if idea.underlying_price else "n/a")
    quality_cols = streamlit.columns(4)
    quality_cols[0].metric("Quality gate", idea.quality_gate)
    quality_cols[1].metric("Underlying quality", idea.underlying_quality)
    quality_cols[2].metric("Income", idea.income_suitability)
    quality_cols[3].metric("LEAPS", idea.leaps_suitability)
    timing_cols = streamlit.columns(4)
    timing_cols[0].metric("Timing", idea.timing_label)
    timing_cols[1].metric("Timing score", f"{idea.timing_score:.2f}")
    timing_cols[2].metric("Trigger", idea.timing_trigger)
    timing_cols[3].metric("FCF positive", "Yes" if idea.free_cash_flow_positive else "No/Unknown")

    streamlit.write(f"**{plan.title}**")
    streamlit.write(plan.thesis)
    streamlit.write(plan.structure)

    plan_cols = streamlit.columns(3)
    with plan_cols[0]:
        streamlit.write("**Entry Checklist**")
        render_bullet_list(streamlit, plan.entry_checklist)
    with plan_cols[1]:
        streamlit.write("**Invalidation / Target**")
        render_bullet_list(streamlit, [plan.invalidation, plan.target])
    with plan_cols[2]:
        streamlit.write("**Risk Controls**")
        render_bullet_list(streamlit, plan.risk_controls)


def _render_bucket_view(streamlit: Any, frame: pd.DataFrame) -> None:
    streamlit.subheader("Regime Strategy Selection")
    streamlit.caption("The market environment selects the instrument first; contract selection comes after that.")

    streamlit.dataframe(
        display_frame(options_strategy_playbook_frame()),
        width="stretch",
        hide_index=True,
    )

    streamlit.subheader("Live Idea Distribution")
    streamlit.dataframe(
        display_frame(options_regime_strategy_frame(frame)),
        width="stretch",
        hide_index=True,
    )

    streamlit.subheader("DTE Buckets")
    bucket_frame = options_bucket_frame(frame)
    streamlit.dataframe(display_frame(bucket_frame), width="stretch", hide_index=True)

    action_frame = options_action_frame(frame)
    streamlit.subheader("Action Quality")
    streamlit.dataframe(display_frame(action_frame), width="stretch", hide_index=True)


def _render_quality_triage(streamlit: Any, frame: pd.DataFrame) -> None:
    streamlit.subheader("Institutional Quality Triage")
    summary = summarize_options_frame(frame)
    cols = streamlit.columns(5)
    cols[0].metric("Institutional/Core", summary["core_quality"])
    cols[1].metric("Income eligible", summary["income_eligible"])
    cols[2].metric("Real fundamentals", summary["fundamental_coverage"])
    cols[3].metric("Timing aligned", summary["timing_aligned"])
    cols[4].metric("Wait timing", summary["wait_timing"])

    streamlit.dataframe(
        display_frame(options_quality_triage_frame(frame)),
        width="stretch",
        hide_index=True,
    )

    streamlit.subheader("Quality Gaps")
    streamlit.caption("Use this to separate compounder/income underlyings from directional-only ideas.")
    streamlit.dataframe(
        display_frame(options_quality_gap_frame(frame)),
        width="stretch",
        hide_index=True,
    )


def _render_contract_view(streamlit: Any, frame: pd.DataFrame) -> None:
    streamlit.subheader("Contract Detail")
    columns = [
        "symbol",
        "direction",
        "contract_symbol",
        "expiration",
        "dte",
        "strike",
        "bid",
        "ask",
        "spread_pct",
        "volume",
        "open_interest",
        "implied_volatility",
        "contract_score",
        "liquidity_score",
    ]
    contract_frame = frame[[column for column in columns if column in frame.columns]].copy()
    streamlit.dataframe(display_frame(contract_frame), width="stretch", hide_index=True)


def _render_risk_view(streamlit: Any, frame: pd.DataFrame) -> None:
    streamlit.subheader("Risk Review")
    columns = [
        "symbol",
        "action",
        "direction",
        "quality_gate",
        "underlying_quality",
        "income_suitability",
        "leaps_suitability",
        "quality_breakdown",
        "quality_missing",
        "technical_timing",
        "timing_label",
        "timing_trigger",
        "ema_alignment",
        "risk_note",
        "liquidity_note",
        "volatility_note",
        "rationale",
    ]
    risk_frame = frame[[column for column in columns if column in frame.columns]].copy()
    streamlit.dataframe(display_frame(risk_frame), width="stretch", hide_index=True)


def _render_saved_ideas(streamlit: Any, data_source: str) -> None:
    streamlit.subheader("Saved Options Watchlist")
    repository = SQLiteOptionIdeaRepository(SCAN_HISTORY_DB)
    status = streamlit.selectbox("Saved status", ["Watch", "Active", "Closed", "Rejected"], index=0)
    if streamlit.button("Refresh saved performance"):
        provider = CachedMarketDataProvider(build_fallback_market_data_provider(data_source))
        updated = repository.update_performance(provider, status=str(status))
        streamlit.success(f"Updated {updated} saved ideas.")
    saved = repository.list_ideas(status=str(status), limit=100)
    if not saved:
        streamlit.info("No saved option ideas in this status bucket.")
        return
    saved_frame = stored_option_ideas_frame(saved)
    streamlit.dataframe(
        display_frame(saved_frame.drop(columns=["payload"], errors="ignore")),
        width="stretch",
        hide_index=True,
    )
    selected = streamlit.selectbox(
        "Performance history",
        [f"{idea.id} | {idea.symbol} | {idea.strategy}" for idea in saved],
    )
    selected_id = int(str(selected).split("|", maxsplit=1)[0].strip())
    history = repository.list_performance(option_idea_id=selected_id, limit=100)
    if not history:
        streamlit.info("No performance snapshots saved for this idea yet.")
        return
    history_frame = option_idea_performance_frame(history)
    streamlit.dataframe(display_frame(history_frame), width="stretch", hide_index=True)


def validate_option_chain_frame(frame: pd.DataFrame, *, chain_source: str) -> dict[str, int | str]:
    attached_contracts = int((frame.get("contract_symbol", pd.Series(dtype=str)).astype(str) != "").sum())
    liquid_contracts = int((frame.get("liquidity_note", pd.Series(dtype=str)) == "Liquid contract").sum())
    weak_spreads = int((frame.get("spread_pct", pd.Series(dtype=float)) > 0.30).sum())
    return {
        "source": chain_source,
        "attached_contracts": attached_contracts,
        "liquid_contracts": liquid_contracts,
        "weak_spreads": weak_spreads,
    }


def _ideas_from_frame(frame: pd.DataFrame) -> list[OptionIdea]:
    return [_idea_from_row(row) for _, row in frame.iterrows()]


def _idea_from_row(row: pd.Series) -> OptionIdea:
    data = {field: row[field] for field in OptionIdea.__dataclass_fields__ if field in row.index}
    return OptionIdea(**data)


def summarize_options_frame(frame: pd.DataFrame) -> dict[str, int | float]:
    if frame.empty:
        return {
            "ideas": 0,
            "trade_candidates": 0,
            "watch": 0,
            "bullish": 0,
            "bearish": 0,
            "avg_idea_score": 0.0,
            "liquid_contracts": 0,
            "core_quality": 0,
            "income_eligible": 0,
            "timing_aligned": 0,
            "fundamental_coverage": 0,
            "wait_timing": 0,
        }
    return {
        "ideas": int(len(frame)),
        "trade_candidates": int((frame["action"] == "Trade Candidate").sum()),
        "watch": int(frame["action"].isin(["Watch", "Quality Watch", "Wait Timing"]).sum()),
        "bullish": int((frame["direction"] == "Bullish").sum()),
        "bearish": int((frame["direction"] == "Bearish").sum()),
        "avg_idea_score": float(frame["idea_score"].mean()),
        "liquid_contracts": int((frame["liquidity_note"] == "Liquid contract").sum()),
        "core_quality": int(
            frame.get("underlying_quality", pd.Series(dtype=str)).isin(["Institutional", "Core"]).sum()
        ),
        "income_eligible": int(
            (frame.get("income_suitability", pd.Series(dtype=str)) == "Put / covered-call eligible").sum()
        ),
        "timing_aligned": int((frame.get("timing_label", pd.Series(dtype=str)) == "Aligned").sum()),
        "fundamental_coverage": int((frame.get("market_cap", pd.Series(dtype=float)) > 0).sum()),
        "wait_timing": int((frame.get("action", pd.Series(dtype=str)) == "Wait Timing").sum()),
    }


def filter_options_frame(
    frame: pd.DataFrame,
    *,
    actions: list[str],
    directions: list[str],
    sources: list[str],
    buckets: list[str],
    min_score: float,
    max_spread: float,
    min_open_interest: int,
    ticker_query: str,
) -> pd.DataFrame:
    filtered = frame.copy()
    if actions:
        filtered = filtered[filtered["action"].isin(actions)]
    if directions:
        filtered = filtered[filtered["direction"].isin(directions)]
    if sources:
        filtered = filtered[filtered["source"].isin(sources)]
    if buckets:
        filtered = filtered[filtered["bucket"].isin(buckets)]
    filtered = filtered[filtered["idea_score"] >= min_score]
    if "spread_pct" in filtered.columns:
        filtered = filtered[(filtered["spread_pct"] <= max_spread) | (filtered["spread_pct"] == 0)]
    if "open_interest" in filtered.columns:
        filtered = filtered[filtered["open_interest"] >= min_open_interest]
    query = ticker_query.strip().upper()
    if query:
        filtered = filtered[filtered["symbol"].str.upper().str.contains(query, regex=False)]
    return filtered.sort_values(["idea_score", "contract_score", "liquidity_score"], ascending=False)


def options_bucket_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return (
        frame.groupby(["strategy", "bucket"], dropna=False)
        .agg(
            ideas=("symbol", "count"),
            trade_candidates=("action", lambda values: int((values == "Trade Candidate").sum())),
            avg_idea_score=("idea_score", "mean"),
            avg_contract_score=("contract_score", "mean"),
            avg_liquidity_score=("liquidity_score", "mean"),
            avg_quality_score=("underlying_quality_score", "mean"),
        )
        .reset_index()
        .sort_values(["trade_candidates", "avg_idea_score", "ideas"], ascending=False)
        .round(3)
    )


def options_regime_strategy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    if "regime_bucket" not in working.columns:
        working["regime_bucket"] = "Not classified"
    if "strategy_reason" not in working.columns:
        working["strategy_reason"] = ""
    if "timing_score" not in working.columns:
        working["timing_score"] = 0.0
    if "underlying_quality_score" not in working.columns:
        working["underlying_quality_score"] = 0.0
    return (
        working.groupby(["regime_bucket", "strategy"], dropna=False)
        .agg(
            ideas=("symbol", "count"),
            trade_candidates=("action", lambda values: int((values == "Trade Candidate").sum())),
            watchlist=("action", lambda values: int(values.isin(["Watch", "Quality Watch", "Wait Timing"]).sum())),
            avg_idea_score=("idea_score", "mean"),
            avg_quality_score=("underlying_quality_score", "mean"),
            avg_timing_score=("timing_score", "mean"),
            symbols=("symbol", lambda values: ", ".join(list(values.astype(str).head(8)))),
            decision_logic=("strategy_reason", _first_non_empty),
        )
        .reset_index()
        .sort_values(["trade_candidates", "avg_idea_score", "ideas"], ascending=False)
        .round(3)
    )


def options_strategy_playbook_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "regime_bucket": "Trending + high conviction",
                "instrument": "Long call",
                "best_when": "Strong directional thesis, quality trend confirmed, IV low/moderate.",
                "exit_framework": "Scale at 25/50/75% and into key support/resistance levels.",
            },
            {
                "regime_bucket": "Trending + moderate conviction",
                "instrument": "Debit spread",
                "best_when": "Directional bias exists, but conviction is moderate or IV/premium is high.",
                "exit_framework": "Scale like long calls; close if trigger support fails.",
            },
            {
                "regime_bucket": "Range-bound / choppy",
                "instrument": "Credit spread",
                "best_when": "Neutral/mild bias, premium is rich, support/resistance is holding.",
                "exit_framework": "Take 50-75% max profit; close if support/resistance breaks.",
            },
            {
                "regime_bucket": "Range-bound + tight target",
                "instrument": "Butterfly / iron butterfly",
                "best_when": "Expected pin near a specific level with muted reaction.",
                "exit_framework": "Use debit-spread style profit scaling; avoid if range expands.",
            },
            {
                "regime_bucket": "Slow thesis (3+ months)",
                "instrument": "LEAPS stock replacement",
                "best_when": "High-quality bullish compounder, longer-term thesis, low theta preference.",
                "exit_framework": "Exit when thesis plays out, trend breaks, or quality gate deteriorates.",
            },
            {
                "regime_bucket": "Short-term momentum (1-5 days)",
                "instrument": "Leveraged ETF / stock only",
                "best_when": "Fast technical reversal or sector rotation where option premium risk is unnecessary.",
                "exit_framework": "Use moving-average rules; never average down after trigger failure.",
            },
        ]
    )


def _first_non_empty(values: pd.Series) -> str:
    for value in values.astype(str):
        if value and value.lower() != "nan":
            return value
    return ""


def options_action_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return (
        frame.groupby(["action", "direction"], dropna=False)
        .agg(
            ideas=("symbol", "count"),
            avg_idea_score=("idea_score", "mean"),
            avg_spread=("spread_pct", "mean"),
            avg_open_interest=("open_interest", "mean"),
            avg_quality_score=("underlying_quality_score", "mean"),
        )
        .reset_index()
        .sort_values(["avg_idea_score", "ideas"], ascending=False)
        .round(3)
    )


def options_quality_triage_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    working = frame.copy()
    working["real_fundamentals"] = working.get("market_cap", pd.Series(dtype=float)).fillna(0) > 0
    working["income_eligible"] = working.get("income_suitability", pd.Series(dtype=str)).isin(
        ["Put / covered-call eligible", "Income eligible after missing checks"],
    )
    working["leaps_eligible"] = working.get("leaps_suitability", pd.Series(dtype=str)).isin(
        ["LEAPS eligible after trigger", "LEAPS watchlist"],
    )
    return (
        working.groupby(["underlying_quality", "quality_gate"], dropna=False)
        .agg(
            ideas=("symbol", "count"),
            trade_candidates=("action", lambda values: int((values == "Trade Candidate").sum())),
            income_eligible=("income_eligible", "sum"),
            leaps_eligible=("leaps_eligible", "sum"),
            real_fundamentals=("real_fundamentals", "sum"),
            avg_idea_score=("idea_score", "mean"),
            avg_quality_score=("underlying_quality_score", "mean"),
            avg_timing_score=("timing_score", "mean"),
        )
        .reset_index()
        .sort_values(["avg_quality_score", "trade_candidates", "ideas"], ascending=False)
        .round(3)
    )


def options_quality_gap_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    columns = [
        "symbol",
        "action",
        "underlying_quality",
        "quality_gate",
        "income_suitability",
        "leaps_suitability",
        "underlying_quality_score",
        "market_cap",
        "eps_growth",
        "revenue_growth",
        "roe",
        "debt_to_equity",
        "profit_margin",
        "free_cash_flow_positive",
        "timing_label",
        "quality_missing",
        "fundamental_note",
    ]
    gap_frame = frame[[column for column in columns if column in frame.columns]].copy()
    if "market_cap" in gap_frame:
        gap_frame["has_fundamentals"] = gap_frame["market_cap"].fillna(0) > 0
    return gap_frame.sort_values(
        ["underlying_quality_score", "timing_label", "symbol"],
        ascending=[False, True, True],
    )


def _ordered_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    ordered_columns = [column for column in IDEA_COLUMNS if column in frame.columns]
    remaining_columns = [column for column in frame.columns if column not in ordered_columns]
    return frame[ordered_columns + remaining_columns].sort_values(
        ["idea_score", "contract_score", "liquidity_score"],
        ascending=False,
    )


def _sorted_values(frame: pd.DataFrame, column: str) -> list[str]:
    if column not in frame.columns:
        return []
    return sorted(str(value) for value in frame[column].dropna().unique())


run_standalone_page(
    "Options Ideas",
    "Generate first-pass options ideas from qx watchlists.",
    render_options_ideas_page,
)
