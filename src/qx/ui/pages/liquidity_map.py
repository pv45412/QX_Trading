from html import escape
from typing import Any

import pandas as pd

from qx.data.cache import CachedMarketDataProvider
from qx.data.factory import (
    build_fallback_market_data_provider,
    build_options_chain_provider,
    build_quote_provider,
)
from qx.data.quotes import QuoteSnapshot
from qx.liquidity.engine import (
    build_liquidity_map,
    generate_tos_liquidity_study,
    liquidity_levels_frame,
    option_walls_frame,
)
from qx.liquidity.models import LiquidityLevel, LiquiditySnapshot, OptionWall
from qx.models.market import BarDataRequest, IntradayBarDataRequest
from qx.ui.app_shell import ensure_app_styles, render_bullet_list, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame
from qx.ui.tradingview import render_lightweight_candles


CHART_INTERVAL_OPTIONS = ["5m", "15m", "30m", "1h", "Daily", "Weekly", "Monthly", "Quarterly"]


def render_liquidity_map_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    streamlit.subheader("Liquidity Map")
    streamlit.caption(
        "Build day-trading levels from price structure and option-chain walls. This is separate from the rectangle qx."
    )

    with streamlit.container(border=True):
        cols = streamlit.columns([1.1, 0.8, 0.9, 0.9, 1.0])
        symbol = cols[0].text_input("Symbol", value="SPY", key="liquidity_symbol")
        period = cols[1].selectbox("History", ["3mo", "6mo", "1y", "2y"], index=1, key="liquidity_period")
        data_source = cols[2].selectbox(
            "Market Data",
            MARKET_DATA_PROVIDER_OPTIONS,
            index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
            key="liquidity_market_data",
        )
        options_source = cols[3].selectbox(
            "Options Data",
            ["schwab", "yfinance", "none"],
            index=0,
            key="liquidity_options_data",
        )
        build_clicked = cols[4].button("Build Map", type="primary", width="stretch")

        chart_cols = streamlit.columns([1.0, 1.0, 1.0, 2.0])
        chart_interval = chart_cols[0].selectbox(
            "Chart Candles",
            CHART_INTERVAL_OPTIONS,
            index=0,
            key="liquidity_chart_interval",
        )
        chart_size = chart_cols[1].selectbox(
            "Chart Size",
            ["Compact", "Standard", "Large"],
            index=1,
            key="liquidity_chart_size",
        )
        refresh_cache = chart_cols[2].checkbox(
            "Refresh cached bars",
            value=False,
            key="liquidity_refresh_cache",
            help="Pull fresh bars from the selected provider instead of using the local cache.",
        )
        streamlit.caption(
            "Use /ES, /NQ, /RTY, /CL, /GC for futures levels. 5m/15m/30m/1h bars are refresh-on-demand, "
            "not streaming ticks; use Refresh cached bars for the latest provider pull. Options walls apply to equities/ETFs only."
        )

    if not build_clicked:
        streamlit.info("Enter a symbol and build the map. Good starting symbols: /ES, /NQ, /RTY, /CL, /GC, SPY, QQQ.")
        return

    quote: QuoteSnapshot | None = None
    with streamlit.spinner(f"Building liquidity map for {symbol.strip().upper()}..."):
        try:
            provider = CachedMarketDataProvider(
                build_fallback_market_data_provider(str(data_source)),
                refresh=bool(refresh_cache),
            )
            options_provider = build_options_chain_provider(str(options_source))
            snapshot = build_liquidity_map(
                symbol,
                provider,
                options_provider=options_provider,
                period=str(period),
            )
            bars = _load_chart_bars(
                provider,
                snapshot.data_symbol,
                period=str(period),
                chart_interval=str(chart_interval),
            )
        except Exception as exc:
            streamlit.error(f"Could not build liquidity map for {symbol.strip().upper()}: {exc}")
            streamlit.info("For Russell futures, use `/RTY`.")
            return

        try:
            quote = build_quote_provider(str(data_source)).get_quote(snapshot.data_symbol)
        except Exception as exc:
            snapshot.diagnostics.append(f"Current quote unavailable: {exc}")

    _render_snapshot_header(streamlit, snapshot, bars, quote)
    stale_warning = _latest_bar_warning(bars, refreshed=bool(refresh_cache), chart_interval=str(chart_interval))
    if stale_warning:
        streamlit.warning(stale_warning)

    tabs = streamlit.tabs(["Map", "Price Levels", "Options Walls", "TOS Export", "Diagnostics"])
    with tabs[0]:
        _render_map_tab(streamlit, snapshot, bars, chart_interval=str(chart_interval), chart_size=str(chart_size))
    with tabs[1]:
        _render_level_table(streamlit, snapshot.levels)
    with tabs[2]:
        _render_option_wall_table(streamlit, snapshot.option_walls)
    with tabs[3]:
        tos_script = generate_tos_liquidity_study(snapshot)
        streamlit.code(tos_script, language="thinkscript")
        streamlit.download_button(
            "Download ThinkScript",
            data=tos_script,
            file_name=f"qx_liquidity_map_{snapshot.symbol}.ts",
            mime="text/plain",
        )
    with tabs[4]:
        streamlit.write("**Provider notes**")
        render_bullet_list(
            streamlit,
            snapshot.diagnostics
            or [
                "Price levels loaded successfully.",
                "Option walls loaded when the selected provider returned option chains.",
            ],
        )


def _render_snapshot_header(
    streamlit: Any,
    snapshot: LiquiditySnapshot,
    bars: pd.DataFrame,
    quote: QuoteSnapshot | None,
) -> None:
    support = _level_text(snapshot.nearest_support)
    resistance = _level_text(snapshot.nearest_resistance)
    call_wall = _wall_text(snapshot.top_call_wall)
    put_wall = _wall_text(snapshot.top_put_wall)
    cols = streamlit.columns(6)
    cols[0].metric("Symbol", snapshot.symbol)
    cols[1].metric("Quote Now", _quote_price_text(quote, snapshot.current_price), _quote_delta_text(quote))
    cols[2].metric("Bias", snapshot.bias)
    cols[3].metric("Nearest Demand", support)
    cols[4].metric("Nearest Supply", resistance)
    cols[5].metric("Asset", snapshot.asset_type)

    streamlit.markdown(
        f"""
<div class="qx-futures-context">
  {_context_chip("Call Wall", call_wall, _tone_from_wall(snapshot.top_call_wall, "call"))}
  {_context_chip("Put Wall", put_wall, _tone_from_wall(snapshot.top_put_wall, "put"))}
  {_context_chip("Data Symbol", snapshot.data_symbol, "neutral")}
  {_context_chip("Quote Source", _quote_source_text(quote), "neutral")}
  {_context_chip("Latest Bar", _latest_bar_label(bars), _latest_bar_tone(bars))}
  {_context_chip("Generated", snapshot.generated_at.strftime("%b %d %I:%M %p"), "neutral")}
</div>
""",
        unsafe_allow_html=True,
    )


def _render_map_tab(
    streamlit: Any,
    snapshot: LiquiditySnapshot,
    bars: Any,
    *,
    chart_interval: str,
    chart_size: str,
) -> None:
    near_levels = sorted(snapshot.levels, key=lambda level: (abs(level.distance_pct), -level.score))[:8]
    if not near_levels:
        streamlit.warning("No levels available.")
        return
    render_lightweight_candles(
        streamlit,
        bars,
        title=f"{snapshot.symbol} liquidity map",
        interval=chart_interval,
        height=_chart_height(chart_size),
        levels=[
            {
                "price": level.price,
                "label": level.label,
                "side": level.side,
                "source": level.source,
            }
            for level in near_levels
        ],
    )
    tiles = [_level_tile(level) for level in near_levels]
    streamlit.markdown(f'<div class="qx-futures-strip">{"".join(tiles)}</div>', unsafe_allow_html=True)

    streamlit.subheader("Execution Read")
    bullets = _execution_read(snapshot)
    render_bullet_list(streamlit, bullets)


def _chart_height(size: str) -> int:
    if size == "Compact":
        return 420
    if size == "Large":
        return 680
    return 540


def _load_chart_bars(
    provider: CachedMarketDataProvider,
    data_symbol: str,
    *,
    period: str,
    chart_interval: str,
) -> pd.DataFrame:
    interval_minutes = _intraday_minutes(chart_interval)
    if interval_minutes is None:
        return provider.get_daily_bars(BarDataRequest(symbol=data_symbol, period=period))
    return provider.get_intraday_bars(
        IntradayBarDataRequest(
            symbol=data_symbol,
            period=_intraday_period(period),
            interval_minutes=interval_minutes,
            include_extended_hours=True,
        )
    )


def _intraday_minutes(chart_interval: str) -> int | None:
    normalized = chart_interval.strip().lower()
    if normalized in {"5m", "5min"}:
        return 5
    if normalized in {"15m", "15min"}:
        return 15
    if normalized in {"30m", "30min"}:
        return 30
    if normalized in {"1h", "hourly"}:
        return 60
    return None


def _intraday_period(period: str) -> str:
    if period == "3mo":
        return "5d"
    return "10d"


def _render_level_table(streamlit: Any, levels: list[LiquidityLevel]) -> None:
    frame = liquidity_levels_frame(levels)
    if frame.empty:
        streamlit.info("No price levels available.")
        return
    columns = ["label", "side", "price", "distance_pct", "score", "source", "note"]
    streamlit.dataframe(display_frame(frame, columns=columns), width="stretch", hide_index=True)


def _render_option_wall_table(streamlit: Any, walls: list[OptionWall]) -> None:
    frame = option_walls_frame(walls)
    if frame.empty:
        streamlit.info("No option walls available for this symbol/provider.")
        return
    columns = ["side", "expiration", "strike", "distance_pct", "open_interest", "volume", "implied_volatility", "score"]
    streamlit.dataframe(display_frame(frame, columns=columns), width="stretch", hide_index=True)


def _execution_read(snapshot: LiquiditySnapshot) -> list[str]:
    read: list[str] = []
    if snapshot.nearest_resistance is not None:
        read.append(
            f"Upside trigger: acceptance above {snapshot.nearest_resistance.price:.2f} "
            f"({snapshot.nearest_resistance.label})."
        )
    if snapshot.nearest_support is not None:
        read.append(
            f"Downside invalidation/support: {snapshot.nearest_support.price:.2f} "
            f"({snapshot.nearest_support.label})."
        )
    if snapshot.top_call_wall is not None:
        read.append(
            f"Call-wall supply estimate: {snapshot.top_call_wall.strike:.2f}, "
            f"OI {snapshot.top_call_wall.open_interest:,}."
        )
    if snapshot.top_put_wall is not None:
        read.append(
            f"Put-wall demand estimate: {snapshot.top_put_wall.strike:.2f}, "
            f"OI {snapshot.top_put_wall.open_interest:,}."
        )
    if not read:
        read.append("Use the closest price structure levels until option-chain data is available.")
    return read


def _level_tile(level: LiquidityLevel) -> str:
    tone = "positive" if level.side == "support" else "negative"
    return (
        f'<div class="qx-future-tile qx-tone-{tone}">'
        f'<div class="qx-future-head"><strong>{escape(level.label)}</strong><span>{escape(level.source)}</span></div>'
        f'<div class="qx-future-main">{level.price:.2f}</div>'
        f'<div class="qx-future-sub">{level.distance_pct:+.1%} from last | score {level.score:.2f}</div>'
        f'<div class="qx-future-status">{escape(level.side.title())}</div>'
        "</div>"
    )


def _context_chip(label: str, value: str, tone: str) -> str:
    return (
        f'<div class="qx-context-chip qx-tone-{escape(tone)}">'
        f'<span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
    )


def _quote_price_text(quote: QuoteSnapshot | None, fallback: float) -> str:
    if quote is not None and quote.last is not None:
        return f"{quote.last:.2f}"
    return f"{fallback:.2f}"


def _quote_delta_text(quote: QuoteSnapshot | None) -> str | None:
    if quote is None or quote.change_pct is None:
        return None
    return f"{quote.change_pct:+.1%}"


def _quote_source_text(quote: QuoteSnapshot | None) -> str:
    if quote is None:
        return "n/a"
    if quote.timestamp is None:
        return quote.provider
    return f"{quote.provider} {quote.timestamp.strftime('%I:%M %p')}"


def _latest_bar_timestamp(bars: pd.DataFrame) -> pd.Timestamp | None:
    if bars.empty:
        return None
    try:
        timestamp = pd.Timestamp(bars.index[-1])
    except (TypeError, ValueError):
        return None
    if pd.isna(timestamp):
        return None
    return timestamp


def _latest_bar_label(bars: pd.DataFrame) -> str:
    timestamp = _latest_bar_timestamp(bars)
    if timestamp is None:
        return "n/a"
    if timestamp.hour or timestamp.minute:
        return timestamp.strftime("%b %d, %I:%M %p")
    return timestamp.strftime("%b %d, %Y")


def _latest_bar_tone(bars: pd.DataFrame) -> str:
    age = _latest_bar_age_days(bars)
    if age is None:
        return "negative"
    return "negative" if age > 3 else "positive"


def _latest_bar_warning(bars: pd.DataFrame, *, refreshed: bool, chart_interval: str = "Daily") -> str | None:
    timestamp = _latest_bar_timestamp(bars)
    age = _latest_bar_age_days(bars)
    if timestamp is None or age is None:
        return "No dated bars were returned for this symbol."
    if _intraday_minutes(chart_interval) is not None:
        age_minutes = max(int((_now_for_timestamp(timestamp) - timestamp).total_seconds() // 60), 0)
        if age_minutes <= 90:
            return None
        action = (
            "The page already requested a fresh provider pull."
            if refreshed
            else "Turn on Refresh cached bars and rebuild the map."
        )
        return f"Latest intraday bar is {timestamp.strftime('%b %d, %I:%M %p')} ({age_minutes} minutes old). {action}"
    if age <= 3:
        return None
    action = "The page already requested a fresh provider pull." if refreshed else "Turn on Refresh cached bars and rebuild the map."
    return f"Latest daily bar is {timestamp.strftime('%b %d, %Y')} ({age} calendar days old). {action}"


def _latest_bar_age_days(bars: pd.DataFrame) -> int | None:
    timestamp = _latest_bar_timestamp(bars)
    if timestamp is None:
        return None
    today = _now_for_timestamp(timestamp).normalize()
    return max((today - timestamp.normalize()).days, 0)


def _now_for_timestamp(timestamp: pd.Timestamp) -> pd.Timestamp:
    timezone = timestamp.tz
    if timezone is None:
        return pd.Timestamp.now()
    return pd.Timestamp.now(tz=timezone)


def _level_text(level: LiquidityLevel | None) -> str:
    return "n/a" if level is None else f"{level.price:.2f}"


def _wall_text(wall: OptionWall | None) -> str:
    if wall is None:
        return "n/a"
    return f"{wall.strike:.2f} ({wall.open_interest:,} OI)"


def _tone_from_wall(wall: OptionWall | None, side: str) -> str:
    if wall is None:
        return "neutral"
    return "negative" if side == "call" else "positive"


run_standalone_page(
    "Liquidity Map",
    "Build day-trading liquidity levels from price structure and option walls.",
    render_liquidity_map_page,
)
