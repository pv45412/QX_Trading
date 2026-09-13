from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pandas as pd

from qx.models.scan import ScanCandidate


def build_rectangle_chart(bars: pd.DataFrame, candidate: ScanCandidate) -> Any:
    """Build an annotated Plotly candlestick chart for one candidate."""
    graph_objects = cast(Any, import_module("plotly.graph_objects"))
    figure = graph_objects.Figure()

    figure.add_trace(
        graph_objects.Candlestick(
            x=list(bars.index),
            open=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            name=candidate.symbol,
        )
    )
    figure.add_hline(
        y=candidate.metrics.resistance,
        line_dash="dash",
        line_color="orange",
        annotation_text="Resistance",
    )
    figure.add_hline(
        y=candidate.metrics.support,
        line_dash="dash",
        line_color="cyan",
        annotation_text="Support",
    )
    figure.add_hrect(
        y0=candidate.metrics.support,
        y1=candidate.metrics.resistance,
        fillcolor="orange",
        opacity=0.08,
        line_width=0,
    )
    figure.update_layout(
        title=f"{candidate.symbol} Rectangle Score {candidate.score:.0%}",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
    )
    return figure


def build_weekly_context_chart(bars: pd.DataFrame, candidate: ScanCandidate) -> Any:
    """Build a weekly chart with 10-week and 30-week moving averages."""
    from qx.patterns.weekly import daily_to_weekly

    graph_objects = cast(Any, import_module("plotly.graph_objects"))
    weekly = daily_to_weekly(bars)
    figure = graph_objects.Figure()
    figure.add_trace(
        graph_objects.Candlestick(
            x=list(weekly.index),
            open=weekly["open"],
            high=weekly["high"],
            low=weekly["low"],
            close=weekly["close"],
            name=f"{candidate.symbol} weekly",
        )
    )
    figure.add_trace(
        graph_objects.Scatter(
            x=list(weekly.index),
            y=weekly["close"].rolling(10).mean(),
            name="10-week SMA",
            line={"color": "red", "width": 1.5},
        )
    )
    figure.add_trace(
        graph_objects.Scatter(
            x=list(weekly.index),
            y=weekly["close"].rolling(30).mean(),
            name="30-week SMA",
            line={"color": "black", "width": 1.5},
        )
    )
    status = candidate.weekly_context.status if candidate.weekly_context else "Unknown"
    figure.update_layout(
        title=f"{candidate.symbol} Weekly Context - {status}",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
    )
    return figure


def write_rectangle_chart(path: Path, bars: pd.DataFrame, candidate: ScanCandidate) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure = build_rectangle_chart(bars, candidate)
    figure.write_html(str(path))
