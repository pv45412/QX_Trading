from typing import Any
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go  # type: ignore[import-untyped]

from qx.data.cache import CachedMarketDataProvider, _cache_symbol, _read_cached_bars
from qx.data.factory import build_fallback_market_data_provider
from qx.models.market import BarDataRequest
from qx.models.position_advisor import PositionInput, evaluate_position, PositionResearchReport
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame
from qx.ui.workspace_context import read_context, render_context_links, sync_context


HISTORY_PERIOD_OPTIONS = ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
HISTORY_TIMEFRAME_OPTIONS = ["Daily", "Weekly", "Monthly", "Yearly"]
POSITION_TYPE_OPTIONS = ["Long Shares", "Short Shares", "Long Call", "Long Put", "Bull Call Spread", "Bear Put Spread"]


def render_ticker_history_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    streamlit.subheader("Instrument Review & Position Advisor")
    context = read_context(getattr(streamlit, "query_params", {}))

    with streamlit.container(border=True):
        controls = streamlit.columns([1.2, 1.0, 1.0, 1.0, 1.0])
        symbol = controls[0].text_input("Ticker", value=context.get("symbol", context.get("etf", "VST")), key="ticker_history_symbol").strip().upper()
        period = controls[1].selectbox("History", HISTORY_PERIOD_OPTIONS, index=HISTORY_PERIOD_OPTIONS.index(context["period"]) if context.get("period") in HISTORY_PERIOD_OPTIONS else 3, key="ticker_history_period")
        timeframe = controls[2].selectbox(
            "Chart timeframe",
            HISTORY_TIMEFRAME_OPTIONS,
            index=0,
            key="ticker_history_timeframe",
        )
        data_source = controls[3].selectbox(
            "Market Data",
            MARKET_DATA_PROVIDER_OPTIONS,
            index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
            key="ticker_history_data_source",
        )
        refresh = controls[4].checkbox(
            "Refresh live data",
            value=False,
            key="ticker_history_refresh",
            help="Bypass the local bar cache for this request.",
        )
        build = streamlit.button("Load Ticker History", type="primary", width="stretch")

    if "symbol" not in read_context({"symbol": symbol}):
        streamlit.warning("Enter a valid ticker symbol.")
        return
    sync_context(streamlit, symbol=symbol, period=str(period))
    render_context_links(streamlit, symbol)
    request_key = (symbol, str(period), str(data_source), context.get("as_of"))
    saved = streamlit.session_state.get("ticker_history_loaded")
    if not build and (saved is None or saved[0] != request_key):
        cache_path = Path("data/cache/bars") / f"{_cache_symbol(symbol)}_{period}.csv"
        if not cache_path.is_file():
            streamlit.info("No saved history matches this ticker and period. Click 'Load Ticker History' to fetch market data.")
            return
        try:
            saved = (request_key, _read_cached_bars(cache_path))
        except (ValueError, OSError, IndexError, KeyError):
            streamlit.error("The saved price history could not be read. Use an explicit live refresh to repair it.")
            return
        streamlit.session_state["ticker_history_loaded"] = saved
    if not symbol:
        streamlit.warning("Enter a ticker symbol first.")
        return

    if build:
        provider = CachedMarketDataProvider(
            build_fallback_market_data_provider(str(data_source)), refresh=bool(refresh),
        )
        with streamlit.spinner(f"Loading {symbol} history..."):
            try:
                bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=str(period)))
            except Exception as exc:
                streamlit.error(f"Could not load {symbol} history: {exc}")
                return
        streamlit.session_state["ticker_history_loaded"] = (request_key, bars)
    else:
        bars = saved[1]
    if context.get("as_of"):
        cutoff = pd.Timestamp(context["as_of"]).date()
        mask = pd.Series([stamp.date() <= cutoff for stamp in pd.DatetimeIndex(bars.index)], index=bars.index)
        bars = bars.loc[mask].copy()
        streamlit.caption(f"Price history cutoff: {context['as_of']}. Displayed from local market cache.")
    if bars.empty:
        streamlit.info("No price observations are available for this selection.")
        return
    history = build_history_frame(bars, timeframe=str(timeframe))

    streamlit.caption(
        f"Loaded {len(bars):,} daily bars for {symbol} through {bars.index[-1].date()}. "
        f"Source: {bars.attrs.get('provenance', {}).get('actual_source', 'unknown')}. Requested provider: {data_source}."
    )
    _render_summary(streamlit, history)

    current_last = float(history["close"].iloc[-1])

    # --- POSITION RESEARCH & ACTION ADVISOR FORM ---
    streamlit.subheader("🎯 Position Research & Action Advisor")
    streamlit.markdown(
        "Evaluate an existing open position (shares, call/put options, vertical spreads) using automated quantitative research, "
        "moving average trends, momentum, and risk diagnostics to get an explicit **HOLD**, **TRIM**, **CLOSE**, or **ROLL** recommendation."
    )

    with streamlit.container(border=True):
        st_cols = streamlit.columns([1.2, 1.0, 1.0, 1.0, 1.0])
        pos_type = st_cols[0].selectbox("Position Type", POSITION_TYPE_OPTIONS, index=0, key="pos_adv_type")
        default_entry = round(current_last * 0.95, 2)
        entry_p = st_cols[1].number_input("Entry Price ($)", value=default_entry, step=0.5, key="pos_adv_entry")
        qty = st_cols[2].number_input("Quantity", value=100.0, step=10.0, key="pos_adv_qty")
        default_target = round(current_last * 1.15, 2)
        target_p = st_cols[3].number_input("Target Price ($)", value=default_target, step=1.0, key="pos_adv_target")
        default_stop = round(current_last * 0.88, 2)
        stop_p = st_cols[4].number_input("Stop Loss ($)", value=default_stop, step=1.0, key="pos_adv_stop")

        eval_btn = streamlit.button("⚡ Research & Evaluate Position", type="primary", width="stretch")

    pos_input = PositionInput(
        symbol=symbol,
        position_type=str(pos_type),
        entry_price=float(entry_p),
        quantity=float(qty),
        target_price=float(target_p) if target_p > 0 else None,
        stop_loss=float(stop_p) if stop_p > 0 else None,
    )

    report = evaluate_position(pos_input, history)

    _render_position_verdict_report(streamlit, report)
    _render_chart(streamlit, history, symbol=symbol, timeframe=str(timeframe), report=report)

    streamlit.subheader("Full History")
    export = history.reset_index().rename(columns={"index": "date"})
    streamlit.download_button(
        "Export Full History CSV",
        export.to_csv(index=False),
        file_name=f"{symbol.lower()}_{str(period)}_{str(timeframe).lower()}.csv",
        mime="text/csv",
    )
    with streamlit.expander("Price history rows"):
        streamlit.dataframe(display_frame(export, columns=list(export.columns), max_rows=5000), width="stretch", hide_index=True)


def _render_position_verdict_report(streamlit: Any, report: PositionResearchReport) -> None:
    verdict = report.action_verdict
    color_map = {
        "HOLD": ("#00c853", "#042c11", "🟢"),
        "TRIM / TAKE PROFIT": ("#ffd600", "#302600", "🟡"),
        "CLOSE / EXIT": ("#ff3d00", "#310c08", "🔴"),
        "ROLL / ADJUST": ("#29b6f6", "#072436", "🔵"),
    }
    accent_color, bg_color, emoji = color_map.get(verdict, ("#29b6f6", "#072436", "ℹ️"))

    streamlit.markdown(
        f"""
        <div style="background-color: {bg_color}; border: 2px solid {accent_color}; border-radius: 10px; padding: 18px 24px; margin: 16px 0 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: {accent_color};">Automated Position Recommendation</span>
                    <h2 style="margin: 4px 0 0 0; color: #ffffff; font-size: 32px; font-weight: 800;">
                        {emoji} {verdict} <span style="font-size: 20px; font-weight: 500; color: #b5bfcd;">({report.confidence_score:.0%} Confidence)</span>
                    </h2>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 13px; color: #8b949e;">Unrealized P&L</div>
                    <div style="font-size: 24px; font-weight: 700; color: {'#00c853' if report.unrealized_pnl >= 0 else '#ff3d00'};">
                        {'+' if report.unrealized_pnl >= 0 else ''}\${report.unrealized_pnl:,.2f} ({'+' if report.unrealized_pnl_pct >= 0 else ''}{report.unrealized_pnl_pct:.1%})
                    </div>
                </div>
            </div>
            <p style="margin: 12px 0 0 0; font-size: 15px; color: #e6e9ee; line-height: 1.5;">
                {report.verdict_summary}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 4-Card Diagnostics Grid
    grid = streamlit.columns(4)
    with grid[0]:
        streamlit.markdown(
            f"""<div style="background:#161b22; padding:12px; border-radius:8px; border:1px solid #30363d;">
                <div style="color:#8b949e; font-size:12px;">ENTRY & P&L DIAGNOSTICS</div>
                <div style="font-size:18px; font-weight:600; color:#fff; margin-top:4px;">\${report.entry_price:.2f} <span style="font-size:12px; color:#8b949e;">Entry</span></div>
                <div style="font-size:13px; margin-top:6px; color:#c9d1d9;">Current Price: <b>\${report.current_price:.2f}</b></div>
                <div style="font-size:13px; color:#c9d1d9;">Open P&L: <b style="color:{'#00c853' if report.unrealized_pnl >= 0 else '#ff3d00'}">{report.unrealized_pnl_pct:.1%}</b></div>
            </div>""",
            unsafe_allow_html=True,
        )
    with grid[1]:
        rr = report.risk_metrics.get("risk_reward_ratio", 1.5)
        dist_stop = report.risk_metrics.get("distance_to_stop_pct", 0.0)
        streamlit.markdown(
            f"""<div style="background:#161b22; padding:12px; border-radius:8px; border:1px solid #30363d;">
                <div style="color:#8b949e; font-size:12px;">RISK : REWARD PARAMETERS</div>
                <div style="font-size:18px; font-weight:600; color:#fff; margin-top:4px;">{rr:.2f}:1 <span style="font-size:12px; color:#8b949e;">R:R Ratio</span></div>
                <div style="font-size:13px; margin-top:6px; color:#c9d1d9;">Stop Loss: <b>\${report.adjusted_stop_loss:.2f}</b> ({dist_stop:.1%})</div>
                <div style="font-size:13px; color:#c9d1d9;">Target Price: <b>\${report.adjusted_target_price:.2f}</b></div>
            </div>""",
            unsafe_allow_html=True,
        )
    with grid[2]:
        rsi = report.technical_metrics.get("rsi_14", 50.0)
        sma20 = report.technical_metrics.get("sma_20", 0.0)
        streamlit.markdown(
            f"""<div style="background:#161b22; padding:12px; border-radius:8px; border:1px solid #30363d;">
                <div style="color:#8b949e; font-size:12px;">TECHNICAL TREND HEALTH</div>
                <div style="font-size:18px; font-weight:600; color:#fff; margin-top:4px;">RSI: {rsi:.1f}</div>
                <div style="font-size:13px; margin-top:6px; color:#c9d1d9;">20-Day SMA: <b>\${sma20:.2f}</b></div>
                <div style="font-size:13px; color:#c9d1d9;">50-Day SMA: <b>\${report.technical_metrics.get('sma_50', 0.0):.2f}</b></div>
            </div>""",
            unsafe_allow_html=True,
        )
    with grid[3]:
        atr = report.technical_metrics.get("atr_14", 0.0)
        pct_high = report.technical_metrics.get("pct_from_high", 0.0)
        streamlit.markdown(
            f"""<div style="background:#161b22; padding:12px; border-radius:8px; border:1px solid #30363d;">
                <div style="color:#8b949e; font-size:12px;">VOLATILITY & RANGE</div>
                <div style="font-size:18px; font-weight:600; color:#fff; margin-top:4px;">ATR: \${atr:.2f}</div>
                <div style="font-size:13px; margin-top:6px; color:#c9d1d9;">52w High: <b>\${report.technical_metrics.get('high_52w', 0.0):.2f}</b></div>
                <div style="font-size:13px; color:#c9d1d9;">Off Peak: <b>{pct_high:.1%}</b></div>
            </div>""",
            unsafe_allow_html=True,
        )

    # Factors List
    f_cols = streamlit.columns(2)
    with f_cols[0]:
        streamlit.markdown("##### 🟢 Bullish / Supporting Factors")
        if report.positive_factors:
            for factor in report.positive_factors:
                streamlit.markdown(f"- ✅ {factor}")
        else:
            streamlit.caption("No strong positive technical drivers found.")
    with f_cols[1]:
        streamlit.markdown("##### 🔴 Risk / Bearish Factors")
        if report.negative_factors:
            for factor in report.negative_factors:
                streamlit.markdown(f"- ⚠️ {factor}")
        else:
            streamlit.caption("No critical risk flags detected.")


def build_history_frame(bars: pd.DataFrame, *, timeframe: str = "Daily") -> pd.DataFrame:
    """Return normalized OHLCV history with returns and drawdown diagnostics."""
    frame = bars[["open", "high", "low", "close", "volume"]].copy().sort_index()
    rule = {"Weekly": "W-FRI", "Monthly": "ME", "Yearly": "YE"}.get(timeframe)
    if rule:
        frame = (
            frame.resample(rule)
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .dropna(subset=["close"])
        )
    frame["return"] = frame["close"].pct_change()
    frame["drawdown"] = frame["close"] / frame["close"].cummax() - 1.0
    return frame


def history_summary(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
        return {"bars": 0, "last": 0.0, "period_return": 0.0, "high": 0.0, "low": 0.0, "max_drawdown": 0.0}
    first_close = float(frame["close"].iloc[0])
    last_close = float(frame["close"].iloc[-1])
    return {
        "bars": int(len(frame)),
        "last": last_close,
        "period_return": last_close / first_close - 1.0 if first_close else 0.0,
        "high": float(frame["high"].max()),
        "low": float(frame["low"].min()),
        "max_drawdown": float(frame["drawdown"].min()),
    }


def _render_summary(streamlit: Any, frame: pd.DataFrame) -> None:
    summary = history_summary(frame)
    cols = streamlit.columns(6)
    cols[0].metric("Bars", summary["bars"])
    cols[1].metric("Last", f"{summary['last']:.2f}")
    cols[2].metric("Period Return", f"{summary['period_return']:.1%}")
    cols[3].metric("Period High", f"{summary['high']:.2f}")
    cols[4].metric("Period Low", f"{summary['low']:.2f}")
    cols[5].metric("Max Drawdown", f"{summary['max_drawdown']:.1%}")


def _render_chart(streamlit: Any, frame: pd.DataFrame, *, symbol: str, timeframe: str, report: PositionResearchReport | None = None) -> None:
    chart = go.Figure()
    chart.add_trace(
        go.Candlestick(
            x=frame.index,
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name=symbol,
        )
    )

    # Add SMA overlays
    if len(frame) >= 20:
        sma20 = frame["close"].rolling(20).mean()
        chart.add_trace(go.Scatter(x=frame.index, y=sma20, mode="lines", name="SMA 20", line=dict(color="#ffa726", width=1.5)))
    if len(frame) >= 50:
        sma50 = frame["close"].rolling(50).mean()
        chart.add_trace(go.Scatter(x=frame.index, y=sma50, mode="lines", name="SMA 50", line=dict(color="#ab47bc", width=1.5)))

    # Add Position Target / Stop / Entry price lines if report provided
    if report:
        chart.add_hline(y=report.entry_price, line_dash="dash", line_color="#3478ff", annotation_text=f"Entry (${report.entry_price:.2f})")
        if report.adjusted_stop_loss > 0:
            chart.add_hline(y=report.adjusted_stop_loss, line_dash="dash", line_color="#ff4b4b", annotation_text=f"Stop (${report.adjusted_stop_loss:.2f})")
        if report.adjusted_target_price > 0:
            chart.add_hline(y=report.adjusted_target_price, line_dash="dash", line_color="#00c853", annotation_text=f"Target (${report.adjusted_target_price:.2f})")

    chart.update_layout(
        title=f"{symbol} {timeframe} Price History & Position Overlays",
        height=560,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font_color="#e6e9ee",
        xaxis_rangeslider_visible=False,
        yaxis_title="Price",
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
    )
    streamlit.plotly_chart(chart, width="stretch", config={"displaylogo": False})


run_standalone_page(
    "Ticker History",
    "Review complete OHLCV history, price structure, and run automated Hold vs Close research on open positions.",
    render_ticker_history_page,
)
