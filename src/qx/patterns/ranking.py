from qx.models.scan import ScanCandidate


def composite_rank_score(candidate: ScanCandidate) -> float:
    """Rank closest matches by pattern quality first, then breakout readiness."""

    score = (
        candidate.pattern_score * 0.45
        + candidate.readiness_score * 0.25
        + candidate.multi_timeframe_score * 0.20
        + candidate.score * 0.10
    )
    return max(0.0, min(1.0, score))


def sort_candidates(candidates: list[ScanCandidate]) -> list[ScanCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            composite_rank_score(candidate),
            candidate.setup_score,
            candidate.pattern_score,
            candidate.readiness_score,
        ),
        reverse=True,
    )
