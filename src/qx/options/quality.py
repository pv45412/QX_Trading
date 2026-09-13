from dataclasses import dataclass

from qx.watchlist.engine import WatchlistCandidate


__all__ = [
    "FundamentalSnapshot",
    "UnderlyingQualityGate",
    "UnderlyingQualityProfile",
    "evaluate_underlying_quality",
]


@dataclass(frozen=True)
class FundamentalSnapshot:
    market_cap: float | None = None
    eps_growth: float | None = None
    revenue_growth: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    profit_margin: float | None = None
    free_cash_flow_positive: bool | None = None


@dataclass(frozen=True)
class UnderlyingQualityGate:
    min_avg_volume: float = 1_000_000
    min_dollar_volume: float = 100_000_000
    min_market_cap: float = 5_000_000_000
    min_underlying_score: float = 0.55
    min_trend_score: float = 0.70
    min_liquidity_score: float = 0.75
    min_directional_score: float = 0.45
    min_fundamental_score: float = 0.55


@dataclass(frozen=True)
class UnderlyingQualityProfile:
    score: float
    label: str
    income_suitability: str
    leaps_suitability: str
    gate: str
    timing: str
    fundamental_note: str
    missing: list[str]
    factor_scores: dict[str, float]
    factor_grades: dict[str, str]
    breakdown: str


def evaluate_underlying_quality(
    candidate: WatchlistCandidate,
    gate: UnderlyingQualityGate | None = None,
    fundamentals: FundamentalSnapshot | None = None,
) -> UnderlyingQualityProfile:
    """Institutional-style quality model for option underlyings.

    The model is intentionally factorized. Today it can run with price/volume
    and watchlist data only. When true fundamentals are available, the same
    interface accepts them without changing option idea generation.
    """
    active_gate = gate or UnderlyingQualityGate()
    resolved_fundamentals = fundamentals or FundamentalSnapshot()
    dollar_volume = candidate.close * candidate.avg_volume_20d

    factor_scores = {
        "liquidity": _liquidity_factor(candidate, dollar_volume, active_gate),
        "trend": _trend_factor(candidate),
        "relative_strength": _relative_strength_factor(candidate),
        "tape": _tape_factor(candidate),
        "business_quality": _business_quality_factor(resolved_fundamentals),
        "options_timing": _options_timing_factor(candidate),
    }
    score = _weighted_score(
        factor_scores,
        {
            "liquidity": 0.22,
            "trend": 0.20,
            "relative_strength": 0.15,
            "tape": 0.12,
            "business_quality": 0.19,
            "options_timing": 0.12,
        },
    )
    missing = _missing_reasons(candidate, dollar_volume, active_gate, resolved_fundamentals, factor_scores)
    factor_grades = {name: _grade(score_value) for name, score_value in factor_scores.items()}
    label = _quality_label(score, missing)
    gate_result = _gate_result(label, candidate, factor_scores, missing)
    income_suitability = _income_suitability(label, gate_result, candidate)
    leaps_suitability = _leaps_suitability(label, gate_result, candidate)
    breakdown = ", ".join(f"{name.replace('_', ' ')} {score_value:.2f}" for name, score_value in factor_scores.items())

    return UnderlyingQualityProfile(
        score=round(score, 3),
        label=label,
        income_suitability=income_suitability,
        leaps_suitability=leaps_suitability,
        gate=gate_result,
        timing=_technical_timing_note(candidate),
        fundamental_note=_fundamental_note(resolved_fundamentals),
        missing=missing,
        factor_scores={name: round(value, 3) for name, value in factor_scores.items()},
        factor_grades=factor_grades,
        breakdown=breakdown,
    )


def _liquidity_factor(candidate: WatchlistCandidate, dollar_volume: float, gate: UnderlyingQualityGate) -> float:
    share_volume_score = min(candidate.avg_volume_20d / (gate.min_avg_volume * 2), 1.0)
    dollar_volume_score = min(dollar_volume / (gate.min_dollar_volume * 2), 1.0)
    return _clamp(candidate.liquidity_score * 0.50 + share_volume_score * 0.25 + dollar_volume_score * 0.25)


def _trend_factor(candidate: WatchlistCandidate) -> float:
    return _clamp(candidate.trend_score * 0.70 + candidate.momentum_score * 0.30)


def _relative_strength_factor(candidate: WatchlistCandidate) -> float:
    return _clamp(candidate.relative_strength_score * 0.70 + candidate.sector_score * 0.30)


def _tape_factor(candidate: WatchlistCandidate) -> float:
    volume_quality = min(candidate.relative_volume_20d / 1.5, 1.0)
    if candidate.options_bias == "Bullish":
        directional_quality = candidate.directional_score
    elif candidate.options_bias == "Neutral":
        directional_quality = candidate.directional_score * 0.60
    else:
        directional_quality = candidate.directional_score * 0.35
    return _clamp(candidate.volume_score * 0.45 + volume_quality * 0.25 + directional_quality * 0.30)


def _business_quality_factor(fundamentals: FundamentalSnapshot) -> float:
    available = [
        _score_market_cap(fundamentals.market_cap),
        _score_growth(fundamentals.eps_growth),
        _score_growth(fundamentals.revenue_growth),
        _score_roe(fundamentals.roe),
        _score_debt(fundamentals.debt_to_equity),
        _score_margin(fundamentals.profit_margin),
        _score_cash_flow(fundamentals.free_cash_flow_positive),
    ]
    scored = [value for value in available if value is not None]
    if not scored:
        return 0.50
    return _clamp(sum(scored) / len(scored))


def _options_timing_factor(candidate: WatchlistCandidate) -> float:
    if candidate.options_bias == "Bullish" and candidate.options_setup in {"Call pullback", "Call breakout"}:
        return _clamp(0.55 + candidate.directional_score * 0.45)
    if candidate.options_bias == "Bullish":
        return _clamp(0.35 + candidate.directional_score * 0.45)
    if candidate.options_bias == "Bearish":
        return _clamp(candidate.directional_score * 0.45)
    return _clamp(candidate.directional_score * 0.35)


def _missing_reasons(
    candidate: WatchlistCandidate,
    dollar_volume: float,
    gate: UnderlyingQualityGate,
    fundamentals: FundamentalSnapshot,
    factor_scores: dict[str, float],
) -> list[str]:
    missing: list[str] = []
    if candidate.avg_volume_20d < gate.min_avg_volume:
        missing.append("avg volume < 1M")
    if dollar_volume < gate.min_dollar_volume:
        missing.append("dollar volume < $100M")
    if candidate.liquidity_score < gate.min_liquidity_score:
        missing.append("liquidity score weak")
    if candidate.trend_score < gate.min_trend_score:
        missing.append("trend alignment weak")
    if candidate.directional_score < gate.min_directional_score:
        missing.append("technical timing weak")
    if candidate.final_score < gate.min_underlying_score:
        missing.append("broad watchlist score weak")
    if fundamentals.market_cap is not None and fundamentals.market_cap < gate.min_market_cap:
        missing.append("market cap < $5B")
    if factor_scores["business_quality"] < gate.min_fundamental_score:
        missing.append("business quality weak")
    if _fundamental_coverage(fundamentals) == 0:
        missing.append("real fundamentals unavailable")
    return missing


def _quality_label(score: float, missing: list[str]) -> str:
    hard_missing = [item for item in missing if item != "real fundamentals unavailable"]
    if score >= 0.82 and not hard_missing:
        return "Institutional"
    if score >= 0.74 and len(hard_missing) <= 1:
        return "Core"
    if score >= 0.62 and len(hard_missing) <= 3:
        return "Quality Watch"
    if score >= 0.50:
        return "Speculative"
    return "Reject"


def _gate_result(
    label: str,
    candidate: WatchlistCandidate,
    factor_scores: dict[str, float],
    missing: list[str],
) -> str:
    hard_missing = [item for item in missing if item != "real fundamentals unavailable"]
    if label in {"Institutional", "Core"} and candidate.options_bias == "Bullish" and not hard_missing:
        return "Pass"
    if label in {"Institutional", "Core"} and candidate.options_bias == "Bullish":
        return "Conditional"
    if label == "Quality Watch" and factor_scores["liquidity"] >= 0.70 and candidate.options_bias == "Bullish":
        return "Review"
    if candidate.options_bias == "Bearish" and label in {"Institutional", "Core", "Quality Watch"}:
        return "Hedge Only"
    return "Fail"


def _income_suitability(label: str, gate: str, candidate: WatchlistCandidate) -> str:
    if gate == "Pass":
        return "Put / covered-call eligible"
    if gate == "Conditional":
        return "Income eligible after missing checks"
    if gate == "Review" and candidate.options_bias == "Bullish":
        return "Income watchlist"
    if gate == "Hedge Only":
        return "Avoid bullish income"
    if label == "Speculative":
        return "Directional only"
    return "Avoid income"


def _leaps_suitability(label: str, gate: str, candidate: WatchlistCandidate) -> str:
    if gate in {"Pass", "Conditional"} and candidate.options_setup in {"Call breakout", "Call pullback"}:
        return "LEAPS eligible after trigger"
    if label in {"Institutional", "Core", "Quality Watch"} and candidate.options_bias == "Bullish":
        return "LEAPS watchlist"
    if gate == "Hedge Only":
        return "Directional hedge only"
    return "Avoid LEAPS"


def _technical_timing_note(candidate: WatchlistCandidate) -> str:
    if candidate.options_bias == "Bullish" and candidate.options_setup == "Call pullback":
        return "Daily uptrend; wait for 15m 8 EMA reclaim after 30m/21 or hourly/50 support."
    if candidate.options_bias == "Bullish" and candidate.options_setup == "Call breakout":
        return "Daily trigger active; confirm 15m/8, 30m/21, hourly/50 alignment before entry."
    if candidate.options_bias == "Bullish":
        return "Daily bullish bias exists; intraday EMA trigger is still required before action."
    if candidate.options_bias == "Bearish":
        return "Bearish directional setup; avoid put-selling or covered-call income framing."
    return "No clean daily setup; wait for intraday EMA alignment and stronger directional score."


def _fundamental_note(fundamentals: FundamentalSnapshot) -> str:
    coverage = _fundamental_coverage(fundamentals)
    if coverage == 0:
        return (
            "Fundamental slots are not populated yet; current grade uses liquidity, trend, "
            "relative strength, sector leadership, tape, and timing as proxies."
        )
    return f"Fundamental coverage {coverage}/7 fields included in the quality grade."


def _fundamental_coverage(fundamentals: FundamentalSnapshot) -> int:
    return sum(
        value is not None
        for value in [
            fundamentals.market_cap,
            fundamentals.eps_growth,
            fundamentals.revenue_growth,
            fundamentals.roe,
            fundamentals.debt_to_equity,
            fundamentals.profit_margin,
            fundamentals.free_cash_flow_positive,
        ]
    )


def _weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    return _clamp(sum(scores[name] * weights[name] for name in weights))


def _grade(score: float) -> str:
    if score >= 0.85:
        return "A"
    if score >= 0.72:
        return "B"
    if score >= 0.58:
        return "C"
    if score >= 0.45:
        return "D"
    return "F"


def _score_market_cap(value: float | None) -> float | None:
    if value is None:
        return None
    return _clamp(value / 50_000_000_000)


def _score_growth(value: float | None) -> float | None:
    if value is None:
        return None
    return _clamp((value + 0.05) / 0.25)


def _score_roe(value: float | None) -> float | None:
    if value is None:
        return None
    return _clamp(value / 0.25)


def _score_debt(value: float | None) -> float | None:
    if value is None:
        return None
    return _clamp(1.0 - value / 2.0)


def _score_margin(value: float | None) -> float | None:
    if value is None:
        return None
    return _clamp(value / 0.25)


def _score_cash_flow(value: bool | None) -> float | None:
    if value is None:
        return None
    return 1.0 if value else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(value, 1.0))
