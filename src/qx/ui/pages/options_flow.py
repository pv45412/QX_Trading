from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go  # type: ignore[import-untyped]

from qx.data.factory import build_fallback_market_data_provider
from qx.models.market import BarDataRequest
from qx.options_flow.engine import analyze_option_flow, parse_flow_csv, suggested_contracts_frame, trades_frame
from qx.options_flow.models import MarketRegimeContext, OptionFlowAnalysis, UnderlyingContext
from qx.storage.options_flow import SQLiteOptionFlowRepository
from qx.ui.app_shell import render_bullet_list, render_section_header, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame


DATABASE_PATH = Path("data/options_flow.db")

CSV_SCHEMA_SAMPLE = """ticker,option_symbol,expiration,strike,call_put,price,bid,ask,size,premium,volume,open_interest,iv,delta,gamma,trade_kind,condition
AAPL,AAPL260619C00200000,2026-06-19,200,CALL,4.20,4.05,4.25,200,84000,1400,18000,0.28,0.42,0.03,sweep,regular
AAPL,AAPL260619P00190000,2026-06-19,190,PUT,2.10,2.00,2.20,75,15750,900,16000,0.31,-0.35,0.03,block,regular
"""


def render_options_flow_page(streamlit: Any) -> None:
    render_section_header(
        streamlit,
        "QX Options Flow Direction Engine",
        "Probability-style call/put flow scoring with price confirmation, IV quality, liquidity context, and risk filters.",
    )
    streamlit.caption(
        "This engine is a decision filter, not a profit predictor. It recommends no-trade when flow, price, IV, or regime are unclear."
    )

    with streamlit.container(border=True):
        cols = streamlit.columns([1.1, 1.2, 1.1, 1.1, 1.1])
        ticker = cols[0].text_input("Ticker", value="SPY").strip().upper()
        source = cols[1].selectbox(
            "Market data",
            MARKET_DATA_PROVIDER_OPTIONS,
            index=provider_index(MARKET_DATA_PROVIDER_OPTIONS, "schwab"),
        )
        history = cols[2].selectbox("History", ["3mo", "6mo", "1y"], index=1)
        flow_source = cols[3].selectbox("Flow input", ["CSV upload", "Sample CSV"], index=0)
        event_risk = cols[4].checkbox("Event / IV crush risk", value=False)

        regime_cols = streamlit.columns(5)
        spy_trend = regime_cols[0].selectbox("SPY trend", ["bullish", "neutral", "bearish"], index=1)
        qqq_trend = regime_cols[1].selectbox("QQQ trend", ["bullish", "neutral", "bearish"], index=1)
        vix_trend = regime_cols[2].selectbox("VIX trend", ["falling", "flat", "rising"], index=1)
        sector_strength = regime_cols[3].selectbox("Sector strength", ["strong", "neutral", "weak"], index=1)
        market_chop = regime_cols[4].checkbox("Market chop", value=False)

        uploaded = None
        if flow_source == "CSV upload":
            uploaded = streamlit.file_uploader("Upload options-flow CSV", type=["csv"])
        with streamlit.expander("CSV fields accepted"):
            streamlit.write(
                "Ticker, option symbol, expiration, strike, call/put, trade price, bid, ask, size, "
                "premium, volume, open interest, implied volatility, delta, gamma, condition, sweep/block/split."
            )
            streamlit.download_button(
                "Download CSV template",
                CSV_SCHEMA_SAMPLE,
                file_name="qx_options_flow_sample.csv",
                mime="text/csv",
            )

        run = streamlit.button("Analyze Flow", type="primary", use_container_width=True)

    if run:
        if flow_source == "CSV upload" and uploaded is None:
            streamlit.warning("Select a CSV before running analysis.")
            return
        try:
            bars = _load_bars(ticker, str(source), history)
            underlying = _underlying_context(ticker, bars)
            frame = _load_flow_frame(flow_source, uploaded, ticker=ticker, current_price=underlying.current_price)
            trades = parse_flow_csv(frame, default_ticker=ticker)
            trades, skipped = _filter_trades_for_ticker(trades, ticker)
            if skipped:
                streamlit.warning(f"Ignored {skipped} options-flow row(s) that did not match {ticker}.")
            if not trades:
                streamlit.warning("No valid options-flow rows found for the selected ticker. Upload a matching CSV or use generated sample data.")
                return
            regime = MarketRegimeContext(
                spy_trend=spy_trend,
                qqq_trend=qqq_trend,
                vix_trend=vix_trend,
                sector_strength=sector_strength,
                macro_event_risk=event_risk,
                market_chop=market_chop,
            )
            analysis = analyze_option_flow(
                trades,
                underlying=underlying,
                regime=regime,
                event_risk=event_risk,
            )
            signal_id = (
                SQLiteOptionFlowRepository(DATABASE_PATH).save_analysis(analysis)
                if flow_source == "CSV upload" else None
            )
            streamlit.session_state["options_flow_analysis"] = analysis
            streamlit.session_state["options_flow_bars"] = bars
            streamlit.session_state["options_flow_signal_id"] = signal_id
            streamlit.session_state["options_flow_is_sample"] = flow_source == "Sample CSV"
        except Exception as exc:
            streamlit.error(f"Could not analyze options flow: {exc}")
            return

    analysis = streamlit.session_state.get("options_flow_analysis")
    if streamlit.session_state.get("options_flow_is_sample"):
        streamlit.warning("Sample data: simulated flow, not live trades. This analysis is not saved.")
    bars = streamlit.session_state.get("options_flow_bars")
    if not isinstance(analysis, OptionFlowAnalysis) or not isinstance(bars, pd.DataFrame):
        streamlit.info("Enter a ticker and analyze uploaded flow, or use the sample CSV to validate the engine.")
        return

    _render_summary(streamlit, analysis)
    _render_tabs(streamlit, analysis, bars)


def _load_flow_frame(flow_source: str, uploaded: Any, *, ticker: str, current_price: float) -> pd.DataFrame:
    if flow_source == "Sample CSV":
        return _sample_flow_frame(ticker, current_price)
    if uploaded is None:
        return pd.DataFrame()
    return pd.read_csv(uploaded)


def _sample_flow_frame(ticker: str, current_price: float) -> pd.DataFrame:
    clean_ticker = ticker.strip().upper()
    rounded_price = max(current_price, 1.0)
    strike_step = _strike_step(rounded_price)
    call_strike = _round_to_step(rounded_price * 1.01, strike_step)
    put_strike = _round_to_step(rounded_price * 0.99, strike_step)
    later_call_strike = _round_to_step(rounded_price * 1.02, strike_step)
    call_price = max(rounded_price * 0.007, 0.5)
    put_price = max(rounded_price * 0.005, 0.35)
    today = datetime.now(UTC).date()
    exp_1 = today + timedelta(days=12)
    exp_2 = today + timedelta(days=19)
    symbol_stub = clean_ticker.replace("/", "").replace("=", "")
    return pd.DataFrame(
        [
            {
                "ticker": clean_ticker,
                "option_symbol": f"{symbol_stub}{exp_1:%y%m%d}C{int(call_strike * 1000):08d}",
                "expiration": exp_1.isoformat(),
                "strike": call_strike,
                "call_put": "CALL",
                "price": round(call_price, 2),
                "bid": round(call_price * 0.97, 2),
                "ask": round(call_price * 1.01, 2),
                "size": 200,
                "premium": round(call_price * 200 * 100, 0),
                "volume": 1400,
                "open_interest": 18000,
                "iv": 0.18,
                "delta": 0.42,
                "gamma": 0.03,
                "trade_kind": "sweep",
                "condition": "generated sample",
            },
            {
                "ticker": clean_ticker,
                "option_symbol": f"{symbol_stub}{exp_1:%y%m%d}C{int(call_strike * 1000):08d}",
                "expiration": exp_1.isoformat(),
                "strike": call_strike,
                "call_put": "CALL",
                "price": round(call_price * 1.02, 2),
                "bid": round(call_price * 0.99, 2),
                "ask": round(call_price * 1.03, 2),
                "size": 150,
                "premium": round(call_price * 1.02 * 150 * 100, 0),
                "volume": 1550,
                "open_interest": 18000,
                "iv": 0.18,
                "delta": 0.43,
                "gamma": 0.03,
                "trade_kind": "sweep",
                "condition": "generated sample",
            },
            {
                "ticker": clean_ticker,
                "option_symbol": f"{symbol_stub}{exp_1:%y%m%d}P{int(put_strike * 1000):08d}",
                "expiration": exp_1.isoformat(),
                "strike": put_strike,
                "call_put": "PUT",
                "price": round(put_price, 2),
                "bid": round(put_price * 0.96, 2),
                "ask": round(put_price * 1.03, 2),
                "size": 75,
                "premium": round(put_price * 75 * 100, 0),
                "volume": 900,
                "open_interest": 16000,
                "iv": 0.19,
                "delta": -0.35,
                "gamma": 0.03,
                "trade_kind": "block",
                "condition": "generated sample",
            },
            {
                "ticker": clean_ticker,
                "option_symbol": f"{symbol_stub}{exp_2:%y%m%d}C{int(later_call_strike * 1000):08d}",
                "expiration": exp_2.isoformat(),
                "strike": later_call_strike,
                "call_put": "CALL",
                "price": round(call_price * 1.18, 2),
                "bid": round(call_price * 1.14, 2),
                "ask": round(call_price * 1.20, 2),
                "size": 120,
                "premium": round(call_price * 1.18 * 120 * 100, 0),
                "volume": 700,
                "open_interest": 8500,
                "iv": 0.22,
                "delta": 0.39,
                "gamma": 0.02,
                "trade_kind": "block",
                "condition": "generated sample",
            },
        ]
    )


def _filter_trades_for_ticker(trades: list[Any], ticker: str) -> tuple[list[Any], int]:
    selected = ticker.strip().upper()
    filtered = [trade for trade in trades if trade.ticker == selected]
    return filtered, len(trades) - len(filtered)


def _strike_step(price: float) -> float:
    if price >= 1000:
        return 25.0
    if price >= 250:
        return 5.0
    if price >= 50:
        return 2.5
    return 1.0


def _round_to_step(value: float, step: float) -> float:
    return round(round(value / step) * step, 2)


def _load_bars(ticker: str, source: str, history: str) -> pd.DataFrame:
    provider = build_fallback_market_data_provider(source)
    bars = provider.get_daily_bars(BarDataRequest(symbol=ticker, period=history))
    if bars.empty:
        raise ValueError(f"No underlying price data returned for {ticker}.")
    return bars.sort_index()


def _underlying_context(ticker: str, bars: pd.DataFrame) -> UnderlyingContext:
    last = bars.iloc[-1]
    previous = bars.iloc[-2] if len(bars) > 1 else last
    tail = bars.tail(20)
    volume_sum = float(tail["volume"].sum()) if "volume" in tail else 0.0
    typical = (tail["high"] + tail["low"] + tail["close"]) / 3
    vwap = float((typical * tail["volume"]).sum() / volume_sum) if volume_sum else float(last["close"])
    avg_volume = float(bars["volume"].tail(21).head(20).mean()) if "volume" in bars else 0.0
    relative_volume = float(last["volume"] / avg_volume) if avg_volume else 0.0
    sma20 = float(bars["close"].tail(20).mean())
    sma50 = float(bars["close"].tail(50).mean()) if len(bars) >= 50 else sma20
    current = float(last["close"])
    trend: Literal["up", "down", "sideways", "unknown"]
    trend = "up" if current > sma20 > sma50 else "down" if current < sma20 < sma50 else "sideways"
    recent_high = float(tail["high"].iloc[:-1].max()) if len(tail) > 1 else float(previous["high"])
    recent_low = float(tail["low"].iloc[:-1].min()) if len(tail) > 1 else float(previous["low"])
    return UnderlyingContext(
        ticker=ticker,
        current_price=current,
        vwap=vwap,
        prior_day_high=float(previous["high"]),
        prior_day_low=float(previous["low"]),
        premarket_high=0.0,
        premarket_low=0.0,
        opening_range_high=0.0,
        opening_range_low=0.0,
        relative_volume=relative_volume,
        trend_direction=trend,
        nearest_demand=recent_low,
        nearest_supply=recent_high,
    )


def _render_summary(streamlit: Any, analysis: OptionFlowAnalysis) -> None:
    streamlit.subheader("Flow Decision")
    cols = streamlit.columns(7)
    cols[0].metric("Ticker", analysis.ticker)
    cols[1].metric("Last", f"{analysis.current_price:.2f}")
    cols[2].metric("Call Buy Score", f"{analysis.call_buy_score:.0f}")
    cols[3].metric("Put Buy Score", f"{analysis.put_buy_score:.0f}")
    cols[4].metric("No-Trade Risk", f"{analysis.no_trade_risk:.0f}")
    cols[5].metric("Trigger", f"{analysis.trigger_price:.2f}" if analysis.trigger_price else "n/a")
    cols[6].metric("Invalidation", f"{analysis.invalidation_price:.2f}" if analysis.invalidation_price else "n/a")

    signal_class = _signal_class(analysis.final_signal)
    streamlit.markdown(
        f'<span class="qx-badge {signal_class}">{analysis.final_signal}</span>',
        unsafe_allow_html=True,
    )


def _render_tabs(streamlit: Any, analysis: OptionFlowAnalysis, bars: pd.DataFrame) -> None:
    flow = trades_frame(analysis.trades, analysis.classifications)
    bullish = flow[flow["directional_read"].eq("bullish")]
    bearish = flow[flow["directional_read"].eq("bearish")]
    conflicts = flow[flow["directional_read"].isin(["neutral", "spread-risk", "hedge-risk"])]

    tabs = streamlit.tabs(
        [
            "Why",
            "Top Bullish Flow",
            "Top Bearish Flow",
            "Conflicting Flow",
            "Suggested Contracts",
            "Risk Warnings",
            "Chart",
            "Diagnostics",
        ]
    )
    with tabs[0]:
        render_bullet_list(streamlit, analysis.why, empty="No explanation generated.")
    with tabs[1]:
        _show_flow_table(streamlit, bullish, "No bullish flow rows.")
    with tabs[2]:
        _show_flow_table(streamlit, bearish, "No bearish flow rows.")
    with tabs[3]:
        _show_flow_table(streamlit, conflicts, "No conflicting, spread-risk, or hedge-risk rows.")
    with tabs[4]:
        contracts = suggested_contracts_frame(analysis)
        if contracts.empty:
            streamlit.info("No contract passed the day-trade or swing-trade quality filters.")
        else:
            streamlit.dataframe(display_frame(contracts), width="stretch", hide_index=True)
    with tabs[5]:
        render_bullet_list(streamlit, analysis.warnings, empty="No risk warnings.")
    with tabs[6]:
        streamlit.plotly_chart(_flow_chart(analysis, bars), width="stretch")
    with tabs[7]:
        streamlit.json(analysis.model_dump(mode="json"))


def _show_flow_table(streamlit: Any, frame: pd.DataFrame, empty: str) -> None:
    if frame.empty:
        streamlit.info(empty)
        return
    ordered = frame.sort_values(["premium", "aggression_score"], ascending=False)
    streamlit.dataframe(
        display_frame(
            ordered,
            columns=[
                "ticker",
                "option_symbol",
                "expiration",
                "strike",
                "option_type",
                "trade_price",
                "bid",
                "ask",
                "spread_pct",
                "size",
                "premium",
                "volume",
                "open_interest",
                "implied_volatility",
                "trade_kind",
                "trade_side",
                "directional_read",
                "aggression_score",
                "risk_tags",
            ],
        ),
        width="stretch",
        hide_index=True,
    )


def _flow_chart(analysis: OptionFlowAnalysis, bars: pd.DataFrame) -> go.Figure:
    chart_bars = bars.tail(80).copy()
    figure = go.Figure()
    figure.add_trace(
        go.Candlestick(
            x=chart_bars.index,
            open=chart_bars["open"],
            high=chart_bars["high"],
            low=chart_bars["low"],
            close=chart_bars["close"],
            name="Price",
        )
    )
    if "volume" in chart_bars:
        figure.add_trace(
            go.Bar(
                x=chart_bars.index,
                y=chart_bars["volume"],
                name="Volume",
                yaxis="y2",
                marker_color="rgba(37, 99, 235, 0.22)",
            )
        )
    last_x = chart_bars.index[-1]
    _add_level(figure, chart_bars, analysis.trigger_price, "Trigger", "#16a34a")
    _add_level(figure, chart_bars, analysis.invalidation_price, "Invalidation", "#dc2626")
    bullish_size = sum(trade.effective_premium for trade, item in zip(analysis.trades, analysis.classifications, strict=True) if item.directional_read == "bullish")
    bearish_size = sum(trade.effective_premium for trade, item in zip(analysis.trades, analysis.classifications, strict=True) if item.directional_read == "bearish")
    if bullish_size:
        figure.add_trace(
            go.Scatter(
                x=[last_x],
                y=[analysis.current_price],
                mode="markers+text",
                marker={"symbol": "triangle-up", "size": 15, "color": "#16a34a"},
                text=[f"Call flow ${bullish_size / 1000:.0f}K"],
                textposition="top center",
                name="Bullish flow",
            )
        )
    if bearish_size:
        figure.add_trace(
            go.Scatter(
                x=[last_x],
                y=[analysis.current_price],
                mode="markers+text",
                marker={"symbol": "triangle-down", "size": 15, "color": "#dc2626"},
                text=[f"Put flow ${bearish_size / 1000:.0f}K"],
                textposition="bottom center",
                name="Bearish flow",
            )
        )
    figure.update_layout(
        height=520,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        xaxis_rangeslider_visible=False,
        yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "visible": False},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font_color="#e6e9ee",
    )
    return figure


def _add_level(figure: go.Figure, bars: pd.DataFrame, level: float | None, label: str, color: str) -> None:
    if not level:
        return
    figure.add_trace(
        go.Scatter(
            x=[bars.index[0], bars.index[-1]],
            y=[level, level],
            mode="lines",
            line={"color": color, "dash": "dash", "width": 1},
            name=f"{label} {level:.2f}",
        )
    )


def _signal_class(signal: str) -> str:
    if signal.startswith("CALLS"):
        return "qx-bull"
    if signal.startswith("PUTS"):
        return "qx-bear"
    if signal in {"CONFLICTED FLOW", "IV CHASE RISK"}:
        return "qx-watch"
    return "qx-neutral"


run_standalone_page(
    "Options Flow",
    "Score directional call/put flow with price, IV, liquidity, and regime filters.",
    render_options_flow_page,
)
