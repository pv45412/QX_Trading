from dataclasses import dataclass

from qx.options.chains import OptionContract
from qx.options.quality import UnderlyingQualityProfile
from qx.options.timing import EmaTimingSnapshot
from qx.watchlist.engine import WatchlistCandidate


@dataclass(frozen=True)
class StrategySelection:
    instrument: str
    regime_bucket: str
    rationale: str
    exit_plan: str


def select_directional_strategy(
    candidate: WatchlistCandidate,
    quality: UnderlyingQualityProfile,
    *,
    contract: OptionContract | None = None,
    timing: EmaTimingSnapshot | None = None,
) -> StrategySelection:
    """Select the options instrument from regime, conviction, quality, and IV context."""

    conviction = _conviction(candidate, quality, timing)
    iv = contract.implied_volatility if contract else None
    high_iv = iv is not None and iv >= 0.55
    low_or_moderate_iv = iv is None or iv < 0.55
    high_quality = quality.label in {"Institutional", "Core"}
    income_eligible = quality.gate in {"Pass", "Conditional", "Review"}
    trend_ok = candidate.trend_score >= 0.70 and candidate.options_bias == "Bullish"
    short_term = candidate.options_setup in {"Call breakout", "Put breakdown"} and candidate.directional_score >= 0.78
    range_bound = candidate.directional_score < 0.58 or candidate.options_setup == "No clean setup"

    if candidate.options_bias == "Bearish":
        return StrategySelection(
            instrument="Put debit spread",
            regime_bucket="Trending + moderate conviction",
            rationale="Bearish technical setup; defined-risk puts are cleaner than premium selling.",
            exit_plan="Scale at 50-75% max gain or close if resistance is reclaimed.",
        )

    if high_quality and trend_ok and conviction >= 0.78 and low_or_moderate_iv:
        return StrategySelection(
            instrument="Long call",
            regime_bucket="Trending + high conviction",
            rationale="Quality, trend, timing, and tape are aligned while IV is not excessive.",
            exit_plan="Scale profits at 25/50/75% and into major resistance or failed EMA support.",
        )

    if high_quality and quality.leaps_suitability.startswith("LEAPS") and candidate.options_setup == "Call pullback":
        return StrategySelection(
            instrument="LEAPS stock replacement",
            regime_bucket="Slow thesis (3+ months)",
            rationale="High-quality bullish pullback favors longer-dated convex exposure with lower theta pressure.",
            exit_plan="Exit when thesis plays out, trend breaks, or quality/timing gate deteriorates.",
        )

    if range_bound and income_eligible:
        return StrategySelection(
            instrument="Credit spread",
            regime_bucket="Range-bound / choppy",
            rationale="Directional edge is not strong enough for premium buying; use support/resistance income only.",
            exit_plan="Take profit at 50-75% max gain; close if support/resistance breaks.",
        )

    if range_bound:
        return StrategySelection(
            instrument="No option trade",
            regime_bucket="Range-bound / low conviction",
            rationale="No clean directional edge and quality gate is not strong enough for income.",
            exit_plan="Wait for trend, timing, or support/resistance confirmation.",
        )

    if short_term and quality.label in {"Speculative", "Quality Watch"}:
        return StrategySelection(
            instrument="Leveraged ETF / stock only",
            regime_bucket="Short-term momentum (1-5 days)",
            rationale="Momentum exists, but quality is not strong enough for long-horizon options or income.",
            exit_plan="Use moving-average rules; never average down after the trigger fails.",
        )

    if high_iv or conviction < 0.78:
        return StrategySelection(
            instrument="Call debit spread",
            regime_bucket="Trending + moderate conviction",
            rationale="Directional bias exists, but conviction or IV favors defined-risk, lower-theta exposure.",
            exit_plan="Use the same scale-out framework as long calls; close if trigger support fails.",
        )

    return StrategySelection(
        instrument="Call debit spread",
        regime_bucket="Trending + moderate conviction",
        rationale="Bullish setup is present; defined risk is preferred until conviction improves.",
        exit_plan="Scale at defined profit levels and close if the technical trigger breaks.",
    )


def _conviction(
    candidate: WatchlistCandidate,
    quality: UnderlyingQualityProfile,
    timing: EmaTimingSnapshot | None,
) -> float:
    timing_score = timing.score if timing else 0.50
    return max(
        0.0,
        min(
            candidate.directional_score * 0.35
            + candidate.readiness_score * 0.20
            + quality.score * 0.30
            + timing_score * 0.15,
            1.0,
        ),
    )
