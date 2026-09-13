from pathlib import Path
from typing import Any

import pandas as pd

from qx.data.cache import CachedMarketDataProvider
from qx.data.factory import build_fallback_market_data_provider
from qx.data.universe import UNIVERSE_OPTIONS
from qx.storage.sqlite import SQLiteScanRepository
from qx.storage.watchlist import SQLiteWatchlistRepository, StoredWatchlistSymbol
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame
from qx.ui.pages.scan import selected_symbols
from qx.watchlist.engine import build_broad_watchlist, watchlist_frame
from qx.ui.workspace_context import read_context, sync_context, workspace_url


SCAN_HISTORY_DB = Path("data/scanner_history.db")


def render_watchlist_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    context = read_context(getattr(streamlit, "query_params", {}))
    universe_options = ["Saved Scanner Review", "Custom", *UNIVERSE_OPTIONS.keys()]
    preferred = "Custom" if context.get("universe") == "custom" else next((name for name, code in UNIVERSE_OPTIONS.items() if code == context.get("universe")), "Saved Scanner Review")
    streamlit.subheader("Multi-Signal Ranking")
    streamlit.caption(
        "Ranks symbols by momentum, trend, relative strength, sector leadership, liquidity, volume, market regime, "
        "and optional rectangle scanner context."
    )

    with streamlit.container(border=True):
        control_cols = streamlit.columns([1.3, 0.9, 0.9, 1.0, 0.85])
        universe_mode = control_cols[0].selectbox(
            "Universe / Source",
            universe_options,
            index=universe_options.index(preferred),
            key="watchlist_universe_source",
        )
        data_source = control_cols[1].selectbox(
            "Market Data",
            MARKET_DATA_PROVIDER_OPTIONS,
            index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
            key="watchlist_market_data",
        )
        period = control_cols[2].selectbox(
            "Price History",
            ["6mo", "1y", "2y", "3y", "5y"],
            index=["6mo", "1y", "2y", "3y", "5y"].index(context["period"]) if context.get("period") in {"6mo", "1y", "2y", "3y", "5y"} else 2,
            key="watchlist_price_history",
        )
        limit = control_cols[3].slider(
            "Max Results",
            5,
            100,
            50,
            5,
            key="watchlist_max_results",
        )
        run_clicked = control_cols[4].button("Build Watchlist", type="primary", width="stretch", disabled=bool(context.get("as_of")))
        symbols_text = ""
        if universe_mode == "Custom":
            symbols_text = streamlit.text_area(
                "Custom Symbols", value=context.get("symbol", "AAPL\nMSFT\nNVDA"), height=82,
                key="watchlist_custom_symbols",
            )
        with streamlit.expander("Ranking settings", expanded=False):
            min_score = streamlit.slider(
                "Minimum Rank Score",
                0.0,
                1.0,
                0.50,
                0.05,
                key="watchlist_minimum_rank_score",
            )

    saved_entries = SQLiteWatchlistRepository(SCAN_HISTORY_DB).list_entries()
    if str(universe_mode) == "Saved Scanner Review":
        _render_saved_scanner_context(streamlit, saved_entries)

    sync_context(streamlit, universe={"Custom": "custom", "Saved Scanner Review": "scanner_review"}.get(str(universe_mode), UNIVERSE_OPTIONS.get(str(universe_mode), "custom")), period=str(period))
    if context.get("as_of"):
        streamlit.warning(f"Requested date: {context['as_of']}. A new ranking is not a historical replay.")
        streamlit.link_button("Use current evidence", workspace_url("broad_watchlist", context, as_of="", snapshot=""))
        return
    request = (str(universe_mode), symbols_text, str(data_source), str(period), int(limit),
               tuple(entry.symbol for entry in saved_entries) if universe_mode == "Saved Scanner Review" else ())
    saved = streamlit.session_state.get("broad_watchlist_result")
    if not run_clicked and (saved is None or saved[0] != request):
        streamlit.info("No compatible ranking is loaded for these settings. No market-data request has started.")
        return
    if run_clicked:
        symbols = _watchlist_symbols(str(universe_mode), symbols_text, saved_entries=saved_entries)
        if not symbols:
            streamlit.info("No symbols are available for this selection.")
            return
        with streamlit.spinner(f"Ranking {len(symbols)} symbols..."):
            try:
                provider = CachedMarketDataProvider(build_fallback_market_data_provider(str(data_source)))
                result = build_broad_watchlist(symbols, provider, repository=SQLiteScanRepository(SCAN_HISTORY_DB),
                                              period=str(period), limit=int(limit), enrich_metadata_limit=min(int(limit), 100))
            except Exception:
                streamlit.session_state.pop("broad_watchlist_result", None)
                streamlit.error("The ranking could not be built. Review Data Health and retry explicitly.")
                return
        streamlit.session_state["broad_watchlist_result"] = (request, result)
    else:
        result = saved[1]

    candidates = [candidate for candidate in result.candidates if candidate.final_score >= min_score]
    summary_cols = streamlit.columns(4)
    summary_cols[0].metric("Ranked", result.total_symbols)
    summary_cols[1].metric("Displayed", len(candidates))
    summary_cols[2].metric("Data Issues", result.failed_symbols)
    summary_cols[3].metric("Market Regime", result.regime.label)
    frame = watchlist_frame(candidates)
    if str(universe_mode) == "Saved Scanner Review":
        frame = _attach_saved_context(frame, saved_entries)
    if frame.empty:
        streamlit.info("No symbols met the current broad watchlist threshold.")
        return

    readiness_counts = frame["readiness_label"].value_counts().to_dict()
    readiness_cols = streamlit.columns(5)
    readiness_cols[0].metric("Ready Now", int(readiness_counts.get("Ready Now", 0)))
    readiness_cols[1].metric("Ready Watch", int(readiness_counts.get("Ready Watch", 0)))
    readiness_cols[2].metric("Base Building", int(readiness_counts.get("Base Building", 0)))
    readiness_cols[3].metric("Extended Risk", int(readiness_counts.get("Extended Risk", 0)))
    readiness_cols[4].metric("Avoid", int(readiness_counts.get("Avoid", 0)))

    table_view = streamlit.segmented_control("Table fields", ["Summary", "Full evidence"], default="Summary", key="watchlist_table_fields")
    streamlit.dataframe(
        display_frame(
            frame,
            columns=["symbol", "sector", "readiness_label", "final_score", "close", "trigger_level", "distance_to_trigger_pct", "risk_score"] if table_view != "Full evidence" else [
                "symbol",
                "previous_saved_status",
                "previous_qx_action",
                "previous_posture",
                "saved_setup_score",
                "saved_at",
                "name",
                "sector",
                "readiness_label",
                "setup_state",
                "readiness_score",
                "final_score",
                "close",
                "trigger_level",
                "distance_to_trigger_pct",
                "breakout_setup_score",
                "momentum_score",
                "trend_score",
                "relative_strength_score",
                "risk_score",
                "relative_volume_20d",
                "avg_volume_20d",
                "rectangle_status",
                "options_bias",
                "options_setup",
                "notes",
            ],
        ),
        width="stretch",
        hide_index=True,
    )
    streamlit.download_button(
        "Download broad watchlist CSV",
        frame.to_csv(index=False),
        file_name="broad_watchlist.csv",
        mime="text/csv",
    )
    if result.failures:
        with streamlit.expander("Data failures"):
            streamlit.json(result.failures)


def _watchlist_symbols(
    universe_mode: str,
    symbols_text: str,
    *,
    saved_entries: list[StoredWatchlistSymbol] | None = None,
) -> list[str]:
    if universe_mode == "Saved Scanner Review":
        entries = saved_entries if saved_entries is not None else SQLiteWatchlistRepository(SCAN_HISTORY_DB).list_entries()
        return [entry.symbol for entry in entries]
    return selected_symbols(universe_mode, symbols_text)


def _render_saved_scanner_context(streamlit: Any, entries: list[StoredWatchlistSymbol]) -> None:
    if not entries:
        streamlit.info("No saved qx-review symbols yet. Add symbols from the Scanner detail panel or use Custom.")
        return
    with streamlit.expander("Saved qx-review context", expanded=False):
        streamlit.caption("This shows the previous scanner status captured when each ticker was saved.")
        streamlit.dataframe(
            display_frame(_saved_context_frame(entries)),
            width="stretch",
            hide_index=True,
        )


def _attach_saved_context(frame: pd.DataFrame, entries: list[StoredWatchlistSymbol]) -> pd.DataFrame:
    if frame.empty or not entries:
        return frame
    context = _saved_context_frame(entries).rename(
        columns={
            "saved_status": "previous_saved_status",
            "qx_action": "previous_qx_action",
            "trade_posture": "previous_posture",
        }
    )
    return frame.merge(
        context[
            [
                "symbol",
                "previous_saved_status",
                "previous_qx_action",
                "previous_posture",
                "saved_setup_score",
                "saved_at",
            ]
        ],
        on="symbol",
        how="left",
    )


def _saved_context_frame(entries: list[StoredWatchlistSymbol]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": entry.symbol,
                "saved_status": entry.context.get("saved_status") or entry.status or "Saved",
                "qx_action": entry.context.get("qx_action") or entry.status,
                "trade_posture": entry.context.get("trade_posture", ""),
                "saved_setup_score": entry.context.get("setup_score"),
                "breakout_level": entry.context.get("breakout_level"),
                "stop_level": entry.context.get("stop_level"),
                "target_1": entry.context.get("target_1"),
                "saved_at": entry.updated_at,
                "source": entry.source,
            }
            for entry in entries
        ]
    )


run_standalone_page(
    "Broad Watchlist",
    "Rank symbols with independent momentum, trend, sector, liquidity, volume, and scanner signals.",
    render_watchlist_page,
)
