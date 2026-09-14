"""Signal score calibration and reliability evaluation engine.

Evaluates whether high signal quality scores (e.g., 80-100) reliably outperform lower scores (e.g., 60-79).
Computes bucket win rates, expected returns, and Brier calibration scores.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ScoreBucketSummary:
    bucket_name: str  # e.g., "Tier 1 (80-100)"
    min_score: float
    max_score: float
    sample_count: int
    win_rate: float
    average_r_multiple: float
    brier_score: float


@dataclass(frozen=True)
class CalibrationReport:
    total_trades_analyzed: int
    is_monotonic: bool  # True if Tier 1 WR > Tier 2 WR > Tier 3 WR
    brier_score_overall: float
    buckets: List[ScoreBucketSummary]
    recommendation: str


def evaluate_signal_calibration(
    scores_and_outcomes: List[Tuple[float, bool, float]],
) -> CalibrationReport:
    """Evaluate reliability of signal quality scores against realized trade outcomes.

    :param scores_and_outcomes: List of tuples (signal_score, is_win, realized_r_multiple).
    """
    if not scores_and_outcomes:
        return CalibrationReport(
            total_trades_analyzed=0,
            is_monotonic=True,
            brier_score_overall=0.0,
            buckets=[],
            recommendation="Insufficient historical trade data for score calibration.",
        )

    bucket_defs = [
        ("Tier 1 (80-100)", 80.0, 100.0),
        ("Tier 2 (60-79)", 60.0, 79.9),
        ("Tier 3 (0-59)", 0.0, 59.9),
    ]

    summaries: List[ScoreBucketSummary] = []
    overall_brier_sum = 0.0

    for b_name, b_min, b_max in bucket_defs:
        in_bucket = [item for item in scores_and_outcomes if b_min <= item[0] <= b_max]
        if not in_bucket:
            summaries.append(
                ScoreBucketSummary(
                    bucket_name=b_name,
                    min_score=b_min,
                    max_score=b_max,
                    sample_count=0,
                    win_rate=0.0,
                    average_r_multiple=0.0,
                    brier_score=0.0,
                )
            )
            continue

        count = len(in_bucket)
        wins = sum(1 for item in in_bucket if item[1])
        win_rate = round(wins / count, 4)
        avg_r = round(sum(item[2] for item in in_bucket) / count, 2)

        # Compute Brier score for this bucket
        brier_sum = 0.0
        for score, is_win, _ in in_bucket:
            prob = score / 100.0
            actual = 1.0 if is_win else 0.0
            diff_sq = (prob - actual) ** 2
            brier_sum += diff_sq
            overall_brier_sum += diff_sq

        brier_bucket = round(brier_sum / count, 4)
        summaries.append(
            ScoreBucketSummary(
                bucket_name=b_name,
                min_score=b_min,
                max_score=b_max,
                sample_count=count,
                win_rate=win_rate,
                average_r_multiple=avg_r,
                brier_score=brier_bucket,
            )
        )

    total_n = len(scores_and_outcomes)
    brier_overall = round(overall_brier_sum / total_n, 4)

    # Check monotonicity across populated buckets
    active_summaries = [s for s in summaries if s.sample_count > 0]
    is_monotonic = True
    for i in range(len(active_summaries) - 1):
        if active_summaries[i].win_rate < active_summaries[i + 1].win_rate:
            is_monotonic = False
            break

    rec = (
        "Signal scores display strong monotonic reliability; higher scores correlate with higher win rates."
        if is_monotonic
        else "Signal calibration non-monotonic; review factor weighting parameters."
    )

    return CalibrationReport(
        total_trades_analyzed=total_n,
        is_monotonic=is_monotonic,
        brier_score_overall=brier_overall,
        buckets=summaries,
        recommendation=rec,
    )
