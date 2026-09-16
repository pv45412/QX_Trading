"""Phase 9 Options Expression Engine."""

import datetime
from typing import Any, Dict, List, Optional
import uuid

from qx.config.rules_config import RulesEngineConfig
from qx.tradeability.models import TradeabilityResult, TradeabilityState
from qx.options_expression.models import (
    OptionsContext,
    OptionsExpressionResult,
    OptionsExpressionState,
    StrategyCandidate,
    StrategyType,
    OptionContract,
)
from qx.options_expression.math import calculate_payoff, calculate_combined_greeks, calculate_fill_prices


class OptionsExpressionEngine:
    def __init__(self, rules_config: Optional[RulesEngineConfig] = None):
        self.config = rules_config or RulesEngineConfig()
        self.oe_cfg = self.config.options_expression
        self.engine_version = "v9.0.0"

    def evaluate_options_expression(
        self,
        tradeability: TradeabilityResult,
        context: OptionsContext,
    ) -> OptionsExpressionResult:
        
        eval_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = OptionsExpressionResult(
            expression_id=f"expr_{uuid.uuid4().hex[:8]}",
            tradeability_id=tradeability.tradeability_id,
            playbook_id=tradeability.playbook_id,
            symbol=tradeability.symbol,
            direction=tradeability.direction,
            state=OptionsExpressionState.NOT_SUITABLE,
            underlying_price=context.underlying_price,
            data_as_of=context.data_as_of,
            evaluated_at=eval_time,
            publication_state=tradeability.publication_state.value,
            iv=context.iv_raw,
            iv_rank=context.iv_rank,
            iv_percentile=context.iv_percentile,
            config_version=self.config.version,
            engine_version=self.engine_version,
        )
        
        # 1. Tradeability Gate
        if tradeability.state != TradeabilityState.TRADEABLE:
            result.state = OptionsExpressionState.BLOCKED
            result.reason_codes.append("UNDERLYING_NOT_TRADEABLE")
            return result

        # 2. Expiration Selection
        playbook_dte_cfg = self.oe_cfg.dte.playbook_windows.get(tradeability.playbook_id)
        if not playbook_dte_cfg:
            result.state = OptionsExpressionState.NOT_SUITABLE
            result.reason_codes.append("NO_VALID_EXPIRATION")
            return result

        valid_expirations = []
        for expiration_date, strikes in context.chain.items():
            # Get an arbitrary contract to check DTE
            first_strike = list(strikes.values())[0]
            first_contract = list(first_strike.values())[0]
            if playbook_dte_cfg.min <= first_contract.dte <= playbook_dte_cfg.max:
                valid_expirations.append(expiration_date)
                
        if not valid_expirations:
            result.state = OptionsExpressionState.NOT_SUITABLE
            result.reason_codes.append("NO_VALID_EXPIRATION")
            return result
            
        # Check event risk
        for event in context.events:
            # Simple check if event happens within earliest valid DTE
            # Real implementation would parse dates
            result.event_risk = True

        candidates = []
        for expiration in valid_expirations:
            strikes = context.chain[expiration]
            if tradeability.direction == "BULLISH":
                # LONG CALL
                lc_candidate = self._build_long_option(
                    strikes, expiration, is_call=True,
                    target_delta_min=self.oe_cfg.long_option.delta_min,
                    target_delta_max=self.oe_cfg.long_option.delta_max
                )
                if lc_candidate: candidates.append(lc_candidate)
                
                # CALL DEBIT SPREAD
                cds_candidate = self._build_debit_spread(
                    strikes, expiration, is_call=True,
                    long_delta_min=self.oe_cfg.debit_spread.long_delta_min,
                    long_delta_max=self.oe_cfg.debit_spread.long_delta_max,
                    structural_targets=tradeability.target_candidates
                )
                if cds_candidate: candidates.append(cds_candidate)
                
                # BULL PUT SPREAD
                bps_candidate = self._build_credit_spread(
                    strikes, expiration, is_call=False,
                    short_delta_min=self.oe_cfg.credit_spread.short_delta_min,
                    short_delta_max=self.oe_cfg.credit_spread.short_delta_max,
                    width=self.oe_cfg.credit_spread.width
                )
                if bps_candidate: candidates.append(bps_candidate)
                
            elif tradeability.direction == "BEARISH":
                # LONG PUT
                lp_candidate = self._build_long_option(
                    strikes, expiration, is_call=False,
                    # For puts, delta is negative, so we use absolute values
                    target_delta_min=self.oe_cfg.long_option.delta_min,
                    target_delta_max=self.oe_cfg.long_option.delta_max
                )
                if lp_candidate: candidates.append(lp_candidate)
                
                # PUT DEBIT SPREAD
                pds_candidate = self._build_debit_spread(
                    strikes, expiration, is_call=False,
                    long_delta_min=self.oe_cfg.debit_spread.long_delta_min,
                    long_delta_max=self.oe_cfg.debit_spread.long_delta_max,
                    structural_targets=tradeability.target_candidates
                )
                if pds_candidate: candidates.append(pds_candidate)
                
                # BEAR CALL SPREAD
                bcs_candidate = self._build_credit_spread(
                    strikes, expiration, is_call=True,
                    short_delta_min=self.oe_cfg.credit_spread.short_delta_min,
                    short_delta_max=self.oe_cfg.credit_spread.short_delta_max,
                    width=self.oe_cfg.credit_spread.width
                )
                if bcs_candidate: candidates.append(bcs_candidate)

        # Apply liquidity gates and payoff math
        valid_candidates = []
        for cand in candidates:
            cand.direction = tradeability.direction
            if not self._validate_liquidity(cand.legs, result):
                # Reason codes are appended in _validate_liquidity
                cand.reason_codes.append("OPTION_LIQUIDITY_INADEQUATE")
                continue
                
            net_debit, net_credit, max_loss, max_profit, breakevens = calculate_payoff(
                cand.strategy_type, cand.legs, cand.leg_quantities
            )
            
            if max_loss is None and cand.strategy_type != StrategyType.LONG_CALL and cand.strategy_type != StrategyType.LONG_PUT:
                 cand.reason_codes.append("MAX_LOSS_UNDEFINED")
                 continue
                 
            cand.net_debit = net_debit
            cand.net_credit = net_credit
            cand.max_loss = max_loss
            cand.max_profit = max_profit
            cand.breakeven_points = breakevens
            
            c_delta, c_gamma, c_theta, c_vega = calculate_combined_greeks(cand.legs, cand.leg_quantities)
            cand.combined_delta = c_delta
            cand.combined_gamma = c_gamma
            cand.combined_theta = c_theta
            cand.combined_vega = c_vega
            
            if cand.net_debit and cand.net_debit > 0 and c_theta is not None:
                cand.theta_pct_of_debit = (c_theta / cand.net_debit)
            
            self._score_candidate(cand, context)
            valid_candidates.append(cand)
            
        if not valid_candidates:
            if not result.reason_codes:
                result.reason_codes.append("NO_VALID_STRIKE")
            result.state = OptionsExpressionState.NOT_SUITABLE
            return result
            
        # Rank and select
        valid_candidates.sort(key=lambda x: x.strategy_fit_score, reverse=True)
        result.candidate_strategies = valid_candidates
        result.primary_candidate_id = valid_candidates[0].candidate_id
        result.state = OptionsExpressionState.SUITABLE
        result.reason_codes.append("OPTIONS_SUITABLE")
        return result

    def _validate_liquidity(self, legs: List[OptionContract], result: OptionsExpressionResult) -> bool:
        for leg in legs:
            if leg.contract_multiplier is None:
                # Can't evaluate payoff math without multiplier
                result.reason_codes.append("CONTRACT_MULTIPLIER_UNAVAILABLE")
                return False
                
            if leg.quote_age_seconds > self.oe_cfg.quote_freshness.max_age_seconds:
                if "STALE_OPTION_CHAIN" not in result.reason_codes:
                    result.reason_codes.append("STALE_OPTION_CHAIN")
                return False
            if leg.bid is None or leg.ask is None or leg.bid >= leg.ask:
                if "INVALID_OPTION_MARKET" not in result.reason_codes:
                    result.reason_codes.append("INVALID_OPTION_MARKET")
                return False
                
            mid = (leg.bid + leg.ask) / 2
            if mid == 0:
                return False
            spread_pct = (leg.ask - leg.bid) / mid
            if spread_pct > self.oe_cfg.liquidity.max_spread_pct:
                if "SPREAD_TOO_WIDE" not in result.reason_codes:
                    result.reason_codes.append("SPREAD_TOO_WIDE")
                return False
                
            if leg.open_interest < self.oe_cfg.liquidity.min_open_interest:
                if "OPEN_INTEREST_TOO_LOW" not in result.reason_codes:
                    result.reason_codes.append("OPEN_INTEREST_TOO_LOW")
                return False
                
            if leg.volume < self.oe_cfg.liquidity.min_volume:
                if "OPTION_VOLUME_TOO_LOW" not in result.reason_codes:
                    result.reason_codes.append("OPTION_VOLUME_TOO_LOW")
                return False
        return True
        
    def _score_candidate(self, cand: StrategyCandidate, context: OptionsContext):
        # Calculate fill assumptions (natural vs midpoint) for recording
        natural_price = 0.0
        midpoint_price = 0.0
        for leg, qty in zip(cand.legs, cand.leg_quantities):
            # If qty > 0 we are buying so natural is Ask
            # If qty < 0 we are selling so natural is Bid
            if qty > 0:
                natural_price += leg.ask
            else:
                natural_price -= leg.bid
            midpoint_price += (leg.bid + leg.ask) / 2.0 * qty
        cand.natural_price = natural_price
        cand.midpoint_price = midpoint_price
        cand.conservative_fill_estimate = natural_price # Conservative is natural
        
        # Max loss definition invariant
        if cand.max_loss is None or str(cand.max_loss) in ["nan", "inf", "-inf"]:
             cand.reason_codes.append("MAX_LOSS_UNDEFINED")
             return # Remains un-scored, will fail gate
             

        # Event risk check
        for event in context.events:
            # Simplified check: if event is known, we apply penalty to candidates
            cand.event_risk_identified = True
            cand.events.append(event)
            cand.reason_codes.append("EVENT_BEFORE_EXPIRATION")
            cand.event_policy = self.oe_cfg.event_risk_policy
            

        # Base score 50
        score = 50.0
        
        # IV Regime adjustment
        if context.iv_rank is not None:
            if context.iv_rank <= self.oe_cfg.volatility.low_iv_rank_max:
                if cand.net_debit and cand.net_debit > 0:
                    score += 20.0
            elif context.iv_rank >= self.oe_cfg.volatility.high_iv_rank_min:
                if cand.net_credit and cand.net_credit > 0:
                    score += 20.0
                    
        # Structural target fit penalty
        if cand.structural_target_fit is not None:
             cand.target_fit_distance = cand.structural_target_fit
             if cand.target_fit_distance > 5.0:
                 cand.reason_codes.append("STRUCTURAL_TARGET_MISMATCH")
                 score -= self.oe_cfg.structural_target_penalty
                 cand.target_fit_score = -self.oe_cfg.structural_target_penalty
             else:
                 cand.target_fit_score = 0.0
             
        if cand.event_risk_identified:
             if cand.event_policy == "SCORE_PENALTY":
                 score -= self.oe_cfg.event_risk_penalty
                 cand.event_penalty_applied = self.oe_cfg.event_risk_penalty
             elif cand.event_policy == "NOT_SUITABLE":
                 cand.reason_codes.append("EVENT_RISK_BLOCKED")
                 return
             elif cand.event_policy == "BLOCK":
                 cand.reason_codes.append("EVENT_RISK_BLOCKED")
                 return
             
        cand.strategy_fit_score = max(0.0, min(100.0, score))

    def _build_long_option(
        self, strikes: Dict[float, Dict[str, OptionContract]], expiration: str, is_call: bool,
        target_delta_min: float, target_delta_max: float
    ) -> Optional[StrategyCandidate]:
        best_leg = None
        best_diff = 999.0
        opt_type = "CALL" if is_call else "PUT"
        
        target_mid = (target_delta_min + target_delta_max) / 2.0
        
        for strike, opts in strikes.items():
            if opt_type in opts:
                leg = opts[opt_type]
                delta = leg.greeks.delta
                if delta is not None:
                    abs_delta = abs(delta)
                    if target_delta_min <= abs_delta <= target_delta_max:
                        diff = abs(abs_delta - target_mid)
                        if diff < best_diff:
                            best_diff = diff
                            best_leg = leg
                            
        if best_leg:
            cand = StrategyCandidate(
                candidate_id=f"cand_{uuid.uuid4().hex[:8]}",
                strategy_type=StrategyType.LONG_CALL if is_call else StrategyType.LONG_PUT,
                direction="",
                expiration=expiration,
                dte=best_leg.dte,
                legs=[best_leg],
                leg_quantities=[1]
            )
            return cand
        return None

    def _build_debit_spread(
        self, strikes: Dict[float, Dict[str, OptionContract]], expiration: str, is_call: bool,
        long_delta_min: float, long_delta_max: float, structural_targets: List[float]
    ) -> Optional[StrategyCandidate]:
        opt_type = "CALL" if is_call else "PUT"
        
        # 1. Find long leg
        long_cand = self._build_long_option(strikes, expiration, is_call, long_delta_min, long_delta_max)
        if not long_cand:
            return None
        long_leg = long_cand.legs[0]
        
        # 2. Find short leg closest to nearest structural target
        if not structural_targets:
            return None # Require structural target for debit spread in this simplified implementation
            
        target = structural_targets[0]
        best_short = None
        best_dist = 99999.0
        
        for strike, opts in strikes.items():
            # For debit spread, short strike must be further out than long strike
            if is_call and strike <= long_leg.strike: continue
            if not is_call and strike >= long_leg.strike: continue
            
            if opt_type in opts:
                leg = opts[opt_type]
                dist = abs(strike - target)
                if dist < best_dist:
                    best_dist = dist
                    best_short = leg
                    
        if best_short:
            cand = StrategyCandidate(
                candidate_id=f"cand_{uuid.uuid4().hex[:8]}",
                strategy_type=StrategyType.CALL_DEBIT_SPREAD if is_call else StrategyType.PUT_DEBIT_SPREAD,
                direction="",
                expiration=expiration,
                dte=long_leg.dte,
                legs=[long_leg, best_short],
                leg_quantities=[1, -1],
                structural_target_fit=best_dist,
                structural_target_price=target,
                structural_target_id="phase8_target_1",
                short_strike=best_short.strike
            )
            return cand
        return None

    def _build_credit_spread(
        self, strikes: Dict[float, Dict[str, OptionContract]], expiration: str, is_call: bool,
        short_delta_min: float, short_delta_max: float, width: float
    ) -> Optional[StrategyCandidate]:
        opt_type = "CALL" if is_call else "PUT"
        
        # 1. Find short leg using short_delta range
        short_cand = self._build_long_option(strikes, expiration, is_call, short_delta_min, short_delta_max)
        if not short_cand:
            return None
        short_leg = short_cand.legs[0]
        
        # 2. Find long leg at exact width
        target_strike = short_leg.strike + width if is_call else short_leg.strike - width
        
        long_leg = None
        # Try to find exact strike or closest wider strike
        for strike, opts in strikes.items():
            if is_call and strike >= target_strike:
                if opt_type in opts:
                    long_leg = opts[opt_type]
                    break
            elif not is_call and strike <= target_strike:
                if opt_type in opts:
                    long_leg = opts[opt_type]
                    break # Assuming strikes are sorted appropriately, wait, dictionary is not guaranteed sorted!
                    
        # Let's sort strikes
        sorted_strikes = sorted(strikes.keys(), reverse=not is_call) # For puts, want decreasing strikes
        for strike in sorted_strikes:
            if is_call and strike >= target_strike:
                if opt_type in strikes[strike]:
                    long_leg = strikes[strike][opt_type]
                    break
            elif not is_call and strike <= target_strike:
                if opt_type in strikes[strike]:
                    long_leg = strikes[strike][opt_type]
                    break
                    
        if long_leg:
            cand = StrategyCandidate(
                candidate_id=f"cand_{uuid.uuid4().hex[:8]}",
                strategy_type=StrategyType.BEAR_CALL_SPREAD if is_call else StrategyType.BULL_PUT_SPREAD,
                direction="",
                expiration=expiration,
                dte=short_leg.dte,
                legs=[short_leg, long_leg],
                leg_quantities=[-1, 1]
            )
            return cand
        return None
