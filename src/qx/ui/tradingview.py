from __future__ import annotations

import json
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any, cast

import pandas as pd


LIGHTWEIGHT_CHARTS_CDN = (
    "https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"
)
LIGHTWEIGHT_CHARTS_LOCAL = Path(__file__).with_name("assets") / "lightweight-charts.standalone.production.js"


def render_lightweight_candles(
    streamlit: Any,
    bars: pd.DataFrame,
    *,
    title: str,
    levels: list[dict[str, Any]] | None = None,
    interval: str = "Daily",
    height: int = 520,
) -> None:
    """Render a TradingView Lightweight Charts candlestick panel inside Streamlit."""
    from streamlit.components.v1 import html

    html(
        build_lightweight_chart_html(
            bars,
            title=title,
            levels=levels or [],
            interval=interval,
            height=height,
        ),
        height=height,
        scrolling=False,
    )


def build_lightweight_chart_html(
    bars: pd.DataFrame,
    *,
    title: str,
    levels: list[dict[str, Any]] | None = None,
    interval: str = "Daily",
    height: int = 520,
) -> str:
    candles, volumes = _chart_data(bars, interval=interval)
    levels_payload = _level_data(levels or [])
    library_script = _library_script_tag()
    interval_label = _interval_label(interval)
    time_visible = "true" if _is_intraday_interval(interval) else "false"
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  {library_script}
  <style>
    body {{
      margin: 0;
      background: transparent;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #e6e9ee;
    }}
    .qx-tv-wrap {{
      height: {height - 4}px;
      border: 1px solid #282e38;
      border-radius: 8px;
      background: #0e1117;
      overflow: hidden;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06), 0 12px 26px rgba(15, 23, 42, 0.05);
    }}
    .qx-tv-head {{
      height: 42px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 14px;
      border-bottom: 1px solid #282e38;
      background: #171c24;
      box-sizing: border-box;
    }}
    .qx-tv-title {{
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0;
    }}
    .qx-tv-note {{
      font-size: 11px;
      color: #9da8b8;
    }}
    #chart {{
      height: {height - 46}px;
      width: 100%;
    }}
    .qx-tv-error {{
      padding: 22px;
      color: #ee6975;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="qx-tv-wrap">
    <div class="qx-tv-head">
      <div class="qx-tv-title">{escape(title)}</div>
      <div class="qx-tv-note">{escape(interval_label)} candles | TradingView Lightweight Charts</div>
    </div>
    <div id="chart"></div>
  </div>
  <script>
    const candles = {json.dumps(candles)};
    const volumes = {json.dumps(volumes)};
    const levels = {json.dumps(levels_payload)};

    function renderChart() {{
      if (!window.LightweightCharts) {{
        document.getElementById('chart').innerHTML =
          '<div class="qx-tv-error">Chart library failed to load. Check network access to unpkg.com.</div>';
        return;
      }}
      const el = document.getElementById('chart');
      const chart = LightweightCharts.createChart(el, {{
        layout: {{
          background: {{ color: '#0e1117' }},
          textColor: '#e6e9ee',
          fontFamily: 'Inter, system-ui, sans-serif',
        }},
        grid: {{
          vertLines: {{ color: '#282e38' }},
          horzLines: {{ color: '#282e38' }},
        }},
        rightPriceScale: {{ borderColor: '#282e38' }},
        timeScale: {{
          borderColor: '#282e38',
          timeVisible: {time_visible},
          secondsVisible: false,
        }},
        crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
        handleScroll: true,
        handleScale: true,
      }});

      const candleSeries = chart.addCandlestickSeries({{
        upColor: '#16a34a',
        downColor: '#dc2626',
        borderUpColor: '#16a34a',
        borderDownColor: '#dc2626',
        wickUpColor: '#15803d',
        wickDownColor: '#b91c1c',
      }});
      candleSeries.setData(candles);

      const volumeSeries = chart.addHistogramSeries({{
        priceFormat: {{ type: 'volume' }},
        priceScaleId: '',
      }});
      volumeSeries.priceScale().applyOptions({{
        scaleMargins: {{ top: 0.82, bottom: 0 }},
      }});
      volumeSeries.setData(volumes);

      levels.forEach((level) => {{
        candleSeries.createPriceLine({{
          price: level.price,
          color: level.color,
          lineWidth: level.width,
          lineStyle: level.style,
          axisLabelVisible: true,
          title: level.title,
        }});
      }});

      chart.timeScale().fitContent();
      const observer = new ResizeObserver(entries => {{
        const width = entries[0].contentRect.width;
        chart.applyOptions({{ width }});
      }});
      observer.observe(el);
    }}

    renderChart();
  </script>
</body>
</html>
"""


@lru_cache(maxsize=1)
def _library_script_tag() -> str:
    if LIGHTWEIGHT_CHARTS_LOCAL.exists():
        return f"<script>{LIGHTWEIGHT_CHARTS_LOCAL.read_text(encoding='utf-8')}</script>"
    return f'<script src="{LIGHTWEIGHT_CHARTS_CDN}"></script>'


def _chart_data(
    bars: pd.DataFrame,
    *,
    interval: str = "Daily",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frame = _resample_bars(bars, interval).tail(_tail_count(interval))
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index)
    candles: list[dict[str, Any]] = []
    volumes: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        timestamp = pd.Timestamp(cast(Any, index))
        time_value: int | str
        if _is_intraday_interval(interval):
            time_value = int(timestamp.timestamp())
        else:
            time_value = timestamp.strftime("%Y-%m-%d")
        open_price = float(row["open"])
        close_price = float(row["close"])
        candles.append(
            {
                "time": time_value,
                "open": open_price,
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": close_price,
            }
        )
        volumes.append(
            {
                "time": time_value,
                "value": float(row.get("volume", 0.0)),
                "color": "rgba(22, 163, 74, 0.32)"
                if close_price >= open_price
                else "rgba(220, 38, 38, 0.28)",
            }
        )
    return candles, volumes


def _resample_bars(bars: pd.DataFrame, interval: str) -> pd.DataFrame:
    frame = bars.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    rule = _resample_rule(interval)
    if rule is None:
        return frame
    return (
        frame.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def _resample_rule(interval: str) -> str | None:
    normalized = interval.lower().strip()
    if normalized.startswith("week"):
        return "W-FRI"
    if normalized.startswith("month"):
        return "ME"
    if normalized.startswith("quarter"):
        return "QE"
    return None


def _is_intraday_interval(interval: str) -> bool:
    normalized = interval.lower().strip()
    return normalized.endswith("m") or normalized.endswith("min") or normalized in {"1h", "hourly"}


def _tail_count(interval: str) -> int:
    normalized = interval.lower().strip()
    if normalized in {"5m", "5min"}:
        return 390
    if normalized in {"15m", "15min"}:
        return 260
    if normalized in {"30m", "30min"}:
        return 220
    if normalized in {"1h", "hourly"}:
        return 180
    if normalized.startswith("week"):
        return 156
    if normalized.startswith("month"):
        return 84
    if normalized.startswith("quarter"):
        return 40
    return 180


def _interval_label(interval: str) -> str:
    normalized = interval.lower().strip()
    if normalized in {"5m", "5min"}:
        return "5-minute"
    if normalized in {"15m", "15min"}:
        return "15-minute"
    if normalized in {"30m", "30min"}:
        return "30-minute"
    if normalized in {"1h", "hourly"}:
        return "Hourly"
    if normalized.startswith("week"):
        return "Weekly"
    if normalized.startswith("month"):
        return "Monthly"
    if normalized.startswith("quarter"):
        return "Quarterly"
    return "Daily"


def _level_data(levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for level in levels:
        price = float(level["price"])
        side = str(level.get("side", "neutral"))
        source = str(level.get("source", "level"))
        label = str(level.get("label", "Level"))
        is_support = side == "support" or "put_wall" in source
        payload.append(
            {
                "price": price,
                "title": f"{label} {price:.2f}",
                "color": "#16a34a" if is_support else "#dc2626",
                "width": 2 if source in {"option_wall", "prior_day", "range"} else 1,
                "style": 2 if source in {"option_wall", "round"} else 0,
            }
        )
    return payload
