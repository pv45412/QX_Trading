from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px  # type: ignore[import-untyped]

from qx.data.cache import CachedMarketDataProvider
from qx.data.cache_status import latest_completed_session
from qx.data.provenance import valid_provenance
from qx.data.factory import build_fallback_market_data_provider
from qx.data.metadata import SymbolMetadataStore
from qx.data.universe import UniverseLoader
from qx.market.sector_rotation import SectorRotationResult, analyze_sector_rotation, sector_rotation_frame
from qx.market.sessions import completed_mover_bars
from qx.models.market import BarDataRequest
from qx.patterns.ranking import composite_rank_score
from qx.storage.sector_rotation import SQLiteSectorRotationRepository, SectorRankChange, StoredSectorRotationSnapshot
from qx.storage.sqlite import SQLiteScanRepository
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.defaults import MARKET_DATA_PROVIDER_OPTIONS, provider_index
from qx.ui.formatting import display_frame, format_timestamp
from qx.ui.sector_board import render_sector_board
from qx.ui.relative_strength_theme import apply_relative_strength_theme
from qx.ui.workspace_context import read_context, workspace_url


SCAN_HISTORY_DB = Path("data/scanner_history.db")

SECTOR_HEAVYWEIGHTS: dict[str, list[str]] = {
    "Communication Services": ["GOOGL", "GOOG", "META", "NFLX"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD"],
    "Consumer Staples": ["WMT", "COST", "PG", "KO"],
    "Energy": ["XOM", "CVX", "COP", "SLB"],
    "Financials": ["BRK-B", "JPM", "V", "MA"],
    "Health Care": ["LLY", "JNJ", "UNH", "ABBV"],
    "Industrials": ["GE", "CAT", "RTX", "HON"],
    "Information Technology": ["MSFT", "NVDA", "AAPL", "AVGO"],
    "Materials": ["LIN", "SHW", "FCX", "ECL"],
    "Real Estate": ["PLD", "AMT", "EQIX", "WELL"],
    "Utilities": ["NEE", "SO", "DUK", "CEG"],
}


def render_sector_rotation_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    apply_relative_strength_theme(streamlit)
    url_context = read_context(getattr(streamlit, "query_params", {}))
    requested_date = url_context.get("as_of", "")
    requested_period = url_context.get("period", "")
    history_options = ["3mo", "6mo", "1y", "2y"]
    if requested_period and requested_period not in history_options:
        history_options.append(requested_period)
    if streamlit.session_state.get("sector_archive_url_period") != requested_period:
        if requested_period:
            streamlit.session_state["sector_history"] = requested_period
        streamlit.session_state["sector_archive_url_period"] = requested_period
    title, action = streamlit.columns([4, 1])
    title.subheader("Sector Archive")
    title.caption("11 S&P 500 sector ETFs / SPY benchmark. This is not an index-constituent universe scan.")
    refresh_clicked = action.button("Refresh Sector Dashboard", type="primary", width="stretch", disabled=bool(requested_date))
    if requested_date:
        streamlit.caption(f"Requested bar/session date: {requested_date}. Live refresh is disabled for dated views.")
        streamlit.link_button("Current sector context", workspace_url("sector_rotation", url_context, as_of=""))
    if url_context.get("universe") not in {None, "sp500"}:
        streamlit.warning(f"Requested universe {url_context['universe']} is not applied. Sector Archive covers the 11 S&P 500 sector ETFs versus SPY.")
    if url_context.get("etf"):
        streamlit.caption(f"ETF context {url_context['etf']} is not applied as a filter; the full sector ETF snapshot is shown.")

    with streamlit.expander("Data and scan settings", expanded=False):
        control_cols = streamlit.columns(3)
        period = control_cols[0].selectbox(
            "History",
            history_options,
            index=2,
            key="sector_history",
        )
        data_source = control_cols[1].selectbox(
            "Market Data",
            MARKET_DATA_PROVIDER_OPTIONS,
            index=provider_index(MARKET_DATA_PROVIDER_OPTIONS),
            key="sector_data_source",
        )
        min_score = control_cols[2].slider(
            "Candidate Rank Floor",
            0.0,
            1.0,
            0.55,
            0.05,
            key="sector_candidate_min_rank",
        )
        with streamlit.expander("Breadth and snapshot settings", expanded=False):
            setting_cols = streamlit.columns(2)
            compute_breadth = setting_cols[0].checkbox(
                "Compute S&P 500 Constituent Breadth",
                value=False,
                key="sector_compute_constituent_breadth",
            )
            save_snapshot = setting_cols[1].checkbox(
                "Save Snapshot On Refresh",
                value=True,
                key="sector_save_snapshot",
            )

    snapshot_repository = SQLiteSectorRotationRepository(SCAN_HISTORY_DB)
    context = (str(period), str(data_source), float(min_score), bool(compute_breadth))
    if refresh_clicked and not requested_date:
        provider = _SessionEvidenceProvider(build_fallback_market_data_provider(str(data_source)), refresh=True)
        with streamlit.spinner("Analyzing sector rotation..."):
            rotation = analyze_sector_rotation(provider, period=str(period))
            rotation_frame = sector_rotation_frame(rotation)
            evidence = provider.context([rotation.benchmark, *[row.etf for row in rotation.rows]],
                                        str(period), rotation.benchmark)
            rotation_frame.attrs["evidence"] = evidence
            candidates_frame = _compatible_candidates(_sector_candidates(min_score), evidence)
            heavyweight_frame = _heavyweight_confirmation(provider, period=str(period), rotation_frame=rotation_frame)
            breadth_frame = (
                _constituent_breadth(provider, period=str(period))
                if compute_breadth
                else _candidate_breadth(candidates_frame)
            )
            heavyweight_frame.attrs["evidence"] = provider.context(
                [rotation.benchmark, *[symbol for symbols in SECTOR_HEAVYWEIGHTS.values() for symbol in symbols]],
                str(period), rotation.benchmark,
            )
            if compute_breadth:
                breadth_frame.attrs["evidence"] = provider.context(
                    UniverseLoader().load("sp500"), str(period), rotation.benchmark,
                )
            if refresh_clicked and save_snapshot:
                snapshot_id = _save_sector_snapshot(
                    snapshot_repository,
                    rotation,
                    period=str(period),
                    data_source=str(data_source),
                    heavyweight_frame=heavyweight_frame,
                    breadth_frame=breadth_frame,
                    evidence=evidence,
                    candidates_frame=candidates_frame,
                )
                streamlit.success(f"Saved sector rotation snapshot {snapshot_id}.")
            rank_changes = snapshot_repository.compare_latest()
        streamlit.session_state["sector_board_frames"] = (rotation_frame, candidates_frame, heavyweight_frame, breadth_frame, rank_changes)
        streamlit.session_state["sector_board_context"] = context
        streamlit.session_state["sector_board_created_at"] = datetime.now(UTC).isoformat()
        _render_trusted_dashboard(streamlit, rotation_frame, candidates_frame, heavyweight_frame, breadth_frame,
                                  rank_changes, created_at=streamlit.session_state["sector_board_created_at"])
        return

    current = streamlit.session_state.get("sector_board_frames")
    if current is not None and not requested_date:
        if streamlit.session_state.get("sector_board_context") != context:
            streamlit.warning("Settings changed. Refresh to apply them; the previous result is not shown.")
            return
        _render_trusted_dashboard(streamlit, *current,
                                  created_at=streamlit.session_state.get("sector_board_created_at", ""))
        return

    latest = (
        _snapshot_for_session(snapshot_repository, requested_date, str(period))
        if requested_date else snapshot_repository.latest()
    )
    if latest is None:
        if requested_date:
            streamlit.warning(
                f"Historical sector data unavailable for {requested_date} / {period}: no snapshot with "
                "matching verified bar/session dates among the latest 200 saved snapshots. "
                "Creation dates and undated snapshots are not substitutes for dated bar evidence."
            )
            return
        streamlit.info("No saved sector rotation snapshot yet. Click Refresh Sector Dashboard to build the first one.")
        return

    streamlit.caption(
        f"Saved snapshot {latest.id} / created {format_timestamp(latest.created_at)} / "
        f"history: {latest.period} / requested source: {latest.data_source}"
    )
    if latest.period != str(period) or latest.data_source != str(data_source):
        streamlit.warning("Saved snapshot settings differ from the selected controls. Displaying the saved scope above.")
    rotation_frame, heavyweight_frame, breadth_frame = _frames_from_sector_snapshot(latest.payload)
    evidence = rotation_frame.attrs.get("evidence", {})
    extras = latest.payload.get("extras", {})
    candidates_frame = _records_frame(extras.get("scanner_candidates", []) if isinstance(extras, dict) else [])
    if isinstance(extras, dict):
        candidates_frame.attrs["evidence"] = extras.get("scanner_evidence", {})
    if _current_evidence(evidence):
        # Prefer attached lineage. Independently loaded scans must prove their own date/context.
        if candidates_frame.empty:
            candidates_frame = _sector_candidates(min_score)
        candidates_frame = _compatible_candidates(candidates_frame, evidence)
        if not candidates_frame.empty:
            candidates_frame = candidates_frame.loc[candidates_frame["rank_score"] >= min_score].copy()
    rank_changes = [] if requested_date else snapshot_repository.compare_latest()
    if requested_date:
        streamlit.caption("Latest-snapshot rank comparisons are withheld in this dated archive view.")
    _render_trusted_dashboard(streamlit, rotation_frame, candidates_frame, heavyweight_frame, breadth_frame,
                              rank_changes, created_at=latest.created_at)


def _snapshot_for_session(
    repository: SQLiteSectorRotationRepository, session_date: str, period: str,
) -> StoredSectorRotationSnapshot | None:
    for snapshot in repository.list_snapshots(limit=200):
        if snapshot.period != period or snapshot.payload.get("benchmark") != "SPY":
            continue
        rotation, _, _ = _frames_from_sector_snapshot(snapshot.payload)
        evidence = rotation.attrs.get("evidence", {})
        if (rotation.empty or "etf" not in rotation or not isinstance(evidence, dict)
                or not isinstance(evidence.get("symbols"), dict)):
            continue
        if (_matching_evidence(evidence, {"session_date": session_date, "period": period, "benchmark": "SPY"})
                and "SPY" in evidence["symbols"]
                and set(rotation["etf"]).issubset(evidence["symbols"])):
            return snapshot
    return None


def _frames_from_sector_snapshot(payload: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sectors = payload.get("sectors", [])
    extras = payload.get("extras", {})
    if not isinstance(sectors, list):
        sectors = []
    if not isinstance(extras, dict):
        extras = {}
    heavyweights = extras.get("heavyweights", [])
    breadth = extras.get("breadth", [])
    if not isinstance(heavyweights, list):
        heavyweights = []
    if not isinstance(breadth, list):
        breadth = []
    frames = _records_frame(sectors), _records_frame(heavyweights), _records_frame(breadth)
    for frame, key in zip(frames, ["evidence", "heavyweight_evidence", "breadth_evidence"], strict=True):
        frame.attrs["evidence"] = extras.get(key, {})
    return frames


def _records_frame(records: object) -> pd.DataFrame:
    return pd.DataFrame([row for row in records if isinstance(row, dict)]) if isinstance(records, list) else pd.DataFrame()


def _evidence_date(evidence: object) -> str:
    if not isinstance(evidence, dict):
        return ""
    try:
        return date.fromisoformat(str(evidence.get("session_date", ""))).isoformat()
    except ValueError:
        return ""


def _current_evidence(evidence: object, as_of: datetime | None = None) -> bool:
    if not isinstance(evidence, dict):
        return False
    symbols = evidence.get("symbols", {})
    return (
        bool(_evidence_date(evidence))
        and _evidence_date(evidence) == latest_completed_session(as_of or datetime.now(UTC))
        and isinstance(symbols, dict) and bool(symbols)
        and evidence.get("benchmark") in symbols
        and all(_evidence_date(item) == _evidence_date(evidence) for item in symbols.values())
    )


def _matching_evidence(left: object, right: object) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    for context in (left, right):
        symbols = context.get("symbols", {})
        if not isinstance(symbols, dict) or any(
            _evidence_date(item) != _evidence_date(context) for item in symbols.values()
        ):
            return False
    return bool(_evidence_date(left)) and all(
        left.get(key) and left.get(key) == right.get(key)
        for key in ("session_date", "benchmark", "period")
    )


def _compatible_candidates(candidates: pd.DataFrame, evidence: object) -> pd.DataFrame:
    context = candidates.attrs.get("evidence", {})
    required = {"symbol", "sector", "status", "rank_score", "session_date"}
    if (not _matching_evidence(context, evidence) or not isinstance(context, dict)
            or not context.get("scan_run_id") or not context.get("universe")
            or not required.issubset(candidates.columns)
            or not candidates["session_date"].eq(_evidence_date(evidence)).all()):
        return pd.DataFrame()
    scores = pd.to_numeric(candidates["rank_score"], errors="coerce")
    if not scores.between(0, 1).all() or candidates["symbol"].isna().any():
        return pd.DataFrame()
    result = candidates.copy()
    result["rank_score"] = scores
    return result


def _render_trusted_dashboard(
    streamlit: Any,
    rotation: pd.DataFrame,
    candidates: pd.DataFrame,
    heavyweights: pd.DataFrame,
    breadth: pd.DataFrame,
    rank_changes: list[SectorRankChange],
    *,
    created_at: str,
) -> None:
    evidence = rotation.attrs.get("evidence", {})
    session_date = _evidence_date(evidence)
    covered = (isinstance(evidence, dict) and isinstance(evidence.get("symbols"), dict)
               and "etf" in rotation and set(rotation["etf"]).issubset(evidence["symbols"]))
    if not _current_evidence(evidence) or not covered:
        streamlit.warning(
            f"Historical / unverified sector snapshot. Bar/session date: {session_date or 'not recorded'}; "
            f"created: {format_timestamp(created_at)}. Latest eligible session: "
            f"{latest_completed_session(datetime.now(UTC))}. Not current market evidence. "
            "Scanner candidates and breadth joins are withheld."
        )
        candidates, breadth = pd.DataFrame(), pd.DataFrame()
    else:
        streamlit.caption(f"Sector bar/session date: {session_date} / benchmark: {evidence.get('benchmark', 'unknown')}")
        candidates = _compatible_candidates(candidates, evidence)
        if candidates.empty:
            streamlit.warning("Scanner join withheld: no saved candidates with matching session date, benchmark, history, and run evidence.")
        else:
            context = candidates.attrs["evidence"]
            streamlit.caption(
                f"Scanner run {context['scan_run_id']} / candidate universe: {context['universe']} / "
                f"bar/session date: {session_date} / actual source: {context.get('actual_source', 'not recorded')}. "
                "Candidate subset, not full-universe breadth."
            )
        if not _matching_evidence(breadth.attrs.get("evidence"), evidence):
            breadth = _candidate_breadth(candidates)
    if not _matching_evidence(heavyweights.attrs.get("evidence"), evidence):
        heavyweights = pd.DataFrame()
    streamlit.caption("Heavyweights are configured representative baskets, not verified dated ETF holdings.")
    if isinstance(evidence, dict) and isinstance(evidence.get("symbols"), dict):
        sources = sorted({str(item.get("actual_source", "unknown")) for item in evidence["symbols"].values() if isinstance(item, dict)})
        streamlit.caption(f"Recorded sector actual sources: {', '.join(sources) or 'unknown'}")
        with streamlit.expander("Session and retrieval evidence"):
            rows = [{"symbol": symbol, **item} for symbol, item in evidence["symbols"].items() if isinstance(item, dict)]
            streamlit.dataframe(display_frame(pd.DataFrame(rows), columns=["symbol", "session_date", "actual_source", "retrieved_at"]),
                                width="stretch", hide_index=True)
    _render_sector_dashboard(streamlit, rotation, candidates, heavyweights, breadth, rank_changes)


class _SessionEvidenceProvider(CachedMarketDataProvider):
    """Pin one refresh to completed sessions and retain evidence for the exact inputs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.as_of = datetime.now(UTC)
        self.responses: dict[tuple[str, str], pd.DataFrame] = {}

    def get_daily_bars(self, request: BarDataRequest) -> pd.DataFrame:
        key = request.symbol, request.period
        if key not in self.responses:
            self.responses[key] = completed_mover_bars(super().get_daily_bars(request), self.as_of)
        return self.responses[key]

    def context(self, symbols: list[str], period: str, benchmark: str) -> dict[str, Any]:
        rows = {}
        for symbol in sorted(set(symbols)):
            bars = self.responses.get((symbol, period))
            if bars is None or bars.empty:
                return {}
            provenance = bars.attrs.get("provenance", {})
            rows[symbol] = {
                "session_date": bars.index[-1].date().isoformat(),
                "actual_source": provenance["actual_source"] if valid_provenance(provenance) else "unknown",
                "retrieved_at": datetime.fromisoformat(provenance["retrieved_at"]).astimezone(UTC).isoformat()
                if valid_provenance(provenance) else None,
            }
        dates = {row["session_date"] for row in rows.values()}
        return {"session_date": dates.pop(), "benchmark": benchmark, "period": period, "symbols": rows} if len(dates) == 1 else {}


def _render_sector_dashboard(
    streamlit: Any,
    rotation_frame: pd.DataFrame,
    candidates_frame: pd.DataFrame,
    heavyweight_frame: pd.DataFrame,
    breadth_frame: pd.DataFrame,
    rank_changes: list[SectorRankChange],
) -> None:
    if rotation_frame.empty:
        streamlit.info("No sector ETF data available.")
        return

    selected = streamlit.selectbox(
        "Sector view",
        [
            "Overview",
            "Money Flow Map",
            "Rotation Matrix",
            "Flow Map",
            "Breadth",
            "Heavyweights",
            "Sector Watchlist",
            "Heatmap",
            "History",
            "Diagnostics",
        ]
    )
    if selected == "Overview":
        render_sector_board(streamlit, rotation_frame, candidates_frame)
    elif selected == "Money Flow Map":
        _render_money_flow_map(streamlit, rotation_frame)
    elif selected == "Rotation Matrix":
        _render_rotation_matrix(streamlit, rotation_frame)
    elif selected == "Flow Map":
        _render_flow_map(streamlit, rotation_frame)
    elif selected == "Breadth":
        _render_breadth(streamlit, breadth_frame)
    elif selected == "Heavyweights":
        _render_heavyweights(streamlit, heavyweight_frame)
    elif selected == "Sector Watchlist":
        _render_sector_watchlist(streamlit, rotation_frame, candidates_frame, breadth_frame, heavyweight_frame)
    elif selected == "Heatmap":
        _render_candidate_heatmap(streamlit, candidates_frame)
    elif selected == "History":
        _render_history(streamlit, rank_changes)
    elif selected == "Diagnostics":
        streamlit.dataframe(display_frame(rotation_frame), width="stretch", hide_index=True)


def _render_flow_summary(streamlit: Any, rotation_frame: pd.DataFrame) -> None:
    leaders = rotation_frame.head(3)
    improving = rotation_frame[rotation_frame["rotation_status"].isin(["Improving", "Early Turn"])].head(3)
    lagging = rotation_frame[rotation_frame["rotation_status"].isin(["Lagging", "Losing Momentum"])].tail(3)
    flow_note = _flow_note(rotation_frame)

    cols = streamlit.columns(4)
    cols[0].metric("Current Leadership", _sector_list(leaders), f"{float(leaders['relative_20d'].mean()):.1%} avg 1M vs SPY")
    cols[1].metric("Improving Now", _sector_list(improving), f"{len(improving)} sectors")
    cols[2].metric("Avoid / Outflow", _sector_list(lagging), f"{len(lagging)} sectors")
    cols[3].metric("Market Tone", flow_note["label"], flow_note["detail"])


def _render_rotation_lens(streamlit: Any, rotation_frame: pd.DataFrame) -> None:
    streamlit.write("**Money Flow Snapshot**")
    lens = _rotation_lens_summary(rotation_frame)
    cols = streamlit.columns(5)
    for index, row in enumerate(lens[:5]):
        cols[index].metric(row["lens"], row["sector"], row["detail"])

    streamlit.write("**Sector Decision Board**")
    streamlit.caption(
        "One row per sector. Use this first: leadership identifies where money is working, "
        "action translates the tape into what to do next."
    )
    decision_frame = _sector_decision_board(rotation_frame)
    streamlit.dataframe(
        display_frame(decision_frame, columns=sector_decision_columns()),
        width="stretch",
        hide_index=True,
    )


def sector_decision_columns() -> list[str]:
    return [
        "sector",
        "etf",
        "group",
        "rotation_status",
        "sector_action",
        "relative_5d",
        "relative_20d",
        "relative_60d",
        "acceleration",
        "leadership_score",
        "extension_risk_score",
        "rsi_14",
    ]


def _sector_decision_board(rotation_frame: pd.DataFrame) -> pd.DataFrame:
    if rotation_frame.empty:
        return rotation_frame
    frame = rotation_frame.copy()
    frame["sector_action"] = frame.apply(_sector_action_from_row, axis=1)
    return frame[[column for column in sector_decision_columns() if column in frame.columns]].sort_values(
        ["leadership_score", "acceleration", "relative_20d"],
        ascending=False,
    )


def _rotation_lens_summary(rotation_frame: pd.DataFrame) -> list[dict[str, str]]:
    if rotation_frame.empty:
        return []
    weekly = rotation_frame.sort_values(["relative_5d", "acceleration"], ascending=False).iloc[0]
    monthly = rotation_frame.sort_values(["relative_20d", "leadership_score"], ascending=False).iloc[0]
    quarterly = rotation_frame.sort_values(["relative_60d", "leadership_score"], ascending=False).iloc[0]
    institutional = rotation_frame.sort_values(["leadership_score", "acceleration"], ascending=False).iloc[0]
    crowded = rotation_frame.sort_values(["extension_risk_score", "distance_from_sma20"], ascending=False).iloc[0]
    return [
        _lens_row("1W Flow", weekly, "relative_5d"),
        _lens_row("1M Flow", monthly, "relative_20d"),
        _lens_row("1Q Flow", quarterly, "relative_60d"),
        _lens_row("Institutional Focus", institutional, "leadership_score"),
        _lens_row("Crowding Risk", crowded, "extension_risk_score"),
    ]


def _lens_row(label: str, row: pd.Series, metric: str) -> dict[str, str]:
    value = float(row.get(metric, 0.0) or 0.0)
    if metric in {"leadership_score", "extension_risk_score"}:
        value_text = f"{value:.2f}"
    else:
        value_text = f"{value:.1%}"
    return {
        "lens": label,
        "sector": str(row.get("sector", "Unknown")),
        "etf": str(row.get("etf", "")),
        "status": str(row.get("rotation_status", "Unknown")),
        "value": value_text,
        "detail": f"{row.get('rotation_status', 'Unknown')} | {metric} {value_text}",
    }


def _render_money_flow_map(streamlit: Any, rotation_frame: pd.DataFrame) -> None:
    streamlit.write("**Weekly acceleration vs monthly relative strength**")
    streamlit.caption("Upper-right sectors are outperforming SPY and still accelerating. Lower-left sectors are lagging.")
    scatter = px.scatter(
        rotation_frame,
        x="relative_20d",
        y="acceleration",
        size="leadership_score",
        color="rotation_status",
        hover_name="sector",
        hover_data=["etf", "group", "relative_5d", "relative_20d", "relative_60d", "above_sma50"],
        title="Sector Money Flow Quadrant",
    )
    scatter.add_vline(x=0, line_dash="dash", line_color="#94a3b8")
    scatter.add_hline(y=0, line_dash="dash", line_color="#94a3b8")
    streamlit.plotly_chart(scatter, width="stretch")

    bar = px.bar(
        rotation_frame.sort_values("relative_20d", ascending=False),
        x="sector",
        y=["relative_5d", "relative_20d", "relative_60d"],
        title="Relative Returns vs SPY: 1 Week, 1 Month, 1 Quarter",
        barmode="group",
    )
    streamlit.plotly_chart(bar, width="stretch")


def _render_rotation_matrix(streamlit: Any, rotation_frame: pd.DataFrame) -> None:
    matrix = rotation_frame.set_index("sector")[["relative_5d", "relative_20d", "relative_60d", "acceleration"]]
    matrix = matrix.rename(
        columns={
            "relative_5d": "1W vs SPY",
            "relative_20d": "1M vs SPY",
            "relative_60d": "1Q vs SPY",
            "acceleration": "Acceleration",
        }
    )
    heatmap = px.imshow(
        matrix,
        aspect="auto",
        color_continuous_scale="RdYlGn",
        title="Sector Rotation Matrix",
        labels={"color": "Relative return"},
    )
    streamlit.plotly_chart(heatmap, width="stretch")

    group_frame = (
        rotation_frame.groupby("group", dropna=False)
        .agg(
            sectors=("sector", "count"),
            avg_relative_20d=("relative_20d", "mean"),
            avg_acceleration=("acceleration", "mean"),
            avg_leadership=("leadership_score", "mean"),
        )
        .reset_index()
        .sort_values(["avg_leadership", "avg_acceleration"], ascending=False)
        .round(4)
    )
    streamlit.write("**Theme groups**")
    streamlit.dataframe(display_frame(group_frame), width="stretch", hide_index=True)


def _render_flow_map(streamlit: Any, rotation_frame: pd.DataFrame) -> None:
    streamlit.write("**Probable Rotation Flow**")
    streamlit.caption(
        "This is an inferred flow map from relative performance and acceleration. It is not fund-flow data."
    )

    flow_frame = _probable_rotation_flows(rotation_frame)
    if flow_frame.empty:
        streamlit.info("No clear rotation flow is visible yet.")
    else:
        streamlit.dataframe(display_frame(flow_frame), width="stretch", hide_index=True)

    action_frame = _sector_action_board(rotation_frame)
    streamlit.write("**Sector Action Board**")
    streamlit.dataframe(display_frame(action_frame), width="stretch", hide_index=True)


def _render_sector_watchlist(
    streamlit: Any,
    rotation_frame: pd.DataFrame,
    candidates_frame: pd.DataFrame,
    breadth_frame: pd.DataFrame,
    heavyweight_frame: pd.DataFrame,
) -> None:
    streamlit.write("**Scanner Candidates By Sector**")
    if candidates_frame.empty:
        streamlit.info("No saved scanner candidates match this score.")
        return

    sector_summary = (
        candidates_frame.groupby("sector", dropna=False)
        .agg(
            candidates=("symbol", "count"),
            avg_rank=("rank_score", "mean"),
            near_breakout=("status", lambda values: int((values == "Near Breakout").sum())),
        )
        .reset_index()
        .merge(
            rotation_frame[
                [
                    "sector",
                    "group",
                    "relative_20d",
                    "acceleration",
                    "rotation_status",
                    "leadership_score",
                    "extension_risk_score",
                ]
            ],
            on="sector",
            how="left",
        )
    )
    if "breadth_score" in breadth_frame.columns:
        sector_summary = sector_summary.merge(breadth_frame[["sector", "breadth_score"]], on="sector", how="left")
    else:
        sector_summary["breadth_score"] = 0.0
    if "heavyweight_score" in heavyweight_frame.columns:
        sector_summary = sector_summary.merge(
            heavyweight_frame[["sector", "heavyweight_score"]],
            on="sector",
            how="left",
        )
    else:
        sector_summary["heavyweight_score"] = 0.0
    sector_summary["institutional_focus"] = (
        (sector_summary["leadership_score"].fillna(0.0) * 0.55)
        + (sector_summary["avg_rank"].fillna(0.0) * 0.20)
        + (sector_summary["breadth_score"].fillna(0.0) * 0.10)
        + (sector_summary["heavyweight_score"].fillna(0.0) * 0.10)
        + ((sector_summary["near_breakout"].fillna(0) / sector_summary["candidates"].clip(lower=1)) * 0.05)
    )
    sector_summary["sector_action"] = sector_summary.apply(_sector_action_from_row, axis=1)
    sector_summary = sector_summary.sort_values(
        ["institutional_focus", "candidates"],
        ascending=False,
    ).round(3)
    streamlit.dataframe(display_frame(sector_summary), width="stretch", hide_index=True)

    selected_sector = streamlit.selectbox(
        "Sector candidate detail",
        ["All", *sector_summary["sector"].dropna().astype(str).tolist()],
    )
    detail = candidates_frame if selected_sector == "All" else candidates_frame[candidates_frame["sector"] == selected_sector]
    streamlit.dataframe(display_frame(detail), width="stretch", hide_index=True)


def _render_breadth(streamlit: Any, breadth_frame: pd.DataFrame) -> None:
    streamlit.write("**Sector Breadth**")
    if breadth_frame.empty:
        streamlit.info("No breadth data available.")
        return
    candidate_subset = "near_breakout_pct" in breadth_frame
    streamlit.caption(
        "Candidate subset only; denominator is saved candidates passing the rank floor."
        if candidate_subset else "Constituent breadth; denominator is successfully checked constituents."
    )
    chart = px.bar(
        breadth_frame.sort_values("breadth_score", ascending=False),
        x="sector",
        y=["near_breakout_pct"] if candidate_subset else ["above_sma50_pct", "above_sma200_pct", "positive_20d_pct"],
        barmode="group",
        title="Candidate Near-Breakout Share" if candidate_subset else "Constituent Breadth",
    )
    streamlit.plotly_chart(chart, width="stretch")
    streamlit.dataframe(display_frame(breadth_frame), width="stretch", hide_index=True)


def _render_heavyweights(streamlit: Any, heavyweight_frame: pd.DataFrame) -> None:
    streamlit.write("**Heavyweight Confirmation**")
    streamlit.caption(
        "A sector leader is more reliable when its largest liquid constituents confirm the ETF move."
    )
    if heavyweight_frame.empty:
        streamlit.info("No heavyweight confirmation data available.")
        return
    chart = px.bar(
        heavyweight_frame.sort_values("heavyweight_score", ascending=False),
        x="sector",
        y="heavyweight_score",
        color="confirmation_status",
        title="Heavyweight Confirmation Score",
    )
    streamlit.plotly_chart(chart, width="stretch")
    streamlit.dataframe(display_frame(heavyweight_frame), width="stretch", hide_index=True)


def _render_history(streamlit: Any, rank_changes: list[SectorRankChange]) -> None:
    streamlit.write("**Latest Saved Rank Changes**")
    if not rank_changes:
        streamlit.info("Save at least two sector snapshots to compare rank changes.")
        return
    frame = pd.DataFrame(
        [
            {
                "sector": change.sector,
                "current_rank": change.current_rank,
                "previous_rank": change.previous_rank,
                "rank_change": change.rank_change,
                "current_status": change.current_status,
                "previous_status": change.previous_status,
                "current_score": change.current_score,
                "previous_score": change.previous_score,
            }
            for change in rank_changes
        ]
    )
    streamlit.dataframe(display_frame(frame), width="stretch", hide_index=True)


def _render_candidate_heatmap(streamlit: Any, candidates_frame: pd.DataFrame) -> None:
    if candidates_frame.empty:
        streamlit.info("No saved scanner candidates match this score.")
        return
    heatmap = px.treemap(
        candidates_frame,
        path=["sector", "quality", "symbol"],
        values="rank_score",
        color="distance_to_resistance",
        color_continuous_scale="RdYlGn_r",
        title="Sector Watchlist Heatmap",
    )
    streamlit.plotly_chart(heatmap, width="stretch")


def _sector_list(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "None"
    return ", ".join(str(sector) for sector in frame["sector"].head(3))


def _flow_note(rotation_frame: pd.DataFrame) -> dict[str, str]:
    group_scores = rotation_frame.groupby("group")["leadership_score"].mean()
    defensive = float(group_scores.reindex(["Defensive"]).fillna(0.0).sum())
    growth = float(group_scores.reindex(["Growth"]).fillna(0.0).sum())
    cyclical = float(group_scores.reindex(["Cyclical", "Value/Cyclical"]).fillna(0.0).mean())
    if growth > defensive and cyclical > defensive:
        return {"label": "Risk On", "detail": "growth/cyclicals leading"}
    if defensive > growth and defensive > cyclical:
        return {"label": "Defensive", "detail": "staples/health/utilities bid"}
    if cyclical > growth:
        return {"label": "Value Rotation", "detail": "cyclicals/value improving"}
    return {"label": "Mixed", "detail": "no clear sector flow"}


def _probable_rotation_flows(rotation_frame: pd.DataFrame) -> pd.DataFrame:
    if rotation_frame.empty:
        return pd.DataFrame()

    frame = rotation_frame.copy()
    frame["outflow_pressure"] = (
        (-frame["relative_20d"].clip(upper=0.0) * 0.45)
        + (-frame["acceleration"].clip(upper=0.0) * 0.35)
        + ((1.0 - frame["leadership_score"].clip(0.0, 1.0)) * 0.20)
    )
    frame["inflow_pressure"] = (
        (frame["relative_20d"].clip(lower=0.0) * 0.40)
        + (frame["acceleration"].clip(lower=0.0) * 0.35)
        + (frame["leadership_score"].clip(0.0, 1.0) * 0.25)
    )

    sources = frame.sort_values(["outflow_pressure", "relative_20d"], ascending=[False, True]).head(3)
    destinations = frame.sort_values(["inflow_pressure", "acceleration"], ascending=[False, False]).head(3)
    rows = []
    for source, destination in zip(sources.to_dict("records"), destinations.to_dict("records"), strict=False):
        if source["sector"] == destination["sector"]:
            continue
        confidence = min(
            1.0,
            max(0.0, float(destination["inflow_pressure"]) + float(source["outflow_pressure"])),
        )
        rows.append(
            {
                "from_sector": source["sector"],
                "from_status": source["rotation_status"],
                "to_sector": destination["sector"],
                "to_status": destination["rotation_status"],
                "confidence": round(confidence, 3),
                "evidence": _flow_evidence(source, destination),
            }
        )
    return pd.DataFrame(rows)


def _sector_action_board(rotation_frame: pd.DataFrame) -> pd.DataFrame:
    frame = rotation_frame.copy()
    frame["sector_action"] = frame.apply(_sector_action_from_row, axis=1)
    columns = [
        "sector",
        "etf",
        "group",
        "rotation_status",
        "relative_5d",
        "relative_20d",
        "relative_60d",
        "acceleration",
        "extension_risk_score",
        "distance_from_sma20",
        "rsi_14",
        "leadership_score",
        "sector_action",
    ]
    return frame[[column for column in columns if column in frame.columns]].sort_values(
        ["leadership_score", "acceleration"],
        ascending=False,
    )


def _sector_action_from_row(row: pd.Series) -> str:
    status = str(row.get("rotation_status", "Neutral"))
    acceleration = float(row.get("acceleration", 0.0) or 0.0)
    relative_20d = float(row.get("relative_20d", 0.0) or 0.0)
    extension_risk = float(row.get("extension_risk_score", 0.0) or 0.0)

    if extension_risk >= 0.60:
        return "Extended: wait pullback"
    if status == "Leading" and acceleration >= 0:
        return "Favor pullbacks"
    if status == "Leading" and acceleration < 0:
        return "Leader, avoid chase"
    if status in {"Improving", "Early Turn"}:
        return "Build watchlist"
    if status == "Losing Momentum":
        return "Tighten risk"
    if status == "Lagging" or relative_20d < -0.03:
        return "Avoid for longs"
    return "Monitor"


def _flow_evidence(source: dict[Any, Any], destination: dict[Any, Any]) -> str:
    return (
        f"{source['sector']} weakening "
        f"({float(source['relative_20d']):.1%} 1M vs SPY, {float(source['acceleration']):.1%} accel); "
        f"{destination['sector']} improving "
        f"({float(destination['relative_20d']):.1%} 1M vs SPY, {float(destination['acceleration']):.1%} accel)"
    )


def _heavyweight_confirmation(
    provider: CachedMarketDataProvider,
    *,
    period: str,
    rotation_frame: pd.DataFrame,
) -> pd.DataFrame:
    spy_20d = _symbol_return_20d(provider, "SPY", period)
    rotation_status = rotation_frame.set_index("sector")["rotation_status"].to_dict()
    rows = []

    def check_symbol(symbol: str) -> tuple[str, bool | None]:
        try:
            bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
            close = float(bars["close"].iloc[-1])
            sma50 = float(bars["close"].rolling(50).mean().dropna().iloc[-1])
            return_20d = _return_over_bars(bars, 20)
            return symbol, close > sma50 and return_20d >= spy_20d
        except Exception:
            return symbol, None

    for sector, symbols in SECTOR_HEAVYWEIGHTS.items():
        details = []
        confirmed = 0
        total = 0
        with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as executor:
            futures = [executor.submit(check_symbol, symbol) for symbol in symbols]
            results = {}
            for future in as_completed(futures):
                symbol_result, confirmed_result = future.result()
                results[symbol_result] = confirmed_result
        for symbol in symbols:
            is_confirmed = results.get(symbol)
            if is_confirmed is None:
                details.append(f"{symbol}:NA")
            else:
                confirmed += int(is_confirmed)
                total += 1
                details.append(f"{symbol}:{'Y' if is_confirmed else 'N'}")
        score = confirmed / total if total else 0.0
        rows.append(
            {
                "sector": sector,
                "rotation_status": rotation_status.get(sector, "Unknown"),
                "confirmed_heavyweights": confirmed,
                "total_heavyweights": total,
                "heavyweight_score": round(score, 3),
                "confirmation_status": _confirmation_status(score),
                "heavyweight_detail": ", ".join(details),
            }
        )
    return pd.DataFrame(rows)


def _candidate_breadth(candidates_frame: pd.DataFrame) -> pd.DataFrame:
    if candidates_frame.empty:
        return pd.DataFrame()
    rows = []
    for sector, group in candidates_frame.groupby("sector", dropna=False):
        candidate_count = len(group)
        near_breakout_pct = float((group["status"] == "Near Breakout").mean()) if candidate_count else 0.0
        score = min(1.0, float(group["rank_score"].mean()) * 0.70 + near_breakout_pct * 0.30)
        rows.append(
            {
                "sector": sector,
                "breadth_source": "saved scanner candidate subset (not universe breadth)",
                "constituents_checked": candidate_count,
                "near_breakout_pct": near_breakout_pct,
                "breadth_score": round(score, 3),
                "breadth_status": _breadth_status(score),
            }
        )
    result = pd.DataFrame(rows)
    result.attrs["evidence"] = candidates_frame.attrs.get("evidence", {})
    return result


def _constituent_breadth(provider: CachedMarketDataProvider, *, period: str) -> pd.DataFrame:
    metadata = SymbolMetadataStore()
    symbols = UniverseLoader().load("sp500")
    by_sector: dict[str, list[str]] = {}
    for symbol in symbols:
        sector = metadata.get(symbol).sector
        by_sector.setdefault(sector, []).append(symbol)

    def check_symbol(symbol: str) -> tuple[str, int, int, int, int]:
        sector = metadata.get(symbol).sector
        try:
            bars = provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period))
            if len(bars) < 200:
                return sector, 0, 0, 0, 0
            close = float(bars["close"].iloc[-1])
            above50 = int(close > float(bars["close"].rolling(50).mean().dropna().iloc[-1]))
            above200 = int(close > float(bars["close"].rolling(200).mean().dropna().iloc[-1]))
            positive20 = int(_return_over_bars(bars, 20) > 0)
            return sector, above50, above200, positive20, 1
        except Exception:
            return sector, 0, 0, 0, 0

    sector_totals = {
        sector: {"above50": 0, "above200": 0, "positive20": 0, "checked": 0}
        for sector in by_sector
    }
    with ThreadPoolExecutor(max_workers=min(16, len(symbols) or 1)) as executor:
        future_by_symbol = {executor.submit(check_symbol, symbol): symbol for symbol in symbols}
        for future in as_completed(future_by_symbol):
            sector, above50, above200, positive20, checked = future.result()
            totals = sector_totals.setdefault(sector, {"above50": 0, "above200": 0, "positive20": 0, "checked": 0})
            totals["above50"] += above50
            totals["above200"] += above200
            totals["positive20"] += positive20
            totals["checked"] += checked

    rows = []
    for sector in by_sector:
        totals = sector_totals.get(sector, {})
        above50 = int(totals.get("above50", 0))
        above200 = int(totals.get("above200", 0))
        positive20 = int(totals.get("positive20", 0))
        checked = int(totals.get("checked", 0))
        above50_pct = above50 / checked if checked else 0.0
        above200_pct = above200 / checked if checked else 0.0
        positive20_pct = positive20 / checked if checked else 0.0
        score = (above50_pct * 0.40) + (above200_pct * 0.35) + (positive20_pct * 0.25)
        rows.append(
            {
                "sector": sector,
                "breadth_source": "S&P 500 constituents",
                "constituents_checked": checked,
                "above_sma50_pct": round(above50_pct, 3),
                "above_sma200_pct": round(above200_pct, 3),
                "positive_20d_pct": round(positive20_pct, 3),
                "breadth_score": round(score, 3),
                "breadth_status": _breadth_status(score),
            }
        )
    return pd.DataFrame(rows).sort_values("breadth_score", ascending=False)


def _save_sector_snapshot(
    repository: SQLiteSectorRotationRepository,
    rotation: SectorRotationResult,
    *,
    period: str,
    data_source: str,
    heavyweight_frame: pd.DataFrame,
    breadth_frame: pd.DataFrame,
    evidence: dict[str, Any] | None = None,
    candidates_frame: pd.DataFrame | None = None,
) -> int:
    return repository.save(
        rotation,
        source="sector_rotation_page",
        period=period,
        data_source=data_source,
        extras={
            "heavyweights": heavyweight_frame.to_dict(orient="records"),
            "breadth": breadth_frame.to_dict(orient="records"),
            "evidence": evidence or {},
            "heavyweight_evidence": heavyweight_frame.attrs.get("evidence", {}),
            "breadth_evidence": breadth_frame.attrs.get("evidence", {}),
            "scanner_candidates": candidates_frame.to_dict(orient="records") if candidates_frame is not None else [],
            "scanner_evidence": candidates_frame.attrs.get("evidence", {}) if candidates_frame is not None else {},
        },
    )


def _symbol_return_20d(provider: CachedMarketDataProvider, symbol: str, period: str) -> float:
    try:
        return _return_over_bars(provider.get_daily_bars(BarDataRequest(symbol=symbol, period=period)), 20)
    except Exception:
        return 0.0


def _return_over_bars(bars: pd.DataFrame, bars_back: int) -> float:
    if len(bars) <= bars_back:
        return 0.0
    previous = float(bars["close"].iloc[-bars_back - 1])
    if previous <= 0:
        return 0.0
    return (float(bars["close"].iloc[-1]) / previous) - 1.0


def _confirmation_status(score: float) -> str:
    if score >= 0.75:
        return "Confirmed"
    if score >= 0.50:
        return "Mixed"
    return "Weak"


def _breadth_status(score: float) -> str:
    if score >= 0.70:
        return "Broad Participation"
    if score >= 0.45:
        return "Mixed Breadth"
    return "Narrow / Weak"


def _sector_candidates(min_score: float) -> pd.DataFrame:
    metadata = SymbolMetadataStore()
    repository = SQLiteScanRepository(SCAN_HISTORY_DB)
    runs = repository.list_scan_runs(limit=1)
    if not runs:
        return pd.DataFrame()
    candidates = [
        candidate
        for candidate in repository.load_candidates(runs[0].id)
        if composite_rank_score(candidate) >= min_score
    ]
    symbols = [candidate.symbol for candidate in candidates]
    metadata_by_symbol = {symbol: metadata.get(symbol) for symbol in symbols}
    frame = pd.DataFrame(
        [
            {
                "symbol": candidate.symbol,
                "sector": metadata_by_symbol[candidate.symbol].sector,
                "industry": metadata_by_symbol[candidate.symbol].industry,
                "quality": candidate.quality_label,
                "status": candidate.setup_status,
                "rank_score": round(composite_rank_score(candidate), 3),
                "distance_to_resistance": round(candidate.metrics.resistance_distance_pct, 4),
            }
            for candidate in candidates
        ]
    )
    # Legacy scan payloads contain no bar date, benchmark, period, or universe evidence.
    # Creation time must never fill those gaps; the join gate will withhold these rows.
    frame.attrs["evidence"] = {"scan_run_id": runs[0].id, "created_at": runs[0].created_at}
    return frame


run_standalone_page(
    "Sector Archive",
    "Saved evidence for 11 S&P 500 sector ETFs versus SPY.",
    render_sector_rotation_page,
)
