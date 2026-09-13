from datetime import UTC, date, datetime

from qx.options_flow.models import OptionFlowTrade, SuggestedContract, clamp_score


DAY_TRADE_SYMBOLS = {"SPX", "SPY", "QQQ"}


def select_contracts(trades: list[OptionFlowTrade], *, current_price: float) -> list[SuggestedContract]:
    candidates: list[SuggestedContract] = []
    today = datetime.now(UTC).date()
    for trade in trades:
        dte = _days_to_expiration(trade.expiration, today)
        day_trade = trade.ticker in DAY_TRADE_SYMBOLS and 0 <= dte <= 3
        swing_trade = 7 <= dte <= 45
        if not day_trade and not swing_trade:
            continue
        if day_trade and not (0.30 <= abs(trade.delta) <= 0.55):
            continue
        if swing_trade and not (0.35 <= abs(trade.delta) <= 0.60):
            continue
        if trade.spread_pct > (0.08 if day_trade else 0.12):
            continue
        if trade.volume < (100 if day_trade else 50) or trade.open_interest < 100:
            continue
        moneyness_penalty = abs(trade.strike - current_price) / current_price * 100 if current_price > 0 else 15
        score = clamp_score(
            100
            - trade.spread_pct * 220
            + min(trade.volume / 20, 15)
            + min(trade.open_interest / 300, 10)
            - moneyness_penalty
        )
        candidates.append(
            SuggestedContract(
                ticker=trade.ticker,
                option_symbol=trade.option_symbol,
                strategy_bucket="Day Trade" if day_trade else "Swing Trade",
                option_type=trade.option_type,
                expiration=trade.expiration,
                strike=trade.strike,
                delta=trade.delta,
                bid=trade.bid,
                ask=trade.ask,
                spread_pct=trade.spread_pct,
                volume=trade.volume,
                open_interest=trade.open_interest,
                score=score,
                reason="Tight spread, usable delta, and enough volume/open interest.",
            )
        )
    return sorted(candidates, key=lambda item: item.score, reverse=True)[:10]


def _days_to_expiration(expiration: date | None, today: date) -> int:
    if expiration is None:
        return 999
    return (expiration - today).days
