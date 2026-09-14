"""Position Adjustment & Roll Engine logic."""

from qx.positions.health import calculate_position_health
from qx.positions.roll.models import (
    PositionAdjustmentPlan,
    PositionRollRecommendation,
    PositionRollRequest,
    RollLeg,
)


def evaluate_position_roll(req: PositionRollRequest) -> PositionAdjustmentPlan:
    """Evaluate an active position and compute optimal roll or adjustment strategy.

    :param req: Position parameters & market health metrics
    :return: PositionAdjustmentPlan containing health score & explicit execution legs
    """
    # 1. Compute multi-factor position health score
    health = calculate_position_health(
        trend_score=req.trend_score,
        structure_score=req.structure_score,
        invalidation_distance_pct=req.invalidation_distance_pct,
        reward_remaining_pct=req.reward_remaining_pct,
        momentum_score=req.momentum_score,
        volatility_score=req.volatility_score,
        dte=req.current_dte,
        stop_breached=req.stop_breached,
        assignment_imminent=req.assignment_imminent,
    )

    strike = req.current_strike or req.underlying_price
    price = req.underlying_price

    # 2. Hard Exit check (Stop breached or critical health score)
    if req.stop_breached or health.action == "EXIT / REVIEW":
        close_action = "SELL_TO_CLOSE" if "long" in req.position_type else "BUY_TO_CLOSE"
        option_kind = "put" if "put" in req.position_type else ("call" if "call" in req.position_type else "underlying")
        recommendation = PositionRollRecommendation(
            roll_type="CLOSE_POSITION",
            target_dte=0,
            net_credit_debit=round(req.current_premium, 2) if "long" in req.position_type else -round(req.current_premium, 2),
            recommended_legs=[
                RollLeg(
                    action=close_action,
                    option_type=option_kind,
                    strike=strike,
                    dte=req.current_dte,
                    estimated_premium=req.current_premium,
                )
            ],
            rationale="Technical invalidation or stop loss breach. Immediate exit recommended to limit downside exposure.",
        )

    # 3. Short Option Defense (Credit Roll Out / Roll Up & Out)
    elif req.position_type in ["short_put", "short_call"] and (
        req.current_dte <= 7 or req.assignment_imminent or health.action in ["TRIM / ADJUST", "ROLL / CLOSE"]
    ):
        target_dte = 30
        close_cost = req.current_premium if req.current_premium > 0 else round(price * 0.02, 2)
        new_premium = round(close_cost * 1.35, 2)
        net_credit = round(new_premium - close_cost, 2)

        is_put = req.position_type == "short_put"
        opt_type = "put" if is_put else "call"
        # Adjust strike if defense needed
        new_strike = round(strike * (0.97 if is_put else 1.03), 2)

        recommendation = PositionRollRecommendation(
            roll_type="CREDIT_ROLL_OUT",
            target_dte=target_dte,
            net_credit_debit=net_credit,
            recommended_legs=[
                RollLeg(
                    action="BUY_TO_CLOSE",
                    option_type=opt_type,
                    strike=strike,
                    dte=req.current_dte,
                    estimated_premium=close_cost,
                ),
                RollLeg(
                    action="SELL_TO_OPEN",
                    option_type=opt_type,
                    strike=new_strike,
                    dte=target_dte,
                    estimated_premium=new_premium,
                ),
            ],
            rationale=f"Roll expiring short {opt_type} out to {target_dte} DTE to extend duration and capture ${net_credit:.2f} net credit.",
        )

    # 4. Long Option Legging into Spread
    elif req.position_type in ["long_call", "long_put"] and (
        health.action in ["TRIM / ADJUST", "ROLL / CLOSE"] or req.reward_remaining_pct < 40.0
    ):
        is_call = req.position_type == "long_call"
        opt_type = "call" if is_call else "put"
        short_strike = round(price * (1.05 if is_call else 0.95), 2)
        sell_premium = round(price * 0.025, 2)

        recommendation = PositionRollRecommendation(
            roll_type="LEG_INTO_SPREAD",
            target_dte=req.current_dte,
            net_credit_debit=sell_premium,
            recommended_legs=[
                RollLeg(
                    action="SELL_TO_OPEN",
                    option_type=opt_type,
                    strike=short_strike,
                    dte=req.current_dte,
                    estimated_premium=sell_premium,
                )
            ],
            rationale=f"Sell OTM {opt_type} against long position to convert single-leg into defined-risk spread and finance decay.",
        )

    # 5. Long Stock Collar Defense
    elif req.position_type == "long_stock" and (
        health.action in ["TRIM / ADJUST", "ROLL / CLOSE"] or health.composite_score < 55.0
    ):
        target_dte = 30
        put_strike = round(price * 0.95, 2)
        call_strike = round(price * 1.05, 2)
        put_cost = round(price * 0.03, 2)
        call_credit = round(price * 0.03, 2)

        recommendation = PositionRollRecommendation(
            roll_type="PROTECTIVE_COLLAR",
            target_dte=target_dte,
            net_credit_debit=0.0,
            recommended_legs=[
                RollLeg(
                    action="BUY_TO_OPEN",
                    option_type="put",
                    strike=put_strike,
                    dte=target_dte,
                    estimated_premium=put_cost,
                ),
                RollLeg(
                    action="SELL_TO_OPEN",
                    option_type="call",
                    strike=call_strike,
                    dte=target_dte,
                    estimated_premium=call_credit,
                ),
            ],
            rationale="Structure Zero-Cost Protective Collar (OTM Put + Covered Call) to cap downside loss while preserving upside.",
        )

    # 6. Default Hold / No Action
    else:
        recommendation = PositionRollRecommendation(
            roll_type="HOLD_NO_ACTION",
            target_dte=req.current_dte,
            net_credit_debit=0.0,
            recommended_legs=[],
            rationale="Position health is within target bounds (Composite >= 55). No structural adjustment needed at this time.",
        )

    return PositionAdjustmentPlan(
        symbol=req.symbol,
        composite_health=health.composite_score,
        health_action=health.action,
        recommendation=recommendation,
    )
