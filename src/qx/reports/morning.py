from dataclasses import dataclass

import pandas as pd

from qx.data.metadata import SymbolMetadataStore
from qx.models.scan import ScanCandidate
from qx.patterns.ranking import composite_rank_score, sort_candidates
from qx.storage.sqlite import SQLiteScanRepository, StoredScanRun


@dataclass(frozen=True)
class MorningReport:
    run: StoredScanRun | None
    previous_run: StoredScanRun | None
    top_candidates: list[ScanCandidate]
    new_candidates: list[ScanCandidate]
    improving_candidates: list[ScanCandidate]
    near_breakout_candidates: list[ScanCandidate]
    extended_leaders: list[ScanCandidate]
    damaged_candidates: list[ScanCandidate]


def build_morning_report(
    repository: SQLiteScanRepository,
    *,
    min_rank_score: float = 0.55,
    limit: int = 25,
) -> MorningReport:
    runs = repository.list_scan_runs(limit=2)
    if not runs:
        return MorningReport(None, None, [], [], [], [], [], [])

    current_run = runs[0]
    previous_run = runs[1] if len(runs) > 1 else None
    current = repository.load_candidates(current_run.id)
    previous = repository.load_candidates(previous_run.id) if previous_run else []
    previous_by_symbol = {candidate.symbol: candidate for candidate in previous}

    eligible = [
        candidate for candidate in current if composite_rank_score(candidate) >= min_rank_score
    ]
    top_candidates = sort_candidates(eligible)[:limit]
    new_candidates = [
        candidate for candidate in top_candidates if candidate.symbol not in previous_by_symbol
    ]
    improving_candidates = [
        candidate
        for candidate in top_candidates
        if _score_change(candidate, previous_by_symbol) >= 0.05
    ]
    near_breakout_candidates = [
        candidate
        for candidate in top_candidates
        if candidate.setup_status in {"Near Breakout", "Breakout"}
        and not _is_weekly_extended(candidate)
    ]
    extended_leaders = [
        candidate for candidate in top_candidates if _is_weekly_extended(candidate)
    ]
    damaged_candidates = [
        candidate
        for candidate in top_candidates
        if candidate.weekly_context is not None and candidate.weekly_context.status == "Damaged"
    ]

    return MorningReport(
        run=current_run,
        previous_run=previous_run,
        top_candidates=top_candidates,
        new_candidates=new_candidates[:limit],
        improving_candidates=improving_candidates[:limit],
        near_breakout_candidates=near_breakout_candidates[:limit],
        extended_leaders=extended_leaders[:limit],
        damaged_candidates=damaged_candidates[:limit],
    )


def morning_report_frame(
    candidates: list[ScanCandidate],
    metadata_store: SymbolMetadataStore | None = None,
) -> pd.DataFrame:
    metadata = metadata_store or SymbolMetadataStore()
    return pd.DataFrame(
        [
            {
                "symbol": candidate.symbol,
                "sector": metadata.get(candidate.symbol).sector,
                "industry": metadata.get(candidate.symbol).industry,
                "quality": candidate.quality_label,
                "status": candidate.setup_status,
                "rank_score": round(composite_rank_score(candidate), 3),
                "setup_score": round(candidate.setup_score, 3),
                "pattern_score": round(candidate.pattern_score, 3),
                "readiness_score": round(candidate.readiness_score, 3),
                "mtf_score": round(candidate.multi_timeframe_score, 3),
                "weekly_status": (
                    candidate.weekly_context.status if candidate.weekly_context else "Unknown"
                ),
                "distance_to_resistance": round(candidate.metrics.resistance_distance_pct, 4),
                "range_pct": round(candidate.metrics.range_pct, 4),
                "relative_volume_20d": round(candidate.metrics.relative_volume_20d, 3),
                "missing": ", ".join(candidate.failed_rule_names[:3]),
            }
            for candidate in candidates
        ]
    )


def sector_summary_frame(
    candidates: list[ScanCandidate],
    metadata_store: SymbolMetadataStore | None = None,
) -> pd.DataFrame:
    frame = morning_report_frame(candidates, metadata_store)
    if frame.empty:
        return frame
    return (
        frame.groupby("sector", dropna=False)
        .agg(
            candidates=("symbol", "count"),
            avg_rank_score=("rank_score", "mean"),
            avg_setup_score=("setup_score", "mean"),
            near_breakout=("status", lambda values: int((values == "Near Breakout").sum())),
            extended=("weekly_status", lambda values: int((values == "Extended Leader").sum())),
        )
        .reset_index()
        .sort_values(["avg_rank_score", "candidates"], ascending=False)
        .round(3)
    )


def _score_change(candidate: ScanCandidate, previous_by_symbol: dict[str, ScanCandidate]) -> float:
    previous = previous_by_symbol.get(candidate.symbol)
    if previous is None:
        return 0.0
    return candidate.setup_score - previous.setup_score


def _is_weekly_extended(candidate: ScanCandidate) -> bool:
    return candidate.weekly_context is not None and candidate.weekly_context.is_extended
