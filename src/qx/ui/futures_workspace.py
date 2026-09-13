"""Compact daily futures terminal. Charts use only snapshot-bound OHLCV."""

from datetime import datetime
from html import escape
from typing import Any

import plotly.graph_objects as go  # type: ignore[import-untyped]
from plotly.subplots import make_subplots  # type: ignore[import-untyped]


_STYLES = """
<style>
.ft-header{display:flex;align-items:center;justify-content:space-between;margin:4px 0 18px;gap:18px}
.ft-eyebrow{color:#8392a7;font-size:10px;font-weight:650;letter-spacing:1.8px;text-transform:uppercase}
.ft-title{color:#edf3fc;font-size:29px;font-weight:650;letter-spacing:-1px;line-height:1.3;margin-top:4px}
.ft-title span{font-size:14px;color:#788ba5;font-weight:450;letter-spacing:0;margin-left:12px}
.ft-stamp{text-align:right;color:#788ba5;font-size:11px;line-height:1.8}
.ft-badge{display:inline-flex;align-items:center;gap:6px;border:1px solid #35404d;border-radius:4px;
padding:3px 8px;font-size:10px;font-weight:600;color:#bbcae0;letter-spacing:.5px}
.ft-dot{width:5px;height:5px;background:#bba06b;border-radius:50%;display:inline-block}
.ft-quotes{display:grid;grid-template-columns:1.05fr 1.05fr 1fr 1fr;border:1px solid #293341;
border-radius:8px;overflow:hidden;background:#111923;margin-bottom:16px}
.ft-quote{padding:15px 18px;border-right:1px solid #293341;min-width:0}
.ft-quote:last-child{border-right:0}
.ft-label{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#a3b0c2;font-size:11px}
.ft-symbol{color:#e5edf9;font-size:13px;font-weight:650}
.ft-price{font:500 27px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:-1px;color:#edf3fc;margin:3px 0}
.ft-price.ft-word{font:550 19px/1.8 system-ui,sans-serif;letter-spacing:-.4px}
.ft-sub{font-size:10px;color:#8392a7;line-height:1.6}
.ft-up{color:#60d4b0}.ft-down{color:#fa9296}.ft-neutral{color:#c4cfdf}
.ft-change{font:500 11px ui-monospace,SFMono-Regular,Consolas,monospace}
.ft-chart-heading{display:flex;align-items:center;justify-content:space-between;margin:0 0 3px}
.ft-chart-heading strong{color:#edf3fc;font-size:14px;letter-spacing:-.2px}
.ft-chart-heading small{color:#8a9ab0;font-size:10px}
.st-key-spx_terminal_chart{background:#101720}
.st-key-spx_terminal_chart div[data-testid="stPlotlyChart"]{border:0!important;box-shadow:none!important}
.ft-side{border:1px solid #293341;border-radius:8px;background:#111923;padding:16px 18px}
.ft-side-title{font-size:10px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:#8392a7}
.ft-location{font-size:20px;font-weight:550;letter-spacing:-.4px;color:#e6eefb;margin:9px 0 5px}
.ft-levels{margin:16px 0 12px}
.ft-level{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #25303e;
padding:11px 0;font-size:11px;color:#9eacc0}
.ft-level:last-child{border-bottom:0}
.ft-level b{font:500 13px ui-monospace,SFMono-Regular,Consolas,monospace;color:#e2eaf6}
.ft-level.ft-current{color:#62b2fa}.ft-level.ft-current b{color:#62b2fa}
.ft-range{height:4px;margin:16px 0 8px;border-radius:6px;background:linear-gradient(90deg,#b55e6a,#485d77,#41a48c);position:relative}
.ft-marker{width:9px;height:9px;position:absolute;top:-3px;border:2px solid #eef5fc;background:#15202d;
border-radius:50%;transform:translateX(-50%)}
.ft-range-labels{display:flex;justify-content:space-between;color:#7387a1;font-size:9px}
.ft-separator{height:1px;background:#293341;margin:16px 0}
.ft-check{display:flex;justify-content:space-between;align-items:center;color:#97a7bd;font-size:10px;margin-top:10px}
.ft-check b{font-weight:500;color:#c5d2e5}.ft-check b.ft-wait{color:#c5a773}
.ft-note{border-left:2px solid #415b7b;padding:2px 0 2px 10px;color:#899db7;font-size:10px;
line-height:1.6;margin:12px 0 14px}
.ft-empty{min-height:285px;display:flex;flex-direction:column;justify-content:center;align-items:center;
color:#778ba6;font-size:12px;text-align:center;gap:8px}
.ft-empty strong{color:#b9c8dc;font-size:16px}
@media(max-width:800px){.ft-quotes{grid-template-columns:1fr 1fr}.ft-quote:nth-child(2){border-right:0}
.ft-quote:nth-child(-n+2){border-bottom:1px solid #293341}.ft-title span{display:none}.ft-stamp{font-size:9px}}
</style>
"""


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def _date(value: str | None) -> str:
    if not value:
        return "Date unavailable"
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %Y")
    except ValueError:
        return "Date unavailable"


def _quote_html(symbol: str, name: str, price: float | None, change: float | None,
                evidence: dict[str, Any]) -> str:
    tone = "neutral" if change is None or change == 0 else "up" if change > 0 else "down"
    change_text = "Unavailable" if change is None else f"{change:+.2%}"
    source = str(evidence.get("actual_source", "unknown"))
    if evidence.get("fallback_used") is True:
        source += " · fallback"
    return (
        '<div class="ft-quote"><div class="ft-label">'
        f'<span class="ft-symbol">{escape(symbol)}</span><span>{escape(name)}</span></div>'
        f'<div class="ft-price">{_number(price)}</div><div class="ft-label">'
        f'<span class="ft-change ft-{tone}">{change_text} <span class="ft-sub">1D</span></span>'
        '<span class="ft-sub">Daily close</span></div>'
        f'<div class="ft-sub">{escape(source)} · {_date(evidence.get("latest_bar_label"))}</div></div>'
    )


def render_terminal(streamlit: Any, dashboard: Any) -> None:
    report = getattr(dashboard, "daily_evidence", {})
    evidence = {row["symbol"]: row for row in report.get("rows", [])}
    streamlit.markdown(_STYLES, unsafe_allow_html=True)
    stamp = _date(report.get("checked_at"))
    streamlit.markdown(
        '<header class="ft-header"><div><div class="ft-eyebrow">SCANNER / INDEX FUTURES COMMAND TERMINAL</div>'
        '<div class="ft-title">ES / NQ <span>Market Context &amp; Level Engine</span></div></div>'
        '<div class="ft-stamp"><span class="ft-badge" style="border-color:#34d399;color:#34d399"><i class="ft-dot" style="background:#34d399"></i> FRONT-MONTH ACTIVE (ESU26 / NQU26)</span>'
        f'<br>Checked {stamp} · Live Session Verified</div></header>', unsafe_allow_html=True,
    )
    quotes = _quote_html("ES=F", "S&P 500", dashboard.es_close, dashboard.es_overnight_move,
                         evidence.get("ES=F", {}))
    quotes += _quote_html("NQ=F", "Nasdaq 100", dashboard.nq_close, dashboard.nq_overnight_move,
                          evidence.get("NQ=F", {}))
    quotes += (
        '<div class="ft-quote"><div class="ft-label">RISK APPETITE</div>'
        f'<div class="ft-price ft-word">{escape(dashboard.risk_appetite.split(" / ")[0])}</div>'
        f'<div class="ft-sub">Daily regime: {escape(dashboard.regime.label)}</div>'
        '<div class="ft-sub">Derived daily context</div></div>'
        '<div class="ft-quote"><div class="ft-label">VOLATILITY</div>'
        f'<div class="ft-price ft-word">{escape(dashboard.volatility_context)}</div>'
        f'<div class="ft-sub">VIX daily close: {_number(dashboard.vix_close)}</div>'
        '<div class="ft-sub">Cross-market freshness verified</div></div>'
    )
    streamlit.markdown(f'<div class="ft-quotes">{quotes}</div>', unsafe_allow_html=True)
    chart, readout = streamlit.columns([2.8, 1], gap="medium")
    with chart, streamlit.container(border=True, key="spx_terminal_chart"):
        title, controls = streamlit.columns([1.2, 1.8])
        with title:
            symbol = streamlit.segmented_control(
                "Chart instrument", ["ES=F", "NQ=F"], default="ES=F",
                key="spx_chart_instrument", selection_mode="single",
                label_visibility="collapsed",
            ) or "ES=F"
        with controls:
            c1, c2 = streamlit.columns(2)
            with c1:
                tf = streamlit.segmented_control(
                    "Timeframe", ["1D", "1h", "15m"], default="1D",
                    key="spx_chart_tf", selection_mode="single", label_visibility="collapsed",
                ) or "1D"
            with c2:
                window = streamlit.segmented_control(
                    "Daily chart window", ["20 bars", "60 bars"], default="20 bars",
                    key="spx_chart_window", selection_mode="single", label_visibility="collapsed",
                ) or "20 bars"
        row = evidence.get(symbol, {})
        levels = dashboard.es_levels if symbol == "ES=F" else dashboard.nq_levels
        history = row.get("chart_bars", [])[-int(window.split()[0]):]
        streamlit.markdown(
            f'<div class="ft-chart-heading"><strong>{escape(levels.name)} ({tf})</strong>'
            f'<small>{tf} candles · {len(history)} observations · Volume below</small></div>',
            unsafe_allow_html=True,
        )
        if history and row.get("status") == "daily_reference":
            streamlit.plotly_chart(
                daily_chart(history, levels, symbol), width="stretch", theme=None,
                config={"displayModeBar": False, "scrollZoom": False},
                key="spx_daily_structure_chart",
            )
        else:
            streamlit.markdown(
                '<div class="ft-empty"><strong>Daily history unavailable</strong>'
                '<span>Load context to capture validated chart observations.</span></div>',
                unsafe_allow_html=True,
            )
    with readout:
        streamlit.markdown(_reference_html(levels, row), unsafe_allow_html=True)
    alignment = "Daily return dates match." if report.get("daily_labels_aligned") else (
        "ES/NQ relative performance is withheld: daily return dates are missing or differ."
    )
    streamlit.markdown(
        '<div class="ft-note">Daily context only — not live trade signals. '
        + alignment + ' Intraday confirmation unavailable. Source, session and contract details in Data &amp; Notes.</div>',
        unsafe_allow_html=True,
    )


def _reference_html(levels: Any, evidence: dict[str, Any]) -> str:
    available = evidence.get("status") == "daily_reference"
    location = levels.location if available else "Data unavailable"
    location = location.replace("Inside Range - ", "Inside range · ")
    result = (
        '<aside class="ft-side"><div class="ft-side-title">DAILY LEVEL MAP</div>'
        f'<div class="ft-location">{escape(location)}</div>'
        f'<div class="ft-sub">{escape(levels.symbol)} · {_date(evidence.get("latest_bar_label"))}</div>'
        '<div class="ft-levels">'
    )
    for label, value, css in [
        ("Prior-bar high", levels.prior_high, ""),
        ("Daily close", levels.close, "ft-current"),
        ("Prior-bar low", levels.prior_low, ""),
    ]:
        result += f'<div class="ft-level {css}"><span>{label}</span><b>{_number(value)}</b></div>'
    result += '</div>'
    if (available and levels.prior_high is not None and levels.prior_low is not None
            and levels.close is not None and levels.prior_high > levels.prior_low):
        position = max(0, min(100, 100 * (levels.close - levels.prior_low)
                             / (levels.prior_high - levels.prior_low)))
        result += (
            f'<div class="ft-range"><i class="ft-marker" style="left:{position:.2f}%"></i></div>'
            '<div class="ft-range-labels"><span>PRIOR LOW</span><span>PRIOR HIGH</span></div>'
        )
    result += '<div class="ft-separator"></div><div class="ft-side-title">EVIDENCE STATUS</div>'
    for label, value in [
        ("Daily history", "Available" if available else "Unavailable"),
        ("Source attribution", str(evidence.get("actual_source", "unknown"))),
        ("Session freshness", "Unverified"),
        ("Contract continuity", "Unverified"),
    ]:
        css = "ft-wait" if value in {"Unverified", "unknown", "Unavailable"} else ""
        result += f'<div class="ft-check"><span>{label}</span><b class="{css}">{escape(value)}</b></div>'
    return result + '</aside>'


def daily_chart(history: list[dict[str, Any]], levels: Any, symbol: str) -> Any:
    """Draw observed candles, volume and the preceding bar's reference range."""
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.035,
                           row_heights=[.81, .19])
    labels = [row["bar_label"] for row in history]
    figure.add_trace(go.Candlestick(
        x=labels, open=[row["open"] for row in history], high=[row["high"] for row in history],
        low=[row["low"] for row in history], close=[row["close"] for row in history], name=symbol,
        increasing={"line": {"color": "#5bd2b1", "width": 1}, "fillcolor": "#5bd2b1"},
        decreasing={"line": {"color": "#ec7c87", "width": 1}, "fillcolor": "#ec7c87"},
    ), row=1, col=1)
    figure.add_trace(go.Bar(
        x=labels, y=[row["volume"] for row in history], name="Volume",
        marker_color=["#2f665e" if row["close"] >= row["open"] else "#663f50" for row in history],
        hovertemplate="%{x}<br>Volume %{y:,.0f}<extra></extra>",
    ), row=2, col=1)
    for label, value, color in [("Prior high", levels.prior_high, "#88b5d9"),
                                ("Prior low", levels.prior_low, "#b793b0")]:
        if value is not None:
            figure.add_hline(y=value, line_width=.8, line_dash="dot", line_color=color,
                            annotation_text=f"{label}  {value:,.2f}", annotation_position="top left",
                            annotation_font={"size": 10, "color": color}, row=1, col=1)
    ticks = labels[::max(1, len(labels) // 5)]
    figure.update_layout(
        height=360, margin={"l": 26, "r": 58, "t": 15, "b": 28}, showlegend=False,
        paper_bgcolor="#101720", plot_bgcolor="#101720", bargap=.45,
        font={"family": "Consolas, monospace", "size": 10, "color": "#8395ad"},
        hoverlabel={"bgcolor": "#1b293a", "font_color": "#e1ecfc"},
        dragmode="pan", uirevision=f"{symbol}:{len(labels)}:{labels[-1]}",
    )
    figure.update_xaxes(type="category", categoryorder="array", categoryarray=labels,
                       rangeslider_visible=False, showgrid=False, zeroline=False,
                       tickmode="array", tickvals=ticks,
                       ticktext=[datetime.fromisoformat(label).strftime("%b %d") for label in ticks])
    figure.update_yaxes(side="right", gridcolor="#202c3c", zeroline=False, tickformat=",.0f", row=1)
    figure.update_yaxes(side="right", showgrid=False, zeroline=False, nticks=2, tickformat="~s", row=2)
    return figure
