from statistics import median

from qx.options_flow.models import FlowClassification, OptionFlowTrade, PremiumAnalysis, clamp_score


def analyze_premium(
    trades: list[OptionFlowTrade],
    classifications: list[FlowClassification],
) -> PremiumAnalysis:
    if not trades:
        return PremiumAnalysis(
            premium_score=0,
            unusual_premium_score=0,
            repeated_flow_score=0,
            ask_call_premium_score=0,
            ask_put_premium_score=0,
        )
    premiums = [trade.effective_premium for trade in trades if trade.effective_premium > 0]
    total_premium = sum(premiums)
    typical = median(premiums) if premiums else 0.0
    unusual = sum(1 for premium in premiums if typical > 0 and premium >= typical * 2.5)
    repeated = _repeated_flow_count(trades)
    ask_call = sum(
        trade.effective_premium
        for trade, classification in zip(trades, classifications, strict=True)
        if trade.option_type == "CALL" and classification.trade_side == "AT_ASK"
    )
    ask_put = sum(
        trade.effective_premium
        for trade, classification in zip(trades, classifications, strict=True)
        if trade.option_type == "PUT" and classification.trade_side == "AT_ASK"
    )
    return PremiumAnalysis(
        premium_score=clamp_score(total_premium / 10_000),
        unusual_premium_score=clamp_score((unusual / max(len(trades), 1)) * 100),
        repeated_flow_score=clamp_score(repeated * 18),
        ask_call_premium_score=clamp_score(ask_call / 7_500),
        ask_put_premium_score=clamp_score(ask_put / 7_500),
    )


def _repeated_flow_count(trades: list[OptionFlowTrade]) -> int:
    counts: dict[tuple[str, float, str | None, str], int] = {}
    for trade in trades:
        key = (
            trade.option_type,
            trade.strike,
            trade.expiration.isoformat() if trade.expiration else None,
            trade.trade_kind.lower(),
        )
        counts[key] = counts.get(key, 0) + 1
    return sum(count - 1 for count in counts.values() if count > 1)
