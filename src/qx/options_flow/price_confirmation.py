from qx.options_flow.models import PriceConfirmation, UnderlyingContext, clamp_score


def confirm_price(context: UnderlyingContext) -> PriceConfirmation:
    price = context.current_price
    call = 40.0
    put = 40.0
    liquidity_break = 0.0
    liquidity_breakdown = 0.0
    notes: list[str] = []

    if price <= 0:
        return PriceConfirmation(
            call_confirmation_score=20.0,
            put_confirmation_score=20.0,
            liquidity_break_score=0.0,
            liquidity_breakdown_score=0.0,
            notes=["Underlying price unavailable; flow lacks price confirmation."],
        )

    if context.vwap > 0:
        if price >= context.vwap:
            call += 25
            notes.append("Underlying is above VWAP, supporting call flow.")
        else:
            put += 25
            notes.append("Underlying is below VWAP, supporting put flow.")
    if context.trend_direction == "up":
        call += 15
    elif context.trend_direction == "down":
        put += 15
    if context.nearest_supply > 0 and price > context.nearest_supply:
        call += 25
        liquidity_break = 90
        notes.append("Price is above nearest supply/liquidity trigger.")
    elif context.nearest_supply > 0 and price >= context.nearest_supply * 0.995:
        call += 12
        liquidity_break = 55
        notes.append("Price is testing nearby supply.")
    if context.nearest_demand > 0 and price < context.nearest_demand:
        put += 25
        liquidity_breakdown = 90
        notes.append("Price is below nearest demand/liquidity support.")
    elif context.nearest_demand > 0 and price <= context.nearest_demand * 1.005:
        put += 12
        liquidity_breakdown = 55
        notes.append("Price is testing nearby demand.")
    if context.opening_range_high > 0 and price > context.opening_range_high:
        call += 12
    if context.opening_range_low > 0 and price < context.opening_range_low:
        put += 12

    trigger = context.nearest_supply or context.prior_day_high or price
    invalidation = context.nearest_demand or context.prior_day_low or price
    return PriceConfirmation(
        call_confirmation_score=clamp_score(call),
        put_confirmation_score=clamp_score(put),
        liquidity_break_score=clamp_score(liquidity_break),
        liquidity_breakdown_score=clamp_score(liquidity_breakdown),
        trigger_price=trigger,
        invalidation_price=invalidation,
        notes=notes,
    )
