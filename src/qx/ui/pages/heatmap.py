from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px  # type: ignore[import-untyped]

from qx.data.metadata import SymbolMetadataStore
from qx.models.scan import ScanCandidate
from qx.patterns.ranking import composite_rank_score
from qx.storage.sqlite import SQLiteScanRepository
from qx.ui.app_shell import ensure_app_styles, run_standalone_page
from qx.ui.formatting import display_frame


SCAN_HISTORY_DB = Path("data/scanner_history.db")
HEATMAP_METADATA_ENRICH_LIMIT = 100


def render_heatmap_page(streamlit: Any) -> None:
    ensure_app_styles(streamlit)
    min_score = streamlit.sidebar.slider("Heatmap min score", 0.0, 1.0, 0.50, 0.05)
    repository = SQLiteScanRepository(SCAN_HISTORY_DB)
    candidates = [
        candidate
        for candidate in repository.latest_candidates()
        if composite_rank_score(candidate) >= min_score
    ]

    streamlit.subheader("Rectangle Heatmap")
    if not candidates:
        streamlit.info("No saved candidates match this score. Run a scan first or lower the score.")
        return

    frame = heatmap_candidates_frame(candidates, max_metadata_enrichment=HEATMAP_METADATA_ENRICH_LIMIT)

    fig = px.treemap(
        frame,
        path=["sector", "quality", "setup_status", "symbol"],
        values="rank_score",
        color="readiness_score",
        color_continuous_scale="RdYlGn",
        hover_data={
            "setup_score": ":.2f",
            "pattern_score": ":.2f",
            "range_pct": ":.2%",
            "distance_to_resistance": ":.2%",
        },
    )
    fig.update_layout(margin={"t": 20, "l": 10, "r": 10, "b": 10})
    streamlit.plotly_chart(fig, width="stretch")
    streamlit.dataframe(
        display_frame(frame.sort_values("rank_score", ascending=False), max_rows=100),
        width="stretch",
        hide_index=True,
    )


def heatmap_candidates_frame(
    candidates: list[ScanCandidate],
    *,
    metadata_store: SymbolMetadataStore | None = None,
    max_metadata_enrichment: int = HEATMAP_METADATA_ENRICH_LIMIT,
) -> pd.DataFrame:
    metadata_store = metadata_store or SymbolMetadataStore()
    symbols = [candidate.symbol for candidate in candidates]
    metadata_store.enrich_yfinance(symbols, max_symbols=max_metadata_enrichment)
    metadata_by_symbol = {symbol: metadata_store.get(symbol) for symbol in symbols}

    frame = pd.DataFrame(
        [
            {
                "symbol": candidate.symbol,
                "sector": metadata_by_symbol[candidate.symbol].sector,
                "industry": metadata_by_symbol[candidate.symbol].industry,
                "quality": candidate.quality_label,
                "setup_status": candidate.setup_status,
                "rank_score": composite_rank_score(candidate),
                "setup_score": candidate.setup_score,
                "pattern_score": candidate.pattern_score,
                "readiness_score": candidate.readiness_score,
                "range_pct": candidate.metrics.range_pct,
                "distance_to_resistance": candidate.metrics.resistance_distance_pct,
            }
            for candidate in candidates
        ]
    )
    return frame


run_standalone_page(
    "Heatmap",
    "Visualize the latest saved scan by score, quality, and setup status.",
    render_heatmap_page,
)
