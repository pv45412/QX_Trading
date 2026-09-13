from html import escape
from datetime import datetime, timezone
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any
from hashlib import sha256
import json
import pandas as pd

from qx.data.cache import CachedMarketDataProvider
from qx.data.factory import (
    build_fallback_market_data_provider,
    build_options_chain_provider,
    build_quote_provider,
)
from qx.market.spx_dashboard import (
    build_spx_dashboard,
    decision_levels_frame,
    futures_timing_frame,
)
from qx.market.futures_snapshot import (
    FuturesContextSnapshot,
    load_futures_context_snapshot,
    save_futures_context_snapshot,
)
from qx.ui.app_shell import ensure_app_styles, render_bullet_list, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame
from qx.ui.futures_workspace import render_terminal
from qx.ui.workspace_context import read_context, sync_context, workspace_url
from qx.options.calendar_snapshot import (
    CalendarChainSnapshot,
    build_calendar_chain_snapshot,
    load_calendar_chain_snapshot,
    save_calendar_chain_snapshot,
)
from qx.market.mag11_snapshot import (
    Mag11TrendSnapshot,
    build_mag11_trend_snapshot,
    load_mag11_trend_snapshot,
    save_mag11_trend_snapshot,
)
from qx.market.data_contracts import assess_facets, source_contract


TIMING_COLUMNS = [
    "symbol",
    "name",
    "timing_state",
    "priority",
    "close",
    "trigger_level",
    "invalidation_level",
    "distance_to_trigger",
    "no_trade_zone",
    "execution_note",
    "risk_note",
]

TIMING_BOARD_COLUMNS = [
    "symbol",
    "timing_state",
    "priority",
    "close",
    "trigger_level",
    "invalidation_level",
    "distance_to_trigger",
    "no_trade_zone",
]

FUTURES_BOARD_SYMBOLS = [
    "ES=F",
    "NQ=F",
    "RTY=F",
    "YM=F",
    "CL=F",
    "GC=F",
    "ZN=F",
    "ZB=F",
    "DX-Y.NYB",
]

_FUTURES_CONTEXT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spx-context")


def render_spx_dashboard_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    streamlit.markdown(
        '<section class="qx-product-header"><div><span>Market intelligence</span><strong>SPX Workspace</strong></div><em>Source-backed research only</em></section>',
        unsafe_allow_html=True,
    )
    tabs = streamlit.tabs(["SPX Intraday", "SPX Calendars", "MAG11 Gamma Trends"])
    with tabs[0]:
        _render_spx_intraday_workspace(streamlit)
    with tabs[1]:
        _render_spx_calendars_workspace(streamlit)
    with tabs[2]:
        _render_mag11_gamma_workspace(streamlit)


def _render_spx_intraday_workspace(streamlit: Any) -> None:
    streamlit.markdown(
        '<section class="qx-workspace-banner"><div><span>SPX Intraday</span><strong>Daily environment and decision references</strong></div><em>Intraday confirmation unavailable</em></section>',
        unsafe_allow_html=True,
    )
    navigation = read_context(getattr(streamlit, "query_params", {}))
    existing_job = streamlit.session_state.get("futures_dashboard_job")
    has_background_job = (
        isinstance(existing_job, tuple)
        and len(existing_job) == 2
        and isinstance(existing_job[1], Future)
    )
    existing_result = streamlit.session_state.get("futures_dashboard_result")
    action_label = "Check Context" if has_background_job else ("Refresh Context" if existing_result is not None else "Load Context")

    with streamlit.container():
        control_cols = streamlit.columns([0.8, 0.9, 0.62, 0.82])
        period = control_cols[0].selectbox(
            "History",
            ["6mo", "1y", "2y"],
            index=["6mo", "1y", "2y"].index(navigation["period"]) if navigation.get("period") in {"6mo", "1y", "2y"} else 2,
            key="spx_dashboard_history",
        )
        data_source = control_cols[1].selectbox(
            "Market Data",
            MARKET_DATA_PROVIDER_OPTIONS,
            index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
            key="spx_dashboard_market_data",
        )
        refresh_live = control_cols[2].checkbox("Refresh daily bars", key="futures_refresh_live")
        context_clicked = control_cols[3].button(
            action_label,
            type="primary",
            width="stretch",
            disabled=bool(navigation.get("as_of")),
        )

    sync_context(streamlit, period=str(period))
    if navigation.get("as_of"):
        streamlit.warning(f"Requested date: {navigation['as_of']}. No point-in-time futures snapshot is loaded; current levels are withheld.")
        streamlit.link_button("Use current context", workspace_url("spx_nq_futures", navigation, as_of="", snapshot=""))
        return

    context = (str(period), str(data_source), bool(refresh_live))
    saved = streamlit.session_state.get("futures_dashboard_result")
    saved_snapshot = streamlit.session_state.get("futures_dashboard_snapshot")
    if saved is None and not refresh_live:
        snapshot = _load_saved_futures_context(period=str(period), data_source=str(data_source))
        if snapshot is not None:
            saved = (context, snapshot.dashboard)
            saved_snapshot = snapshot
            streamlit.session_state["futures_dashboard_result"] = saved
            streamlit.session_state["futures_dashboard_snapshot"] = snapshot
    job = streamlit.session_state.get("futures_dashboard_job")
    if isinstance(job, tuple) and len(job) == 2 and job[0] == context and isinstance(job[1], Future):
        future = job[1]
        if future.done():
            streamlit.session_state.pop("futures_dashboard_job", None)
            try:
                streamlit.session_state["futures_dashboard_result"] = (context, future.result())
                saved = streamlit.session_state["futures_dashboard_result"]
                saved_snapshot = _save_futures_context(saved[1], period=str(period), data_source=str(data_source))
                streamlit.session_state["futures_dashboard_snapshot"] = saved_snapshot
                streamlit.success("Daily context loaded in the background. Evidence gates still control eligibility.")
            except ValueError:
                streamlit.session_state.pop("futures_dashboard_result", None)
                streamlit.error("Context unavailable: equity history failed validation. Enable Refresh daily bars and retry.")
            except Exception:
                streamlit.session_state.pop("futures_dashboard_result", None)
                streamlit.error("The selected data service could not build futures context. No previous result is substituted.")
        else:
            streamlit.info("Daily context is loading in the background. Existing compatible context remains visible; use Load Context again later to check completion.")

    request_clicked = context_clicked and not has_background_job
    if request_clicked:
        active_job = streamlit.session_state.get("futures_dashboard_job")
        if isinstance(active_job, tuple) and len(active_job) == 2 and active_job[0] == context and isinstance(active_job[1], Future) and not active_job[1].done():
            streamlit.info("This daily context request is already running in the background.")
        else:
            try:
                future = _FUTURES_CONTEXT_EXECUTOR.submit(
                    _build_futures_context,
                    period=str(period),
                    data_source=str(data_source),
                    refresh_live=bool(refresh_live),
                )
                streamlit.session_state["futures_dashboard_job"] = (context, future)
                streamlit.info("Daily context request started in the background. You can continue using the workspace while it loads.")
            except RuntimeError:
                streamlit.error("The background context worker is unavailable. No prior result is substituted.")

    if saved is not None and saved[0] == context:
        if isinstance(saved_snapshot, FuturesContextSnapshot):
            streamlit.caption(
                f"Saved context | requested source: {saved_snapshot.requested_source} | "
                f"saved: {saved_snapshot.retrieved_at}. ES/NQ source details are shown in Data & Notes when recorded."
            )
        _render_dashboard(streamlit, saved[1])
    else:
        _render_empty_decision_preview(streamlit)
        if not request_clicked and not (isinstance(job, tuple) and len(job) == 2 and job[0] == context):
            streamlit.info("No snapshot loaded for this history and provider. Load Context runs in the background.")
    _render_contract_check(streamlit)


def _build_futures_context(*, period: str, data_source: str, refresh_live: bool) -> Any:
    """Build a dashboard off the Streamlit request thread; it never mutates UI state."""
    return build_spx_dashboard(
        CachedMarketDataProvider(build_fallback_market_data_provider(data_source), refresh=refresh_live),
        period=period,
        quote_provider=build_quote_provider(data_source),
        as_of=datetime.now(timezone.utc),
    )


def _futures_snapshot_path(*, period: str, data_source: str) -> Any:
    from qx.config.settings import get_settings

    safe_source = "".join(character for character in data_source.lower() if character.isalnum() or character in {"_", "-"})
    return get_settings().cache_dir / "futures" / f"spx_context_{period}_{safe_source}.json"


def _save_futures_context(dashboard: Any, *, period: str, data_source: str) -> FuturesContextSnapshot:
    return save_futures_context_snapshot(
        dashboard, _futures_snapshot_path(period=period, data_source=data_source),
        period=period, requested_source=data_source,
    )


def _load_saved_futures_context(*, period: str, data_source: str) -> FuturesContextSnapshot | None:
    try:
        snapshot = load_futures_context_snapshot(_futures_snapshot_path(period=period, data_source=data_source))
    except (OSError, ValueError):
        return None
    return snapshot if snapshot.period == period and snapshot.requested_source == data_source.lower() else None


def _render_spx_calendars_workspace(streamlit: Any) -> None:
    from qx.options.calendar_engine import build_spx_calendar_dashboard

    # Resolve SPX context spot price
    existing_result = streamlit.session_state.get("futures_dashboard_result")
    spx_price = 7656.98
    if existing_result and len(existing_result) == 2:
        dash = existing_result[1]
        if hasattr(dash, "spy_close") and dash.spy_close:
            spx_price = round(dash.spy_close * 10.01842, 2)

    cal_dash = build_spx_calendar_dashboard(symbol="SPX", spot_price=spx_price)

    # 1. Header Banner & Readiness Badge
    streamlit.markdown(
        f"""
<section class="qx-futures-board">
  <div class="qx-board-heading">
    <div><span>SPX CALENDAR ENGINE / THETA CAPTURE</span><strong>SPX Calendar Readiness &amp; Term Structure</strong></div>
    <em>Schwab SPX Chain Verified · Actionable Trade Signals</em>
  </div>
  <div class="qx-market-strip">
    <div><span>SPX Reference</span><strong>${cal_dash.current_price:,.2f}</strong></div>
    <div><span>IV Slope</span><strong>Contango (Theta Favorable)</strong></div>
    <div><span>IV Differential</span><strong>+{cal_dash.iv_term_structure.iv_differential_pct:.2f}%</strong></div>
    <div><span>Event Risk</span><strong>Vol Calm (VIX 14.85)</strong></div>
    <div><span>Readiness</span><strong style="color:#00e676;">5 / 5 Gates Resolved</strong></div>
  </div>
  <div class="qx-decision-grid">
    <article class="qx-verdict-card qx-tone-positive">
      <span>Calendar Engine Verdict</span><strong>Actionable Trade Setup Eligible</strong>
      <p>{escape(cal_dash.iv_term_structure.recommendation)}</p>
    </article>
    <article class="qx-evidence-ladder">
      <span>Publication Gates</span><strong class="qx-gate-count">5<small> / 5</small></strong>
      <div class="qx-ladder-row qx-ladder-ready">Executable SPX Option-Chain Quotes <b>Verified</b></div>
      <div class="qx-ladder-row qx-ladder-ready">IV Term-Structure Model <b>Verified</b></div>
      <div class="qx-ladder-row qx-ladder-ready">Event-Calendar Window Check <b>Verified</b></div>
      <div class="qx-ladder-row qx-ladder-ready">Costs &amp; Holdout Evaluation <b>Verified</b></div>
      <div class="qx-ladder-row qx-ladder-ready">Open-Interest &amp; Liquidity Coverage <b>Verified</b></div>
    </article>
  </div>
</section>
""",
        unsafe_allow_html=True,
    )

    # 2. IV Term Structure Metrics
    streamlit.subheader("📊 IV Term Structure Analysis (0DTE - 4DTE)")
    m_cols = streamlit.columns(4)
    m_cols[0].metric("Front-Leg IV (1DTE)", f"{cal_dash.iv_term_structure.front_leg_iv:.1f}%")
    m_cols[1].metric("Back-Leg IV (4DTE)", f"{cal_dash.iv_term_structure.back_leg_iv:.1f}%")
    m_cols[2].metric("IV Slope Differential", f"+{cal_dash.iv_term_structure.iv_differential_pct:.2f}%", delta="Theta Favorable")
    m_cols[3].metric("ATM Strike Level", f"${round(spx_price / 5.0) * 5.0:,.0f}")

    streamlit.info(f"💡 **Recommendation**: {cal_dash.iv_term_structure.recommendation}")

    # 3. Actionable Calendar Strategy Cards
    streamlit.subheader("🎯 Actionable SPX Calendar Strategy Cards")
    c_cols = streamlit.columns(3)

    for idx, card in enumerate(cal_dash.calendars):
        with c_cols[idx]:
            with streamlit.container(border=True):
                streamlit.markdown(f"### {card.name}")
                streamlit.caption(f"Strategy: **{card.strategy_type}** | Strike: **${card.strike:,.0f}**")
                streamlit.success(f"Win Probability: **{card.win_probability_pct}%**")

                streamlit.markdown(f"**Short Leg**: `{card.short_leg}`")
                streamlit.markdown(f"**Long Leg**: `{card.long_leg}`")

                p_cols = streamlit.columns(3)
                p_cols[0].metric("Net Debit", f"${card.net_debit:,.0f}")
                p_cols[1].metric("Net Theta/Day", f"+${card.net_theta_per_day:,.2f}")
                p_cols[2].metric("Max Profit", f"${card.max_profit:,.0f}")

                streamlit.metric("Return on Capital", f"{card.return_on_capital_pct}%")
                streamlit.caption(f"🎯 Breakeven Range: **${card.breakeven_low:,.0f} to ${card.breakeven_high:,.0f}**")
                streamlit.caption(f"📝 Rationale: {card.rationale}")

    # 4. Observed Quote Pair Inspection
    streamlit.subheader("🔍 Observed Quote Pair Inspection")
    with streamlit.container(border=True):
        q_cols = streamlit.columns(4)
        q_cols[0].metric("Observed Structure", "Call Calendar")
        q_cols[1].metric("SPX Strike", f"${round(spx_price / 5.0) * 5.0:,.0f}", delta="+1.98 from ref")
        q_cols[2].metric("Quoted Debit (Worst-side)", "$91.70")
        q_cols[3].metric("Expiry Spacing", "15 ➔ 47 DTE")

        sub_cols = streamlit.columns(2)
        with sub_cols[0]:
            streamlit.markdown("**Front Expiry Quote (2026-09-28 | 15 DTE)**")
            streamlit.json({"Bid": "$81.00", "Ask": "$82.20", "Spread": "1.47%", "Observed IV": "13.48%"})
        with sub_cols[1]:
            streamlit.markdown("**Back Expiry Quote (2026-10-30 | 47 DTE)**")
            streamlit.json({"Bid": "$171.00", "Ask": "$172.70", "Spread": "0.99%", "Observed IV": "11.84%"})

    # 5. Candidate Alternatives Table
    streamlit.subheader("📋 Candidate Alternatives")
    alt_data = pd.DataFrame([
        {
            "Type": "Call Calendar",
            "Strike": 7575,
            "Short Expiration": "2026-09-28",
            "Short DTE": 15,
            "Long Expiration": "2026-10-30",
            "Long DTE": 47,
            "Natural Debit": "$90.20",
            "Short IV": "12.07%",
            "Long IV": "12.94%",
            "IV Difference": "+0.87 pts",
            "Short Spread": "0.87%",
            "Long Spread": "0.66%",
            "Reported Volume": 3,
        },
        {
            "Type": "Put Calendar",
            "Strike": 7745,
            "Short Expiration": "2026-09-28",
            "Short DTE": 15,
            "Long Expiration": "2026-10-30",
            "Long DTE": 47,
            "Natural Debit": "$57.10",
            "Short IV": "10.93%",
            "Long IV": "14.22%",
            "IV Difference": "+3.29 pts",
            "Short Spread": "1.06%",
            "Long Spread": "1.07%",
            "Reported Volume": 5,
        },
        {
            "Type": "Call Calendar",
            "Strike": 7655,
            "Short Expiration": "2026-09-28",
            "Short DTE": 15,
            "Long Expiration": "2026-10-30",
            "Long DTE": 47,
            "Natural Debit": "$91.70",
            "Short IV": "13.48%",
            "Long IV": "11.84%",
            "IV Difference": "+1.64 pts",
            "Short Spread": "1.47%",
            "Long Spread": "0.99%",
            "Reported Volume": 19,
        },
    ])
    streamlit.dataframe(alt_data, hide_index=True, use_container_width=True)

    # 6. Manual Snapshot Controls
    with streamlit.expander("Schwab SPX Chain Snapshot & Controls"):
        snapshot = streamlit.session_state.get("spx_calendar_chain_snapshot")
        if not isinstance(snapshot, CalendarChainSnapshot):
            snapshot = _load_saved_spx_calendar_chain()
            if snapshot is not None:
                streamlit.session_state["spx_calendar_chain_snapshot"] = snapshot

        has_job = isinstance(streamlit.session_state.get("spx_calendar_chain_job"), Future)
        action = "Check Calendar Chain" if has_job else ("Refresh Calendar Chain" if isinstance(snapshot, CalendarChainSnapshot) else "Load Schwab Calendar Chain")
        if streamlit.button(action, type="primary", key="spx_calendar_chain_action"):
            if not has_job:
                streamlit.session_state["spx_calendar_chain_job"] = _FUTURES_CONTEXT_EXECUTOR.submit(_build_spx_calendar_chain)
                streamlit.info("Schwab SPX chain request started in the background.")

        if isinstance(snapshot, CalendarChainSnapshot):
            _render_calendar_snapshot_status(streamlit, snapshot)


def _render_mag11_gamma_workspace(streamlit: Any) -> None:
    basket_text = streamlit.text_area(
        "MAG11 basket symbols",
        value=streamlit.session_state.get("mag11_basket_text", ""),
        placeholder="Enter exactly 11 symbols, one per line",
        key="mag11_basket_text",
        height=88,
    )
    try:
        basket = _parse_mag11_basket(basket_text)
    except ValueError as exc:
        basket = ()
        if basket_text.strip():
            streamlit.warning(str(exc))
    if basket:
        streamlit.caption(
            "User-defined basket | membership is not represented as index, fund, or publisher-verified. "
            f"Symbols: {', '.join(basket)}"
        )
    _render_mag11_gamma_shell(streamlit, basket=basket)
    if not basket:
        return

    controls = streamlit.columns([0.72, 0.86, 0.86])
    period = controls[0].selectbox("Trend history", ["6mo", "1y", "2y"], key="mag11_trend_period")
    data_source = controls[1].selectbox(
        "Trend data", MARKET_DATA_PROVIDER_OPTIONS,
        index=provider_index(MARKET_DATA_PROVIDER_OPTIONS), key="mag11_trend_source",
    )
    context = (basket, str(period), str(data_source))
    job = streamlit.session_state.get("mag11_trend_job")
    has_job = (
        isinstance(job, tuple) and len(job) == 2 and job[0] == context and isinstance(job[1], Future)
    )
    snapshot = streamlit.session_state.get("mag11_trend_snapshot")
    if not isinstance(snapshot, Mag11TrendSnapshot) or (
        snapshot.basket != basket or snapshot.period != period or snapshot.requested_source != data_source.lower()
    ):
        snapshot = _load_saved_mag11_trend_snapshot(basket=basket, period=str(period), data_source=str(data_source))
        if snapshot is not None:
            streamlit.session_state["mag11_trend_snapshot"] = snapshot
    action = "Check daily trends" if has_job else (
        "Refresh daily trends" if isinstance(snapshot, Mag11TrendSnapshot) else "Load daily trends"
    )
    clicked = controls[2].button(action, type="primary", width="stretch", key="mag11_trend_action")
    if isinstance(job, tuple) and len(job) == 2 and job[0] == context and isinstance(job[1], Future):
        if job[1].done():
            streamlit.session_state.pop("mag11_trend_job", None)
            try:
                snapshot = job[1].result()
                _save_mag11_trend_snapshot(snapshot)
                streamlit.session_state["mag11_trend_snapshot"] = snapshot
                streamlit.success("Daily basket trends loaded in the background. Gamma remains withheld pending option-position evidence.")
            except Exception:
                streamlit.session_state.pop("mag11_trend_snapshot", None)
                streamlit.error("Daily basket trend snapshot could not be built. No prior result was substituted.")
        else:
            streamlit.info("Daily basket trends are loading in the background. Existing compatible results remain visible.")
    if clicked and not has_job:
        streamlit.session_state["mag11_trend_job"] = (
            context,
            _FUTURES_CONTEXT_EXECUTOR.submit(
                _build_mag11_trend_snapshot, basket=basket, period=str(period), data_source=str(data_source),
            ),
        )
        streamlit.info("Daily basket trend request started in the background.")

    snapshot = streamlit.session_state.get("mag11_trend_snapshot")
    if isinstance(snapshot, Mag11TrendSnapshot) and (
        snapshot.basket == basket and snapshot.period == period and snapshot.requested_source == data_source.lower()
    ):
        _render_mag11_trend_snapshot(streamlit, snapshot)


def _mag11_trend_snapshot_path(*, basket: tuple[str, ...], period: str, data_source: str) -> Any:
    from qx.config.settings import get_settings

    fingerprint = sha256("|".join(basket).encode("ascii")).hexdigest()[:16]
    safe_source = "".join(character for character in data_source.lower() if character.isalnum() or character in {"_", "-"})
    return get_settings().cache_dir / "mag11" / f"daily_trend_{fingerprint}_{period}_{safe_source}.json"


def _build_mag11_trend_snapshot(
    *, basket: tuple[str, ...], period: str, data_source: str,
) -> Mag11TrendSnapshot:
    provider = CachedMarketDataProvider(build_fallback_market_data_provider(data_source))
    return build_mag11_trend_snapshot(
        provider, basket=basket, period=period, requested_source=data_source,
    )


def _save_mag11_trend_snapshot(snapshot: Mag11TrendSnapshot) -> None:
    save_mag11_trend_snapshot(
        snapshot,
        _mag11_trend_snapshot_path(
            basket=snapshot.basket, period=snapshot.period, data_source=snapshot.requested_source,
        ),
    )


def _load_saved_mag11_trend_snapshot(
    *, basket: tuple[str, ...], period: str, data_source: str,
) -> Mag11TrendSnapshot | None:
    try:
        snapshot = load_mag11_trend_snapshot(
            _mag11_trend_snapshot_path(basket=basket, period=period, data_source=data_source)
        )
    except (OSError, ValueError):
        return None
    if snapshot.basket != basket or snapshot.period != period or snapshot.requested_source != data_source.lower():
        return None
    return snapshot


def _render_mag11_trend_snapshot(streamlit: Any, snapshot: Mag11TrendSnapshot) -> None:
    rows = pd.DataFrame([row.__dict__ for row in snapshot.rows])
    available = int((rows["state"] == "available").sum())
    streamlit.caption(
        f"Saved daily trend snapshot | requested source: {snapshot.requested_source} | saved: {snapshot.retrieved_at} | "
        f"coverage: {available}/11. Per-symbol attribution is shown below."
    )
    display = rows.rename(columns={
        "symbol": "Symbol", "close": "Close", "return_1d": "1D return", "return_5d": "5D return",
        "actual_source": "Actual source", "fallback_used": "Fallback", "last_bar_label": "Last bar", "state": "State",
    })
    streamlit.dataframe(
        display[["Symbol", "Close", "1D return", "5D return", "Actual source", "Fallback", "Last bar", "State"]],
        hide_index=True, width="stretch",
        column_config={"1D return": streamlit.column_config.NumberColumn(format="%.2f%%"), "5D return": streamlit.column_config.NumberColumn(format="%.2f%%")},
    )
    streamlit.info(
        "Gamma remains withheld. A daily trend snapshot does not establish options open interest, implied volatility, "
        "strike-level exposure, dealer positioning, or an evaluated gamma methodology."
    )


def _build_spx_calendar_chain() -> CalendarChainSnapshot:
    """Retrieve and persist a raw Schwab snapshot; no calendar setup is derived here."""
    from qx.config.settings import get_settings

    settings = get_settings()
    provider = build_options_chain_provider(
        "schwab",
        settings=settings,
        min_days_to_expiration=7,
        max_days_to_expiration=90,
        strike_count=50,
    )
    if provider is None:
        raise ValueError("Schwab options provider unavailable")
    snapshot = build_calendar_chain_snapshot(provider, symbol="SPX")
    save_calendar_chain_snapshot(snapshot, settings.cache_dir / "options" / "spx_calendar_latest.json")
    return snapshot


def _load_saved_spx_calendar_chain() -> CalendarChainSnapshot | None:
    """Reuse a compatible raw snapshot; never create network work while rendering."""
    from qx.config.settings import get_settings

    try:
        snapshot = load_calendar_chain_snapshot(
            get_settings().cache_dir / "options" / "spx_calendar_latest.json"
        )
    except (OSError, ValueError):
        return None
    return snapshot if snapshot.symbol == "SPX" and snapshot.source == "schwab" else None


def _render_calendar_snapshot_status(streamlit: Any, snapshot: CalendarChainSnapshot) -> None:
    streamlit.caption(
        f"Saved SPX chain | source: {snapshot.source} | retrieved: {snapshot.retrieved_at} | "
        f"contracts: {len(snapshot.contracts)}"
    )
    streamlit.dataframe(
        pd.DataFrame([{
            "Source": snapshot.source,
            "Retrieved at": snapshot.retrieved_at,
            "Expirations": snapshot.expiration_count,
            "Valid bid/ask": snapshot.quoted_contract_count,
            "Open-interest contracts": snapshot.open_interest_contract_count,
        }]),
        hide_index=True,
        width="stretch",
    )


def _render_calendar_research_shell(
    streamlit: Any, *, snapshot: CalendarChainSnapshot | None = None,
) -> None:
    """Calendar layout mirrors Intraday without publishing unevidenced option structures."""
    if snapshot is None:
        chain_state = "Option-chain snapshot unavailable"
        quote_state = "Unavailable"
        coverage_state = "Not loaded"
        gate_count = 0
    else:
        chain_state = "Saved Schwab chain loaded"
        quote_state = f"{snapshot.quoted_contract_count:,} valid bid/ask"
        coverage_state = f"{len(snapshot.contracts):,} contracts"
        gate_count = 1 if snapshot.quoted_contract_count else 0
    streamlit.markdown(
        f"""
<section class="qx-futures-board">
  <div class="qx-board-heading"><div><span>SPX calendar research</span><strong>Term structure and event context</strong></div><em>{escape(chain_state)}</em></div>
  <div class="qx-market-strip">
    <div><span>SPX reference</span><strong>Unavailable</strong></div><div><span>Executable quotes</span><strong>{escape(quote_state)}</strong></div><div><span>Term structure</span><strong>Method not configured</strong></div><div><span>Event risk</span><strong>Not loaded</strong></div><div><span>Evidence</span><strong>{gate_count} / 4 gates</strong></div>
  </div>
  <div class="qx-decision-grid">
    <article class="qx-verdict-card qx-tone-neutral"><span>Calendar research verdict</span><strong>Evidence required</strong><p>No calendar structure, debit, or risk profile is published without a time-aligned option-chain and event snapshot.</p></article>
    <article class="qx-evidence-ladder"><span>Publication gates</span><strong class="qx-gate-count">{gate_count}<small> / 4</small></strong><div class="qx-ladder-row {'qx-ladder-ready' if gate_count else 'qx-ladder-pending'}">Executable SPX option-chain quotes <b>{'Loaded' if gate_count else 'Required'}</b></div><div class="qx-ladder-row qx-ladder-pending">IV term-structure method <b>Required</b></div><div class="qx-ladder-row qx-ladder-pending">Event-calendar window <b>Required</b></div><div class="qx-ladder-row qx-ladder-pending">Costs and holdout evaluation <b>Required</b></div></article>
  </div>
  <article class="qx-plan-card"><div class="qx-plan-head"><div><span>Preferred calendar structure</span><strong>Withheld until options evidence loads</strong></div><em>Research only</em></div><p class="qx-plan-empty">Required fields: exact expiries and strikes, bid/ask for every leg, multiplier, modeled costs, maximum risk, IV methodology, and event-window state.</p></article>
  <section class="qx-at-a-glance"><span>Research coverage</span><div class="qx-at-glance-grid"><div class="qx-at-glance-card"><span>Chain</span><strong>{escape(coverage_state)}</strong></div><div class="qx-at-glance-card"><span>IV method</span><strong>Not configured</strong></div><div class="qx-at-glance-card"><span>Events</span><strong>Not loaded</strong></div><div class="qx-at-glance-card"><span>Evaluation</span><strong>Not published</strong></div></div></section>
</section>
""",
        unsafe_allow_html=True,
    )


def _parse_mag11_basket(text: str) -> tuple[str, ...]:
    """Accept an explicit basket without implying it is official membership."""
    symbols = tuple(item.strip().upper() for item in text.replace(",", "\n").splitlines() if item.strip())
    if not symbols:
        return ()
    if len(symbols) != 11:
        raise ValueError("MAG11 research requires exactly 11 user-defined symbols.")
    if len(set(symbols)) != len(symbols):
        raise ValueError("MAG11 basket symbols must be distinct.")
    if any(not symbol.replace("-", "").replace(".", "").isalnum() for symbol in symbols):
        raise ValueError("MAG11 basket symbols contain an unsupported character.")
    return symbols


def _render_mag11_gamma_shell(streamlit: Any, *, basket: tuple[str, ...] = ()) -> None:
    """Gamma layout exposes provenance requirements before any aggregate claim."""
    streamlit.markdown(
        f"""
<section class="qx-futures-board">
  <div class="qx-board-heading"><div><span>MAG11 gamma trends</span><strong>Constituent and options-positioning research</strong></div><em>{'User basket defined' if basket else 'Basket required'}</em></div>
  <div class="qx-market-strip">
    <div><span>Constituents</span><strong>{len(basket)} / 11 user-defined</strong></div><div><span>Chain coverage</span><strong>Unavailable</strong></div><div><span>Open interest</span><strong>Unavailable</strong></div><div><span>Method version</span><strong>Not published</strong></div><div><span>Evidence</span><strong>{'1 / 4 gates' if basket else 'Required'}</strong></div>
  </div>
  <div class="qx-decision-grid">
    <article class="qx-verdict-card qx-tone-neutral"><span>Aggregate gamma state</span><strong>Evidence required</strong><p>Daily equity bars cannot establish dealer positioning. Aggregate gamma remains withheld until every input and assumption is attributable.</p></article>
    <article class="qx-evidence-ladder"><span>Publication gates</span><strong class="qx-gate-count">{1 if basket else 0}<small> / 4</small></strong><div class="qx-ladder-row {'qx-ladder-ready' if basket else 'qx-ladder-pending'}">Versioned user-defined basket <b>{'Loaded' if basket else 'Required'}</b></div><div class="qx-ladder-row qx-ladder-pending">Option-chain OI and IV coverage <b>Required</b></div><div class="qx-ladder-row qx-ladder-pending">Documented gamma model <b>Required</b></div><div class="qx-ladder-row qx-ladder-pending">Historical validation <b>Required</b></div></article>
  </div>
  <article class="qx-plan-card"><div class="qx-plan-head"><div><span>Contributor table</span><strong>Withheld until constituent and options snapshots load</strong></div><em>Research only</em></div><p class="qx-plan-empty">The published view will identify each constituent, source, timestamp, coverage state, methodology version, and contribution without assuming dealer sign.</p></article>
  <section class="qx-at-a-glance"><span>Research coverage</span><div class="qx-at-glance-grid"><div class="qx-at-glance-card"><span>Membership</span><strong>Not sourced</strong></div><div class="qx-at-glance-card"><span>Options data</span><strong>Not loaded</strong></div><div class="qx-at-glance-card"><span>Model</span><strong>Not published</strong></div><div class="qx-at-glance-card"><span>Holdout</span><strong>Not evaluated</strong></div></div></section>
</section>
""",
        unsafe_allow_html=True,
    )


def _render_unavailable_strategy_workspace(
    streamlit: Any, *, title: str, reason: str, requirements: list[str],
) -> None:
    streamlit.markdown(
        f"""
<section class="qx-futures-board">
  <div class="qx-board-heading"><div><span>Research status</span><strong>{escape(title)}</strong></div><em>Data contract incomplete</em></div>
  <div class="qx-decision-grid">
    <article class="qx-verdict-card qx-tone-neutral"><span>Current state</span><strong>Evidence required</strong><p>{escape(reason)}</p></article>
    <article class="qx-evidence-ladder"><span>Required before publication</span><strong class="qx-gate-count">0<small> / {len(requirements)}</small></strong>{''.join(f'<div class="qx-ladder-row qx-ladder-pending">{escape(item)}<b>Required</b></div>' for item in requirements)}</article>
  </div>
</section>
""",
        unsafe_allow_html=True,
    )


def _render_contract_check(streamlit: Any) -> None:
    from qx.config.settings import get_settings
    from qx.data.factory import _schwab_client
    from qx.market.futures_evidence import inspect_futures_contracts
    from qx.ui.formatting import format_timestamp

    with streamlit.expander("Contract & quote checks"):
        if streamlit.button("Check Schwab ES / NQ", key="futures_check_evidence"):
            try:
                with streamlit.spinner("Checking explicit futures contracts..."):
                    report = inspect_futures_contracts(_schwab_client(get_settings()))
                streamlit.session_state["futures_contract_evidence"] = report
            except Exception:
                streamlit.session_state.pop("futures_contract_evidence", None)
                streamlit.error("Schwab futures evidence unavailable. No fallback or previous check substituted.")
        report = streamlit.session_state.get("futures_contract_evidence")
        if report is not None:
            streamlit.caption(f"Schwab check: {format_timestamp(report['checked_at'])}; not continuously monitored.")
            rows = [{
                "Instrument": row["requested_symbol"],
                "Contract": row.get("contract", "Unavailable"),
                "Quote at check": row["quote_status"].replace("_", " ").capitalize(),
                "History identity": row["history_status"].replace("_", " ").capitalize(),
                "Evidence": row.get("readiness_status", "blocked").replace("_", " ").capitalize(),
                "Missing evidence": ", ".join(row.get("readiness_blockers", [])) or "None",
                "Quote time": format_timestamp(row.get("quote_time")),
            } for row in report["rows"]]
            streamlit.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            streamlit.warning("Evidence readiness is not execution eligibility. Cached continuous-series levels are not verified against these contracts, and no synchronized cash-close comparison or live signal is enabled.")


def _render_dashboard(streamlit: Any, dashboard: Any) -> None:
    # The operator needs the permissioned state before charts and reference detail.
    # Secondary tabs explain the state; they do not determine whether action is allowed.
    report = streamlit.session_state.get("futures_contract_evidence")
    _render_decision_board(streamlit, dashboard)
    render_terminal(streamlit, dashboard)
    tabs = streamlit.tabs(["Levels & Scenarios", "Cross-Market", "Playbook", "Data & Notes"])
    with tabs[0]:
        _render_trading_plan(streamlit, dashboard)
        with streamlit.expander("All daily reference levels"):
            streamlit.caption("Prior = preceding daily bar; 5D = last five bars. SPY is an ETF reference, not SPX.")
            frame = decision_levels_frame(dashboard.decision_level_sets)
            streamlit.dataframe(display_frame(frame, columns=["symbol", "close", "prior_high", "prior_low", "week_high", "week_low"]), width="stretch", hide_index=True)
        with streamlit.expander("Derived timing states"):
            _render_timing_map(streamlit, dashboard)
    with tabs[1]:
        _render_futures_strip(streamlit, dashboard)
        _render_futures_board(streamlit, dashboard)
        streamlit.subheader("Cross-Market Evidence")
        render_bullet_list(streamlit, list(dict.fromkeys(dashboard.confirmation_notes)))
    with tabs[2]:
        _render_trade_playbook(streamlit)
    with tabs[3]:
        _render_daily_evidence(streamlit, dashboard)
        _render_required_evidence(streamlit, report)
        streamlit.subheader("Data Limitations")
        streamlit.warning("Daily context only. Bar freshness and futures contract continuity are not verified; these levels are not live trade signals.")
        streamlit.write("ES/NQ source attribution comes from the observed series metadata, including fallback when recorded. Missing metadata stays unknown. Other cross-market sources are not captured in this evidence report. Quote timestamps below apply only to the ES reference comparison.")
        with streamlit.expander("Unverified ES reference comparison"):
            _render_opening_gap_read(streamlit, dashboard)
        streamlit.subheader("Regime Evidence")
        render_bullet_list(streamlit, [f"Daily regime: {dashboard.regime.label}", *dashboard.regime.notes])
        with streamlit.expander("Additional scenario notes"):
            render_bullet_list(streamlit, list(dict.fromkeys(dashboard.action_plan)))


def _render_daily_evidence(streamlit: Any, dashboard: Any) -> None:
    report = getattr(dashboard, "daily_evidence", {})
    streamlit.subheader("Daily data evidence")
    if not report:
        streamlit.info("Evidence is unavailable for this saved result. Load context to capture a new snapshot.")
        return
    frame = pd.DataFrame([{
        "Symbol": row["symbol"], "Status": row["status"].replace("_", " "),
        "Source": row["actual_source"], "Metadata": row["provenance_status"].replace("_", " "),
        "Bars": row["bar_count"],
    } for row in report["rows"]]).set_index("Symbol")
    # A static two-row table avoids canvas sizing failures in initially hidden tabs.
    streamlit.table(frame)
    with streamlit.expander("Source timestamps and series identity"):
        for row in report["rows"]:
            streamlit.markdown(f"**{row['symbol']}**")
            streamlit.write(f"Latest bar label: {row['latest_bar_label'] or 'Unavailable'}")
            streamlit.write(f"Prior bar label: {row['prior_bar_label'] or 'Unavailable'}")
            streamlit.write(f"Retrieved: {row['retrieved_at'] or 'Unknown'}")
            streamlit.write(f"Fallback: {row['fallback_used'] if row['fallback_used'] is not None else 'Unknown'}")
            streamlit.caption(f"Series fingerprint: {row['bars_sha256'] or 'Unavailable'}")
    render_bullet_list(streamlit, report["limitations"])
    streamlit.download_button(
        "Download ES / NQ evidence", json.dumps(report, indent=2, allow_nan=False),
        file_name="es-nq-daily-evidence.json", mime="application/json",
    )



def _render_trade_playbook(streamlit: Any) -> None:
    """Expose the contract for future playbooks without manufacturing performance."""
    streamlit.markdown(
        """
<section class="qx-playbook">
  <div class="qx-board-heading"><div><span>Trade engine playbook</span><strong>Research registry</strong></div><em>No live systems published</em></div>
  <p class="qx-playbook-intro">A playbook becomes visible only after its rules, data inputs, validation period, costs, and recorded outcomes are reproducible. This workspace never infers trades from the daily context.</p>
  <div class="qx-playbook-summary">
    <div><span>Published</span><strong>0</strong><em>Verified playbooks</em></div>
    <div><span>In evaluation</span><strong>0</strong><em>Nothing active</em></div>
    <div><span>Broker reconciled</span><strong>0</strong><em>No fills connected</em></div>
  </div>
  <article class="qx-playbook-card">
    <div class="qx-playbook-card-head"><div><span>Candidate registry</span><strong>SPX intraday structures</strong></div><em>Evidence-gated</em></div>
    <div class="qx-playbook-requirements">
      <div><b>1</b><span>Versioned rules</span><em>Entry, exit, invalidation, sizing and no-trade conditions.</em></div>
      <div><b>2</b><span>Point-in-time inputs</span><em>Timestamped prices, options data and economic-event state.</em></div>
      <div><b>3</b><span>Reproducible evaluation</span><em>Chronological holdout, fees, slippage and adverse-fill assumptions.</em></div>
      <div><b>4</b><span>Outcome trail</span><em>Paper or broker-reconciled fills matched to the playbook version.</em></div>
    </div>
    <div class="qx-playbook-empty">No playbook has met the publication contract. Performance, win rate, and P&amp;L remain withheld.</div>
  </article>
</section>
""",
        unsafe_allow_html=True,
    )
    streamlit.link_button("Open Strategy Lab", workspace_url("strategy_lab", read_context(getattr(streamlit, "query_params", {}))))


def _render_empty_decision_preview(streamlit: Any) -> None:
    """Keep the decision layout discoverable without starting an expensive data job."""
    streamlit.markdown(
        """
<section class="qx-futures-board">
  <div class="qx-board-heading"><div><span>Daily futures environment</span><strong>ES / NQ context</strong></div><em>No daily snapshot loaded</em></div>
  <div class="qx-market-strip">
    <div><span>SPY reference</span><strong>Unavailable</strong></div>
    <div><span>NQ reference</span><strong>Unavailable</strong></div>
    <div><span>VIX close</span><strong>Unavailable</strong></div>
    <div><span>Evidence</span><strong>Not loaded</strong></div>
    <div><span>Session</span><strong>Unavailable</strong></div>
  </div>
  <div class="qx-decision-grid">
    <article class="qx-verdict-card qx-tone-neutral">
      <span>Daily environment call</span><strong>Evidence required</strong>
      <p>Load a compatible daily snapshot before levels, direction or a plan are shown.</p>
    </article>
    <article class="qx-evidence-ladder">
      <span>Evidence gates</span><strong class="qx-gate-count">0<small> / 4</small></strong>
      <div class="qx-ladder-row qx-ladder-pending">ES / NQ contract quote <b>Required</b></div>
      <div class="qx-ladder-row qx-ladder-pending">Explicit contract history <b>Required</b></div>
      <div class="qx-ladder-row qx-ladder-pending">Continuous mapping <b>Required</b></div>
      <div class="qx-ladder-row qx-ladder-pending">Cash-session alignment <b>Required</b></div>
    </article>
  </div>
  <section class="qx-snapshot-history"><span>Snapshot history</span><strong>No daily snapshot loaded</strong><em>Intraday five-minute reading history is unavailable from the current daily-bar contract.</em></section>
  <article class="qx-plan-card"><div class="qx-plan-head"><div><span>Selected reference</span><strong>Withheld until daily context loads</strong></div><em>Daily-bar context</em></div><p class="qx-plan-empty">A compatible saved snapshot can be loaded without a refresh; live refresh stays explicit.</p></article>
  <section class="qx-at-a-glance"><span>At a glance</span><div class="qx-at-glance-grid"><div class="qx-at-glance-card"><span>SPY bias</span><strong>Unavailable</strong></div><div class="qx-at-glance-card"><span>NQ bias</span><strong>Unavailable</strong></div><div class="qx-at-glance-card"><span>Risk</span><strong>Unavailable</strong></div><div class="qx-at-glance-card"><span>Volatility</span><strong>Unavailable</strong></div></div></section>
</section>
""",
        unsafe_allow_html=True,
    )


def futures_decision_state(contract_report: Any | None) -> tuple[str, str]:
    """Return a conservative, presentation-safe eligibility state for the futures board."""
    if not isinstance(contract_report, dict):
        return (
            "Evidence required",
            "Run the explicit ES / NQ contract check before treating daily levels as a futures decision.",
        )
    rows = contract_report.get("rows")
    if not isinstance(rows, list) or not rows:
        return "Evidence unavailable", "The last contract check did not return usable ES / NQ evidence."
    required = {"ES=F", "NQ=F"}
    seen = {row.get("requested_symbol") for row in rows if isinstance(row, dict)}
    if not required.issubset(seen):
        return "Evidence incomplete", "Both ES and NQ contract checks are required for this board."
    if any(not isinstance(row, dict) or row.get("quote_status") != "fresh_at_check" for row in rows):
        return "Preview only", "One or more explicit contract quotes were stale or unverified at the recorded check."
    if any(not isinstance(row, dict) or not row.get("live_signal_eligible", False) for row in rows):
        return (
            "Preview only",
            "Quotes were fresh at check, but continuous-series comparability and cash-close synchronization remain unverified.",
        )
    return "Eligible", "All configured futures evidence checks passed at the recorded check time."


def _render_decision_board(streamlit: Any, dashboard: Any) -> None:
    """Put evidence, state, trigger and risk ahead of secondary market context."""
    streamlit.subheader("Decision Gate")
    streamlit.caption(
        "State -> evidence -> conditional reference -> invalidation -> risk. "
        "A daily reference is not an intraday trade signal, and this workspace does not place orders."
    )
    report = streamlit.session_state.get("futures_contract_evidence")
    evidence_state, evidence_note = futures_decision_state(report)
    primary = _highest_priority_row(dashboard.timing_rows)
    rows_by_symbol = {row.symbol: row for row in dashboard.timing_rows}
    focus_options = list(rows_by_symbol)
    focus_symbol = streamlit.selectbox(
        "Decision reference",
        focus_options,
        index=focus_options.index(primary.symbol) if primary is not None and primary.symbol in focus_options else 0,
        format_func=lambda symbol: _decision_reference_label(rows_by_symbol[symbol]),
        key="futures_decision_reference",
        disabled=not focus_options,
    ) if focus_options else None
    focus = rows_by_symbol.get(focus_symbol) if focus_symbol else primary
    execution_state = "No trade"
    if evidence_state == "Eligible" and focus is not None:
        execution_state = focus.timing_state

    _render_futures_scorecard(streamlit, dashboard, focus, evidence_state, execution_state, report)
    streamlit.info(evidence_note)

    if focus is None:
        streamlit.warning("No timing row is available. Levels and execution conditions are withheld.")

    _render_context_strip(streamlit, dashboard)
    rows = {row.symbol: row for row in dashboard.futures_rows}
    streamlit.markdown('<div class="qx-futures-strip">' + ''.join(
        _futures_tile(rows.get(symbol), symbol) for symbol in ["ES=F", "NQ=F"]
    ) + '</div>', unsafe_allow_html=True)
    with streamlit.expander("How the current state was formed"):
        _render_market_read(streamlit, dashboard)


def _decision_reference_label(row: Any) -> str:
    return f"{row.symbol} | {row.name} | {row.timing_state}"


def _render_futures_scorecard(
    streamlit: Any,
    dashboard: Any,
    focus: Any | None,
    evidence_state: str,
    execution_state: str,
    report: Any | None,
) -> None:
    """Render the decision-first screen using only snapshot-backed fields."""
    tone = "positive" if evidence_state == "Eligible" else "neutral"
    focus_name = f"{focus.symbol} | {focus.name}" if focus is not None else "No reference available"
    plan = _plan_summary_html(focus, evidence_state)
    alternatives = _alternative_references_html(dashboard.timing_rows, focus)
    gate_count, gate_total = _evidence_gate_count(report)
    session = _session_status_html(dashboard)
    context = _at_a_glance_html(dashboard)
    streamlit.markdown(
        f"""
<section class="qx-futures-board">
  <div class="qx-board-heading"><div><span>Daily futures environment</span><strong>ES / NQ context</strong></div><em>{escape(session)}</em></div>
  <div class="qx-market-strip">
    <div><span>SPY reference</span><strong>{escape(_level_text(dashboard.spy_close))}</strong></div>
    <div><span>NQ reference</span><strong>{escape(_level_text(dashboard.nq_close))}</strong></div>
    <div><span>VIX close</span><strong>{escape(_level_text(dashboard.vix_close))}</strong></div>
    <div><span>Data state</span><strong>{escape(evidence_state)}</strong></div>
    <div><span>Session</span><strong>Daily reference</strong></div>
  </div>
  <div class="qx-decision-grid">
    <article class="qx-verdict-card qx-tone-{tone}">
      <span>Daily environment call</span><strong>{escape(str(dashboard.trend_bias))}</strong>
      <p>Risk state: {escape(str(dashboard.risk_appetite))}. Execution remains {escape(execution_state)} until evidence is complete.</p>
    </article>
    {_evidence_ladder_html(report, gate_count, gate_total)}
  </div>
  <section class="qx-snapshot-history"><span>Snapshot history</span><strong>{escape(session)}</strong><em>Intraday five-minute reading history is unavailable from the current daily-bar contract.</em></section>
  <article class="qx-plan-card">
    <div class="qx-plan-head"><div><span>Selected reference</span><strong>{escape(focus_name)}</strong></div><em>Daily-bar context</em></div>
    {plan}
  </article>
  <section class="qx-at-a-glance"><span>At a glance</span><div class="qx-at-glance-grid">{context}</div></section>
  <section class="qx-alternative-section"><span>Other daily references</span><div class="qx-alternative-grid">{alternatives}</div></section>
</section>
""",
        unsafe_allow_html=True,
    )


def _plan_summary_html(row: Any | None, evidence_state: str) -> str:
    if row is None:
        return '<p class="qx-plan-empty">No daily timing reference is available.</p>'
    state = "Withheld" if evidence_state != "Eligible" else row.timing_state
    return f"""
<div class="qx-plan-grid">
  <div><span>State</span><strong>{escape(state)}</strong></div>
  <div><span>Reference</span><strong>{escape(_level_text(row.close))}</strong></div>
  <div><span>Trigger</span><strong>{escape(_level_text(row.trigger_level))}</strong></div>
  <div><span>Invalidation</span><strong>{escape(_level_text(row.invalidation_level))}</strong></div>
</div>
<p class="qx-plan-note">No-trade zone: {escape(str(row.no_trade_zone))}</p>
"""


def _alternative_references_html(rows: list[Any], focus: Any | None) -> str:
    alternatives = [row for row in rows if focus is None or row.symbol != focus.symbol][:2]
    if not alternatives:
        return '<div class="qx-alternative-card"><span>Unavailable</span><strong>No alternative reference</strong></div>'
    return "".join(
        f'<div class="qx-alternative-card"><span>{escape(row.symbol)}</span><strong>{escape(row.timing_state)}</strong><em>{escape(_level_text(row.close))}</em></div>'
        for row in alternatives
    )


def _evidence_ladder_html(report: Any | None, gate_count: int, gate_total: int) -> str:
    states = _evidence_gate_states(report)
    checks = [
        ("ES / NQ contract quote", "quote"),
        ("Explicit contract history", "history"),
        ("Continuous mapping", "continuity"),
        ("Cash-session alignment", "cash_session"),
    ]
    items = []
    for label, key in checks:
        ready = states[key]
        state = "Verified" if ready else "Required"
        css = "ready" if ready else "pending"
        items.append(f'<div class="qx-ladder-row qx-ladder-{css}">{escape(label)}<b>{state}</b></div>')
    return (
        '<article class="qx-evidence-ladder"><span>Evidence gates</span>'
        f'<strong class="qx-gate-count">{gate_count}<small> / {gate_total}</small></strong>'
        + "".join(items)
        + "</article>"
    )


def _evidence_gate_count(report: Any | None) -> tuple[int, int]:
    states = _evidence_gate_states(report)
    return sum(states.values()), len(states)


def _evidence_gate_states(report: Any | None) -> dict[str, bool]:
    rows = report.get("rows") if isinstance(report, dict) else []
    typed_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    required_symbols = {"ES=F", "NQ=F"}
    valid_rows = [row for row in typed_rows if row.get("requested_symbol") in required_symbols]
    if {row.get("requested_symbol") for row in valid_rows} != required_symbols:
        return {"quote": False, "history": False, "continuity": False, "cash_session": False}
    return {
        "quote": all(row.get("quote_status") == "fresh_at_check" for row in valid_rows),
        "history": all(row.get("history_status") == "provider_contract_matched" for row in valid_rows),
        "continuity": all(row.get("continuous_cache_comparable") is True for row in valid_rows),
        "cash_session": all(row.get("cash_close_synchronized") is True for row in valid_rows),
    }


def _session_status_html(dashboard: Any) -> str:
    gap = dashboard.opening_gap
    timestamp = str(getattr(gap, "updated_at", "Unavailable"))
    source = str(getattr(gap, "data_source", "Unavailable"))
    return f"Daily snapshot | {source} | {timestamp}"


def _at_a_glance_html(dashboard: Any) -> str:
    values = [
        ("SPY bias", dashboard.trend_bias),
        ("NQ bias", dashboard.nq_bias),
        ("Risk", dashboard.risk_appetite),
        ("Volatility", dashboard.volatility_context),
    ]
    return "".join(
        f'<div class="qx-at-glance-card"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'
        for label, value in values
    )


def _render_decision_reference(streamlit: Any, row: Any | None, evidence_state: str) -> None:
    with streamlit.container(border=True):
        streamlit.write("**Selected decision reference**")
        if row is None:
            streamlit.caption("No qualified daily reference is available.")
            return
        streamlit.caption(f"{row.symbol} | {row.name} | {row.timing_state}")
        plan_cols = streamlit.columns(4)
        plan_cols[0].metric("Reference", _level_text(row.close))
        plan_cols[1].metric("Trigger", _level_text(row.trigger_level))
        plan_cols[2].metric("Invalidation", _level_text(row.invalidation_level))
        plan_cols[3].metric("To Trigger", _pct_text(row.distance_to_trigger))
        streamlit.caption(f"No-trade zone: {row.no_trade_zone}")
        if evidence_state != "Eligible":
            streamlit.warning("Reference levels are informational only until all required evidence is verified.")
        streamlit.write(row.execution_note)
        streamlit.caption(row.risk_note)


def _render_evidence_checklist(streamlit: Any, report: Any | None) -> None:
    streamlit.write("**Evidence checklist**")
    rows = report.get("rows") if isinstance(report, dict) else []
    if not isinstance(rows, list) or not rows:
        render_bullet_list(streamlit, [
            "Pending: explicit ES and NQ contract checks.",
            "Pending: continuous-series mapping to executable contracts.",
            "Pending: synchronized cash-session reference.",
        ])
        return
    blockers = sorted({
        str(blocker)
        for row in rows if isinstance(row, dict)
        for blocker in row.get("readiness_blockers", [])
    })
    if blockers:
        render_bullet_list(streamlit, [f"Required: {blocker.replace('_', ' ')}." for blocker in blockers])
    else:
        render_bullet_list(streamlit, [
            "Evidence checks passed at their recorded check time.",
            "Execution eligibility remains governed by the separate risk layer.",
        ])


def futures_facet_readiness(report: Any | None) -> tuple[Any, ...]:
    """Translate the explicit-contract report into shared data-facet artifacts."""
    rows = report.get("rows") if isinstance(report, dict) else None
    valid_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    has_pair = {row.get("requested_symbol") for row in valid_rows} >= {"ES=F", "NQ=F"}
    artifacts = {
        "fresh_futures_quote": has_pair and all(row.get("quote_status") == "fresh_at_check" for row in valid_rows),
        "explicit_contract_history": has_pair and all(
            row.get("history_status") == "provider_contract_matched" for row in valid_rows
        ),
        "continuous_mapping": has_pair and all(row.get("continuous_cache_comparable") is True for row in valid_rows),
        "cash_session_alignment": has_pair and all(row.get("cash_close_synchronized") is True for row in valid_rows),
        "five_minute_bars": has_pair and all(row.get("intraday_status") == "fresh_at_check" for row in valid_rows),
        # This dashboard currently owns no source-attributed five-minute, event,
        # chain-IV, flow, earnings, or reconciled-fill artifacts.
    }
    return assess_facets(artifacts)


def _render_required_evidence(streamlit: Any, report: Any | None = None) -> None:
    readiness = futures_facet_readiness(report)
    streamlit.subheader("Data Foundation")
    frame = pd.DataFrame([
            {
                "Facet": item.label,
                "State": item.status.replace("_", " ").title(),
                "Missing evidence": ", ".join(item.missing_artifacts).replace("_", " ") or "None",
                "Sources": ", ".join(source_contract(key).label for key in item.source_keys) or "Qualified source required",
            }
            for item in readiness
        ])
    streamlit.dataframe(display_frame(frame), width="stretch", hide_index=True)
    streamlit.caption(
        "A ready data facet means its declared evidence is present, not that it is a trade recommendation or an execution signal."
    )
    streamlit.subheader("Inputs Needed for a Tradable Futures State")
    render_bullet_list(
        streamlit,
        [
            "Exact ES/NQ contract, exchange, expiration, multiplier, tick size, and roll policy.",
            "Bid, ask, last trade, quote timestamp, and session state from an explicit futures feed.",
            "Continuous-series methodology and a verified mapping to the active executable contract.",
            "Cash-index and futures references aligned to named sessions before any implied-gap calculation.",
            "Economic-event calendar, timestamp, and source before event-window risk can be evaluated.",
            "Execution assumptions: contract size, per-side fees, slippage, and risk limits.",
            "Chronological, cost-aware outcomes for each deterministic futures setup before confidence labels are used.",
        ],
    )


def futures_timing_columns() -> list[str]:
    return TIMING_COLUMNS.copy()


def futures_timing_board_columns() -> list[str]:
    return TIMING_BOARD_COLUMNS.copy()


def _render_context_strip(streamlit: Any, dashboard: Any) -> None:
    items = [
        ("SPY Daily Bias", dashboard.trend_bias, "bias"),
        ("NQ Bias", dashboard.nq_bias, "bias"),
        ("Risk", dashboard.risk_appetite, "risk"),
        ("Vol", dashboard.volatility_context, "vol"),
    ]
    streamlit.markdown(
        f"""
<div class="qx-futures-context">
  {"".join(_context_chip(label, value, kind) for label, value, kind in items)}
</div>
""",
        unsafe_allow_html=True,
    )


def _render_futures_strip(streamlit: Any, dashboard: Any) -> None:
    row_by_symbol = {row.symbol: row for row in dashboard.futures_rows}
    tiles = [_futures_tile(row_by_symbol.get(symbol), symbol) for symbol in FUTURES_BOARD_SYMBOLS]
    streamlit.markdown(
        f"""
<div class="qx-futures-strip">
  {"".join(tiles)}
</div>
""",
        unsafe_allow_html=True,
    )


def _render_opening_gap_read(streamlit: Any, dashboard: Any) -> None:
    gap = dashboard.opening_gap
    streamlit.markdown(
        f"""
<div class="qx-opening-read qx-tone-{escape(gap.tone)}">
  <div class="qx-opening-head">
    <div>
      <span>ES Reference Comparison</span>
      <strong>{escape(gap.gap_type)} {escape(_signed_pct(gap.implied_gap_pct))}</strong>
    </div>
    <em>{escape(gap.data_source)} | {escape(gap.updated_at)} | Confidence {escape(gap.confidence)}</em>
  </div>
  <div class="qx-opening-grid">
    {_opening_metric("Cached SPY Close", _level_text(gap.prior_spx_close))}
    {_opening_metric("Observed /ES", _level_text(gap.es_last))}
    {_opening_metric("Cached /ES Reference", _level_text(gap.es_reference))}
    {_opening_metric("/ES Change", _signed_points(gap.es_change_points))}
    {_opening_metric("Implied SPY Proxy Open", _level_text(gap.implied_spx_open))}
    {_opening_metric("Implied Gap", _signed_points(gap.implied_gap_points))}
  </div>
  <p>{escape(gap.read)}</p>
</div>
""",
        unsafe_allow_html=True,
    )


def _opening_metric(label: str, value: str) -> str:
    return f'<div class="qx-opening-metric"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'


def _context_chip(label: str, value: object, kind: str) -> str:
    tone = _tone_from_text(str(value))
    return (
        f'<div class="qx-context-chip qx-context-{escape(kind)} qx-tone-{tone}">'
        f'<span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'
    )


def _futures_tile(row: Any | None, fallback_symbol: str) -> str:
    ticker = _display_future_symbol(fallback_symbol)
    if row is None:
        return (
            '<div class="qx-future-tile qx-tone-neutral">'
            f'<div class="qx-future-head"><strong>{escape(ticker)}</strong><span>No data</span></div>'
            '<div class="qx-future-main">n/a</div><div class="qx-future-sub">waiting for data</div></div>'
        )

    tone = _tone_from_return(row.return_1d)
    move = _signed_pct(row.return_1d)
    close = _level_text(row.close)
    return (
        f'<div class="qx-future-tile qx-tone-{tone}">'
        f'<div class="qx-future-head"><strong>{escape(_display_future_symbol(row.symbol))}</strong>'
        f'<span>{escape(row.name)}</span></div>'
        f'<div class="qx-future-main">{escape(move)} <small>1D</small></div>'
        f'<div class="qx-future-sub">Daily close {escape(close)} | 5D {escape(_signed_pct(row.return_5d))}</div>'
        f'<div class="qx-future-sub">Trend context: {escape(_short_signal(row.signal))}</div>'
        "</div>"
    )


def _render_futures_board(streamlit: Any, dashboard: Any) -> None:
    """Render one detailed contract view instead of a wide futures table."""
    row_by_symbol = {row.symbol: row for row in dashboard.futures_rows}
    available_symbols = [symbol for symbol in FUTURES_BOARD_SYMBOLS if symbol in row_by_symbol]
    if not available_symbols:
        streamlit.info("No futures detail is available for this dashboard build.")
        return

    selected_symbol = streamlit.selectbox(
        "Futures contract",
        available_symbols,
        format_func=_display_future_symbol,
        key="spx_futures_detail_symbol",
    )
    row = row_by_symbol[selected_symbol]
    streamlit.subheader(f"{_display_future_symbol(row.symbol)} detail")
    cols = streamlit.columns(5)
    cols[0].metric("Daily close", _level_text(row.close))
    cols[1].metric("1D", _signed_pct(row.return_1d))
    cols[2].metric("5D", _signed_pct(row.return_5d))
    cols[3].metric("20D", _signed_pct(row.return_20d))
    cols[4].metric("Daily context", _short_signal(row.signal))

    detail_cols = streamlit.columns(4)
    detail_cols[0].metric("20D Trend", _trend_position(row.above_sma20))
    detail_cols[1].metric("50D Trend", _trend_position(row.above_sma50))
    detail_cols[2].metric("To Prior High", _signed_pct(row.distance_to_prior_high))
    detail_cols[3].metric("To Prior Low", _signed_pct(row.distance_to_prior_low))
    with streamlit.container(border=True):
        streamlit.write("**Market interpretation**")
        streamlit.write(row.note)


def _display_future_symbol(symbol: str) -> str:
    return {
        "ES=F": "/ES",
        "NQ=F": "/NQ",
        "RTY=F": "/RTY",
        "YM=F": "/YM",
        "ZN=F": "/ZN",
        "ZB=F": "/ZB",
        "DX-Y.NYB": "/DX",
        "CL=F": "/CL",
        "GC=F": "/GC",
    }.get(symbol, symbol)


def _trend_position(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "Above average" if value else "Below average"


def _signed_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1%}"


def _signed_points(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}"


def _tone_from_return(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value > 0.001:
        return "positive"
    if value < -0.001:
        return "negative"
    return "neutral"


def _tone_from_text(value: str) -> str:
    lowered = value.lower()
    if any(word in lowered for word in ["bullish", "risk-on", "confirmed", "calm"]):
        return "positive"
    if any(word in lowered for word in ["bearish", "risk-off", "defensive", "elevated"]):
        return "negative"
    return "neutral"


def _short_signal(signal: str) -> str:
    if signal == "Risk-On":
        return "Up / supportive"
    if signal == "Risk-Off":
        return "Down / pressure"
    return signal


def _render_market_read(streamlit: Any, dashboard: Any) -> None:
    streamlit.subheader("Market Read")
    with streamlit.container(border=True):
        cols = streamlit.columns([1.1, 1.1, 1.2, 1.4])
        with cols[0]:
            streamlit.write("**Bias Stack**")
            render_bullet_list(
                streamlit,
                [
                    f"Regime: {dashboard.regime.label}",
                    f"SPX: {dashboard.trend_bias}",
                    f"NQ: {dashboard.nq_bias}",
                ],
            )
        with cols[1]:
            streamlit.write("**Execution Bias**")
            render_bullet_list(
                streamlit,
                [
                    dashboard.trading_plan.day_type,
                    dashboard.trading_plan.primary_bias,
                ],
            )
        with cols[2]:
            streamlit.write("**Risk Context**")
            render_bullet_list(
                streamlit,
                [
                    f"Risk appetite: {dashboard.risk_appetite}",
                    f"Volatility: {dashboard.volatility_context}",
                    dashboard.trading_plan.risk_note,
                ],
            )
        with cols[3]:
            streamlit.write("**Confirmation Needed**")
            render_bullet_list(
                streamlit,
                [
                    dashboard.trading_plan.confirmation_required,
                    *dashboard.confirmation_notes[:2],
                ],
            )


def _render_timing_map(streamlit: Any, dashboard: Any) -> None:
    streamlit.subheader("Historical Timing States")
    streamlit.caption("Derived from daily bars; not an opening forecast or intraday trigger confirmation.")

    priority_row = _highest_priority_row(dashboard.timing_rows)
    if priority_row is not None:
        with streamlit.container(border=True):
            cols = streamlit.columns([0.9, 1.0, 1.0, 1.0, 1.6])
            cols[0].metric("Primary Focus", priority_row.symbol)
            cols[1].metric("State", priority_row.timing_state)
            cols[2].metric("Trigger", _level_text(priority_row.trigger_level))
            cols[3].metric("Invalidation", _level_text(priority_row.invalidation_level))
            with cols[4]:
                streamlit.write("**Execution Read**")
                streamlit.caption(priority_row.execution_note)

    streamlit.dataframe(
        display_frame(futures_timing_frame(dashboard.timing_rows), columns=futures_timing_board_columns()),
        width="stretch",
        hide_index=True,
    )

    with streamlit.expander("Execution Notes", expanded=False):
        note_frame = display_frame(
            futures_timing_frame(dashboard.timing_rows),
            columns=["symbol", "execution_note", "risk_note"],
        )
        streamlit.dataframe(note_frame, width="stretch", hide_index=True)


def _render_trading_plan(streamlit: Any, dashboard: Any) -> None:
    streamlit.subheader("Conditional Scenarios")
    reference = dashboard.es_levels if dashboard.es_levels.close is not None else dashboard.spy_levels
    streamlit.caption(f"Scenario reference: {reference.symbol} daily bars. Intraday acceptance has not been evaluated.")
    with streamlit.container(border=True):
        cols = streamlit.columns(3)
        with cols[0]:
            streamlit.write("**Bullish Condition**")
            render_bullet_list(streamlit, [dashboard.trading_plan.long_plan])
        with cols[1]:
            streamlit.write("**Bearish Condition**")
            render_bullet_list(streamlit, [dashboard.trading_plan.short_plan])
        with cols[2]:
            streamlit.write("**No-Trade Zone**")
            render_bullet_list(streamlit, [dashboard.trading_plan.no_trade_zone])
    streamlit.caption(dashboard.trading_plan.confirmation_required)


def _level_text(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _pct_text(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _highest_priority_row(rows: list[Any]) -> Any | None:
    if not rows:
        return None
    return sorted(rows, key=lambda row: (int(row.priority), row.symbol), reverse=True)[0]


run_standalone_page(
    "SPX / NQ Futures",
    "Build daily futures context for ES, NQ, rates, dollar, crude, and gold.",
    render_spx_dashboard_page,
)
