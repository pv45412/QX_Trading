"""Phase 9 Options Expression Math and Payoff Utilities."""

from typing import List, Optional, Tuple

from qx.options_expression.models import OptionContract, StrategyType


def calculate_fill_prices(
    legs: List[OptionContract], leg_quantities: List[int]
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate natural, midpoint, and conservative fill prices.
    Returns: (natural_price, midpoint_price, conservative_fill_estimate)
    Prices are represented as cash impact per 1 unit of strategy (positive = debit, negative = credit)
    """
    natural_sum = 0.0
    midpoint_sum = 0.0
    conservative_sum = 0.0

    for leg, qty in zip(legs, leg_quantities):
        if leg.bid is None or leg.ask is None:
            return None, None, None
            
        mid = (leg.bid + leg.ask) / 2.0
        midpoint_sum += mid * qty

        if qty > 0:
            # Buying: Natural is Ask, Conservative is Ask
            natural_sum += leg.ask * qty
            conservative_sum += leg.ask * qty
        else:
            # Selling: Natural is Bid, Conservative is Bid
            natural_sum += leg.bid * qty
            conservative_sum += leg.bid * qty

    return natural_sum, midpoint_sum, conservative_sum


def calculate_payoff(
    strategy_type: StrategyType,
    legs: List[OptionContract],
    leg_quantities: List[int]
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], List[float]]:
    """
    Calculate payoff metrics based on the conservative fill estimate.
    Returns: (net_debit, net_credit, max_loss, max_profit, breakeven_points)
    Values are multiplied by contract_multiplier.
    """
    _, _, fill_price = calculate_fill_prices(legs, leg_quantities)
    if fill_price is None:
        return None, None, None, None, []

    # Calculate actual dollar cost using multiplier
    # Assuming all legs have the same multiplier for simple standard structures
    multiplier = legs[0].contract_multiplier
    cash_flow = fill_price * multiplier

    net_debit = cash_flow if cash_flow > 0 else 0.0
    net_credit = -cash_flow if cash_flow < 0 else 0.0

    max_loss = None
    max_profit = None
    breakevens = []

    if strategy_type == StrategyType.LONG_CALL:
        max_loss = net_debit
        # Theoretically unlimited
        breakevens = [legs[0].strike + fill_price]
        
    elif strategy_type == StrategyType.LONG_PUT:
        max_loss = net_debit
        # Technically strike * multiplier - debit, but practically 'unlimited' downside
        max_profit = (legs[0].strike * multiplier) - net_debit
        breakevens = [legs[0].strike - fill_price]
        
    elif strategy_type in (StrategyType.CALL_DEBIT_SPREAD, StrategyType.PUT_DEBIT_SPREAD):
        max_loss = net_debit
        width = abs(legs[0].strike - legs[1].strike) * multiplier
        max_profit = width - net_debit
        
        if strategy_type == StrategyType.CALL_DEBIT_SPREAD:
            # Long lower strike call, short higher strike call
            long_strike = min(legs[0].strike, legs[1].strike)
            breakevens = [long_strike + fill_price]
        else:
            # Long higher strike put, short lower strike put
            long_strike = max(legs[0].strike, legs[1].strike)
            breakevens = [long_strike - fill_price]
            
    elif strategy_type in (StrategyType.BULL_PUT_SPREAD, StrategyType.BEAR_CALL_SPREAD):
        max_profit = net_credit
        width = abs(legs[0].strike - legs[1].strike) * multiplier
        max_loss = width - net_credit
        
        if strategy_type == StrategyType.BULL_PUT_SPREAD:
            # Short higher put, long lower put
            # Breakeven = Short Put Strike - Net Credit (per share)
            short_strike = max(legs[0].strike, legs[1].strike)
            breakevens = [short_strike - (-fill_price)] 
        else:
            # Short lower call, long higher call
            # Breakeven = Short Call Strike + Net Credit (per share)
            short_strike = min(legs[0].strike, legs[1].strike)
            breakevens = [short_strike + (-fill_price)] 

    return net_debit, net_credit, max_loss, max_profit, breakevens


def calculate_combined_greeks(
    legs: List[OptionContract], leg_quantities: List[int]
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Calculate combined Greeks for the strategy.
    Returns: (delta, gamma, theta, vega)
    Values are multiplied by contract_multiplier.
    """
    c_delta, c_gamma, c_theta, c_vega = 0.0, 0.0, 0.0, 0.0
    
    for leg, qty in zip(legs, leg_quantities):
        if leg.greeks.delta is None:
            return None, None, None, None
            
        mult = leg.contract_multiplier * qty
        c_delta += leg.greeks.delta * mult
        
        if leg.greeks.gamma is not None:
            c_gamma += leg.greeks.gamma * mult
        if leg.greeks.theta is not None:
            c_theta += leg.greeks.theta * mult
        if leg.greeks.vega is not None:
            c_vega += leg.greeks.vega * mult
            
    return c_delta, c_gamma, c_theta, c_vega
