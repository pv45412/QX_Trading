from qx.options_flow.models import FlowClassification, OptionFlowTrade, TradeSide


SPREAD_KEYWORDS = {"spread", "multi", "split", "combo", "roll", "complex"}
HEDGE_KEYWORDS = {"hedge", "stock", "delta neutral", "conversion"}


def classify_trade(trade: OptionFlowTrade) -> FlowClassification:
    side = _trade_side(trade)
    tags = _risk_tags(trade)
    if "spread-risk" in tags:
        return FlowClassification(
            trade_side=side,
            aggression_score=25.0,
            directional_read="spread-risk",
            bullish_score=15.0,
            bearish_score=15.0,
            risk_tags=tags,
        )
    if "hedge-risk" in tags:
        return FlowClassification(
            trade_side=side,
            aggression_score=25.0,
            directional_read="hedge-risk",
            bullish_score=20.0,
            bearish_score=20.0,
            risk_tags=tags,
        )

    if side == "AT_ASK":
        if trade.option_type == "CALL":
            return FlowClassification(
                trade_side=side,
                aggression_score=90.0,
                directional_read="bullish",
                bullish_score=90.0,
                bearish_score=5.0,
                risk_tags=tags,
            )
        return FlowClassification(
            trade_side=side,
            aggression_score=90.0,
            directional_read="bearish",
            bullish_score=5.0,
            bearish_score=90.0,
            risk_tags=tags,
        )
    if side == "AT_BID":
        if trade.option_type == "CALL":
            return FlowClassification(
                trade_side=side,
                aggression_score=70.0,
                directional_read="bearish",
                bullish_score=10.0,
                bearish_score=65.0,
                risk_tags=tags + ["possible call sale"],
            )
        return FlowClassification(
            trade_side=side,
            aggression_score=70.0,
            directional_read="bullish",
            bullish_score=65.0,
            bearish_score=10.0,
            risk_tags=tags + ["possible put sale"],
        )
    if side == "MID":
        return FlowClassification(
            trade_side=side,
            aggression_score=35.0,
            directional_read="neutral",
            bullish_score=30.0,
            bearish_score=30.0,
            risk_tags=tags + ["mid-market print"],
        )
    return FlowClassification(
        trade_side=side,
        aggression_score=15.0,
        directional_read="neutral",
        bullish_score=15.0,
        bearish_score=15.0,
        risk_tags=tags + ["unknown execution side"],
    )


def _trade_side(trade: OptionFlowTrade) -> TradeSide:
    if trade.ask <= 0 or trade.bid <= 0 or trade.ask < trade.bid or trade.trade_price <= 0:
        return "UNKNOWN"
    spread = max(trade.ask - trade.bid, 0.01)
    tolerance = max(spread * 0.12, 0.01)
    midpoint = trade.midpoint
    if trade.trade_price >= trade.ask - tolerance:
        return "AT_ASK"
    if trade.trade_price <= trade.bid + tolerance:
        return "AT_BID"
    if abs(trade.trade_price - midpoint) <= tolerance:
        return "MID"
    return "UNKNOWN"


def _risk_tags(trade: OptionFlowTrade) -> list[str]:
    text = f"{trade.trade_condition} {trade.trade_kind}".lower()
    tags: list[str] = []
    if any(keyword in text for keyword in SPREAD_KEYWORDS):
        tags.append("spread-risk")
    if any(keyword in text for keyword in HEDGE_KEYWORDS):
        tags.append("hedge-risk")
    if trade.trade_kind.lower() in {"sweep", "block"}:
        tags.append(trade.trade_kind.lower())
    if trade.spread_pct > 0.20:
        tags.append("wide spread")
    return tags
