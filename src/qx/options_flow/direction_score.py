from qx.options_flow.models import (
    DirectionScore,
    FlowClassification,
    FinalSignal,
    IVQuality,
    MarketRegimeContext,
    PremiumAnalysis,
    PriceConfirmation,
    RiskAssessment,
    clamp_score,
)


def score_direction(
    classifications: list[FlowClassification],
    premium: PremiumAnalysis,
    iv_quality: IVQuality,
    price: PriceConfirmation,
    regime: MarketRegimeContext,
    risk: RiskAssessment,
) -> DirectionScore:
    bullish_flow = _avg([item.bullish_score for item in classifications])
    bearish_flow = _avg([item.bearish_score for item in classifications])
    call_sweep = _tag_score(classifications, "sweep", "bullish")
    put_sweep = _tag_score(classifications, "sweep", "bearish")
    call_regime = _call_regime_score(regime)
    put_regime = _put_regime_score(regime)
    call_score = clamp_score(
        bullish_flow * 0.25
        + call_sweep * 0.15
        + premium.ask_call_premium_score * 0.15
        + price.call_confirmation_score * 0.20
        + price.liquidity_break_score * 0.10
        + iv_quality.iv_quality_score * 0.10
        + call_regime * 0.05
    )
    put_score = clamp_score(
        bearish_flow * 0.25
        + put_sweep * 0.15
        + premium.ask_put_premium_score * 0.15
        + price.put_confirmation_score * 0.20
        + price.liquidity_breakdown_score * 0.10
        + iv_quality.iv_quality_score * 0.10
        + put_regime * 0.05
    )
    final = _final_signal(call_score, put_score, risk.no_trade_risk, iv_quality.iv_chase_risk)
    why = _why(call_score, put_score, price, premium, regime)
    return DirectionScore(
        call_buy_score=call_score,
        put_buy_score=put_score,
        no_trade_risk=risk.no_trade_risk,
        final_signal=final,
        why=why,
        warnings=risk.warnings,
    )


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _tag_score(classifications: list[FlowClassification], tag: str, direction: str) -> float:
    hits = [
        item
        for item in classifications
        if tag in item.risk_tags and item.directional_read == direction
    ]
    return clamp_score(len(hits) * 35)


def _call_regime_score(regime: MarketRegimeContext) -> float:
    score = 50.0
    if regime.spy_trend == "bullish":
        score += 20
    if regime.qqq_trend == "bullish":
        score += 15
    if regime.vix_trend == "falling":
        score += 10
    if regime.sector_strength == "strong":
        score += 10
    if regime.macro_event_risk or regime.market_chop:
        score -= 20
    return clamp_score(score)


def _put_regime_score(regime: MarketRegimeContext) -> float:
    score = 50.0
    if regime.spy_trend == "bearish":
        score += 20
    if regime.qqq_trend == "bearish":
        score += 15
    if regime.vix_trend == "rising":
        score += 10
    if regime.sector_strength == "weak":
        score += 10
    if regime.macro_event_risk:
        score -= 10
    return clamp_score(score)


def _final_signal(call: float, put: float, risk: float, iv_risk: float) -> FinalSignal:
    if iv_risk >= 80 and max(call, put) < 82:
        return "IV CHASE RISK"
    if risk >= 75:
        return "NO TRADE"
    if call >= 65 and put >= 65 and abs(call - put) <= 12:
        return "CONFLICTED FLOW"
    if call >= 75 and call >= put + 10 and risk < 65:
        return "CALLS STRONG"
    if call >= 60 and call >= put + 8 and risk < 70:
        return "CALLS WATCH"
    if put >= 75 and put >= call + 10 and risk < 65:
        return "PUTS STRONG"
    if put >= 60 and put >= call + 8 and risk < 70:
        return "PUTS WATCH"
    return "NO TRADE"


def _why(
    call: float,
    put: float,
    price: PriceConfirmation,
    premium: PremiumAnalysis,
    regime: MarketRegimeContext,
) -> list[str]:
    lead = "call" if call > put else "put" if put > call else "balanced"
    reasons = [
        f"Lead side is {lead}; calls {call:.0f}, puts {put:.0f}.",
        f"Ask-side call premium score {premium.ask_call_premium_score:.0f}; ask-side put premium score {premium.ask_put_premium_score:.0f}.",
        f"Price confirmation: calls {price.call_confirmation_score:.0f}, puts {price.put_confirmation_score:.0f}.",
        f"Market regime: SPY {regime.spy_trend}, QQQ {regime.qqq_trend}, VIX {regime.vix_trend}.",
    ]
    reasons.extend(price.notes)
    return reasons
