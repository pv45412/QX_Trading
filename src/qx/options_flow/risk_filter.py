from qx.options_flow.models import (
    FlowClassification,
    IVQuality,
    MarketRegimeContext,
    OptionFlowTrade,
    PriceConfirmation,
    RiskAssessment,
    clamp_score,
)


def assess_no_trade_risk(
    trades: list[OptionFlowTrade],
    classifications: list[FlowClassification],
    iv_quality: IVQuality,
    price_confirmation: PriceConfirmation,
    regime: MarketRegimeContext,
) -> RiskAssessment:
    warnings: list[str] = []
    risk = 10.0
    bullish = sum(item.bullish_score for item in classifications)
    bearish = sum(item.bearish_score for item in classifications)
    if bullish > 0 and bearish > 0 and min(bullish, bearish) / max(bullish, bearish) >= 0.65:
        risk += 28
        warnings.append("Call and put flow are too balanced; direction is conflicted.")
    if iv_quality.iv_chase_risk >= 65:
        risk += 25
        warnings.extend(iv_quality.warnings)
    wide = [trade for trade in trades if trade.spread_pct > 0.15]
    if wide:
        risk += min(22, len(wide) * 6)
        warnings.append("One or more contracts have wide bid/ask spreads.")
    thin = [trade for trade in trades if trade.volume < 50 or trade.open_interest < 100]
    if thin:
        risk += min(18, len(thin) * 4)
        warnings.append("Thin option volume/open interest reduces reliability.")
    if max(price_confirmation.call_confirmation_score, price_confirmation.put_confirmation_score) < 55:
        risk += 18
        warnings.append("Underlying price does not confirm the flow strongly.")
    risky_tags = [
        tag
        for classification in classifications
        for tag in classification.risk_tags
        if tag in {"spread-risk", "hedge-risk", "mid-market print", "unknown execution side"}
    ]
    if risky_tags:
        risk += min(20, len(risky_tags) * 5)
        warnings.append("Some flow may be spread, hedge, roll, or non-directional flow.")
    if regime.market_chop:
        risk += 12
        warnings.append("Market regime is choppy.")
    if regime.macro_event_risk:
        risk += 15
        warnings.append("Macro event risk is active.")
    return RiskAssessment(no_trade_risk=clamp_score(risk), warnings=_dedupe(warnings))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
