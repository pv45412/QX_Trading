"""Snapshot-only sector presentation; no provider calls during navigation."""

from typing import Any

import pandas as pd
import plotly.express as px  # type: ignore[import-untyped]
import math
from html import escape


def ranked_sectors(frame: pd.DataFrame, window: str = "relative_20d") -> pd.DataFrame:
    return frame.sort_values(window, ascending=False, na_position="last", kind="stable").reset_index(drop=True)


def excess_cell_style(value: object) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value == 0:
        return ""
    return ("background-color: #e0f3eb; color: #146448" if value > 0
            else "background-color: #fbe8ea; color: #a22b3c")


def dark_excess_style(value: object) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value == 0:
        return "color: #99a3b0"
    return "color: #32c69a" if value > 0 else "color: #ec7583"


def _leadership_summaries(st: Any, frame: pd.DataFrame) -> None:
    columns = st.columns(3)
    for column, (title, field, ascending) in zip(columns, [
        ("20D leaders", "relative_20d", False),
        ("5D leaders", "relative_5d", False),
        ("20D laggards", "relative_20d", True),
    ], strict=True):
        rows = frame.dropna(subset=[field]).sort_values(field, ascending=ascending).head(3)
        content = ""
        for _, row in rows.iterrows():
            color = "rs-up" if row[field] >= 0 else "rs-down"
            content += (f'<div class="rs-summary-row"><span><b>{escape(str(row["etf"]))}</b>'
                        f'<small>{escape(str(row["sector"]))}</small></span>'
                        f'<span class="{color}">{row[field] * 100:+.2f} pp</span></div>')
        if rows.empty:
            content = "Unavailable"
        column.markdown(f'<div class="rs-summary"><div class="rs-summary-title">{escape(title.upper())}</div>{content}</div>', unsafe_allow_html=True)


def render_sector_board(st: Any, frame: pd.DataFrame, candidates: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No sector observations available.")
        return
    _leadership_summaries(st, frame)
    st.divider()
    st.subheader("Sector Ranking")
    controls = st.columns([2, 1])
    query = controls[0].text_input("Find sector or ETF", key="sector_board_search", placeholder="Symbol or sector")
    window = controls[1].selectbox("Rank window", ["20D", "5D", "60D"], key="sector_board_window")
    metric = {"5D": "relative_5d", "20D": "relative_20d", "60D": "relative_60d"}[window]
    ranked = ranked_sectors(frame, metric)
    valid = ranked[ranked[metric].notna()]
    columns = st.columns(3)
    columns[0].metric(f"{window} leader", str(valid.iloc[0]["etf"]) if not valid.empty else "Unavailable")
    columns[1].metric("Ahead of SPY", f"{int((ranked[metric] > 0).sum())} / {len(valid)}")
    computed = int(frame.get("rs_status", pd.Series(dtype=str)).eq("COMPUTED").sum())
    columns[2].metric("Aligned RS evidence", f"{computed} / {len(frame)}")
    if query.strip():
        mask = ranked[["etf", "sector"]].fillna("").astype(str).apply(
            lambda col: col.str.contains(query.strip(), case=False, regex=False)
        ).any(axis=1)
        ranked = ranked[mask]
    if ranked.empty:
        st.info("No matching sectors.")
        return
    shown = ranked[["etf", "sector", "relative_5d", "relative_20d", "relative_60d"]].copy()
    shown.columns = ["ETF", "Sector", "5D vs SPY (pp)", "20D vs SPY (pp)", "60D vs SPY (pp)"]
    for column in shown.columns[2:]:
        shown[column] = pd.to_numeric(shown[column], errors="coerce") * 100
    config = {name: st.column_config.NumberColumn(name, format="%+.2f") for name in shown.columns[2:]}
    if "rs_quadrant" in ranked:
        shown["RS quadrant"] = ranked["rs_quadrant"]
    table_key = "sector_ranking_" + window + "_" + "_".join(ranked["etf"].astype(str))
    styled = shown.style.map(lambda value: "background-color: #151920; color: #e8edf3")
    styled = styled.map(dark_excess_style, subset=list(config))
    event = st.dataframe(styled,
                        hide_index=True, width="stretch", height=min(470, 38 + len(shown) * 35),
                        column_config=config, on_select="rerun", selection_mode="single-row", key=table_key)
    st.download_button("Export ranking", shown.to_csv(index=False), "sector-ranking.csv", "text/csv")
    symbols = ranked["etf"].tolist()
    selected_rows = event.selection.rows
    selection = (table_key, tuple(selected_rows))
    if st.session_state.get("sector_board_selection") != selection:
        st.session_state["sector_board_selection"] = selection
        if selected_rows and 0 <= selected_rows[0] < len(symbols):
            st.session_state["sector_board_symbol"] = symbols[selected_rows[0]]
    if st.session_state.get("sector_board_symbol") not in symbols:
        st.session_state["sector_board_symbol"] = symbols[0]
    symbol = st.selectbox("ETF details", ranked["etf"].tolist(), key="sector_board_symbol")
    row = ranked[ranked["etf"] == symbol].iloc[0]
    st.divider()
    st.subheader(f"{symbol} / {row['sector']}")
    chart_frame = pd.DataFrame({"Window": ["5 days", "20 days", "60 days"], "Relative return (pp)": [row["relative_5d"] * 100, row["relative_20d"] * 100, row["relative_60d"] * 100]})
    chart = px.bar(chart_frame, x="Window", y="Relative return (pp)", color="Relative return (pp)", color_continuous_scale=["#c43d45", "#f3f4f5", "#23866a"], color_continuous_midpoint=0)
    chart.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), showlegend=False, coloraxis_showscale=False)
    chart.update_layout(template="plotly_dark", paper_bgcolor="#0e1117", plot_bgcolor="#0e1117", font_color="#e6e9ee")
    st.plotly_chart(chart, width="stretch")
    with st.expander("Rule evidence", expanded=True):
        if row.get("rs_status") == "COMPUTED":
            st.write(f"**{row['rs_quadrant']}** · RS20 {row['rs20_aligned'] * 100:+.2f} pp · five-day RS change {row['rs_momentum_5d'] * 100:+.2f} pp")
            st.caption("Date-aligned calculation. Source freshness has not been verified.")
        else:
            st.warning(f"Aligned RS evidence unavailable: {row.get('rs_status', 'legacy snapshot')}. No replacement values inferred.")
        st.caption("Excess return = ETF return minus SPY return. Existing scan qualification is unchanged.")
    st.write("**Saved scanner candidates**")
    if candidates.empty or "sector" not in candidates:
        st.info("No saved candidates available.")
    else:
        selected = candidates[candidates["sector"] == row["sector"]]
        if selected.empty:
            st.info("No saved candidates for this sector.")
        else:
            columns_to_show = [name for name in ["symbol", "rank_score", "status", "close"] if name in selected]
            st.dataframe(selected[columns_to_show], hide_index=True, width="stretch")
