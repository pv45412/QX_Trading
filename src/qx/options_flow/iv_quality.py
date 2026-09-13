from statistics import mean

from qx.options_flow.models import IVQuality, OptionFlowTrade, clamp_score


def evaluate_iv_quality(trades: list[OptionFlowTrade], *, event_risk: bool = False) -> IVQuality:
    ivs = [trade.implied_volatility for trade in trades if trade.implied_volatility > 0]
    if not ivs:
        return IVQuality(
            iv_quality_score=45.0,
            iv_chase_risk=35.0,
            event_risk=event_risk,
            warnings=["IV unavailable; treating IV quality as neutral-risk."],
        )
    avg_iv = mean(ivs)
    high_iv_ratio = sum(1 for iv in ivs if iv >= 1.0) / len(ivs)
    elevated_ratio = sum(1 for iv in ivs if iv >= 0.75) / len(ivs)
    iv_chase = clamp_score(high_iv_ratio * 100 + elevated_ratio * 35 + (20 if event_risk else 0))
    quality = clamp_score(90 - iv_chase * 0.65)
    warnings: list[str] = []
    if avg_iv >= 1.0:
        warnings.append("Average IV is very elevated; long options may be IV-chase trades.")
    elif avg_iv >= 0.75:
        warnings.append("IV is elevated; require stronger price confirmation.")
    if event_risk:
        warnings.append("Event risk is active; IV crush risk can dominate direction.")
    return IVQuality(iv_quality_score=quality, iv_chase_risk=iv_chase, event_risk=event_risk, warnings=warnings)
