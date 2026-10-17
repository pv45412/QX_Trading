import math
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from qx.config.rules_config import RulesEngineConfig, load_rules_config
from qx.portfolio.models import (
    AccountRiskContext, 
    PortfolioRiskResult, 
    PortfolioRiskState,
    FreshnessState
)
from qx.portfolio.sectors import normalize_sector
from qx.options_expression.models import OptionsExpressionResult, StrategyCandidate
from qx.options_expression.greeks import is_greek_available


class PortfolioRiskEngine:
    def __init__(self, rules_config: Optional[RulesEngineConfig] = None):
        self.config = rules_config or load_rules_config()
        self.risk_cfg = self.config.portfolio_risk
        self.engine_version = "1.0"

    def evaluate_portfolio_risk(
        self,
        candidate: StrategyCandidate,
        expr_result: OptionsExpressionResult,
        account_ctx: AccountRiskContext,
        evaluation_timestamp: Optional[datetime | str] = None,
    ) -> PortfolioRiskResult:
        if isinstance(evaluation_timestamp, datetime):
            evaluated_at = evaluation_timestamp.isoformat()
        else:
            evaluated_at = evaluation_timestamp or expr_result.evaluated_at
        
        result = PortfolioRiskResult(
            risk_result_id=f"pr_{uuid.uuid4().hex[:8]}",
            expression_id=expr_result.expression_id,
            candidate_id=candidate.candidate_id,
            symbol=expr_result.symbol,
            strategy_type=candidate.strategy_type.value,
            direction=candidate.direction,
            state=PortfolioRiskState.PORTFOLIO_APPROVED,
            account_id=account_ctx.account_id,
            account_equity=account_ctx.equity,
            buying_power_available=account_ctx.buying_power,
            evaluated_at=evaluated_at,
            data_as_of=account_ctx.data_as_of.isoformat() if hasattr(account_ctx.data_as_of, 'isoformat') else str(account_ctx.data_as_of),
            config_version=self.config.version,
            engine_version=self.engine_version,
            portfolio_delta_before=account_ctx.greeks.net_delta,
            portfolio_gamma_before=account_ctx.greeks.net_gamma,
            portfolio_theta_before=account_ctx.greeks.net_theta,
            portfolio_vega_before=account_ctx.greeks.net_vega,
        )
        
        reason_codes = []
        ladder = {}

        def block(reason: str):
            result.state = PortfolioRiskState.BLOCKED
            reason_codes.append(reason)
            ladder[reason] = "BLOCKED"
            
        def veto(reason: str):
            if result.state != PortfolioRiskState.BLOCKED:
                result.state = PortfolioRiskState.PORTFOLIO_VETOED
                reason_codes.append(reason)
                ladder[reason] = "VETOED"
                
        # 1. Phase 9 State
        if expr_result.state != "SUITABLE":
            block("CANDIDATE_NOT_SUITABLE")
                
        # 2. Account Freshness and State
        if account_ctx.freshness in [FreshnessState.STALE_BLOCKED, FreshnessState.STALE_WARNED]:
            block("STALE_ACCOUNT_DATA")
            
        if getattr(account_ctx, "read_only", None) is False:
            block("ACCOUNT_NOT_READ_ONLY")
            
        if getattr(account_ctx, "sync_status", None) != "SYNCED":
            block("ACCOUNT_SYNC_ERROR")

        if (
            getattr(account_ctx, "sector_status", "UNAVAILABLE") != "KNOWN"
            or any(
                getattr(position, "sector_status", "UNAVAILABLE") != "KNOWN"
                for position in account_ctx.positions
            )
        ):
            block("SECTOR_PROVENANCE_INCOMPLETE")
        
        if account_ctx.equity <= 0:
            block("ACCOUNT_DATA_UNAVAILABLE")

        multiplier = getattr(candidate, "contract_multiplier", None)
        if multiplier is None or not math.isfinite(multiplier) or multiplier <= 0:
            block("CONTRACT_MULTIPLIER_UNAVAILABLE")
        else:
            multiplier = float(multiplier)

        # 3. Candidate Max Loss Known
        max_loss = candidate.max_loss
        if max_loss is None or math.isnan(max_loss) or math.isinf(max_loss):
            block("MAX_LOSS_UNAVAILABLE")
        else:
            result.max_loss_per_contract = max_loss
            result.candidate_quantity = 1
            result.candidate_total_max_loss = max_loss * 1

        # If blocked at data level, stop early
        if result.state == PortfolioRiskState.BLOCKED:
            result.reason_codes = reason_codes
            result.evidence_ladder = ladder
            return result
            
        # 4. Max contracts / Risk Budget
        max_allowed_risk_dollars = account_ctx.equity * (self.risk_cfg.per_trade.max_risk_pct_equity / 100.0)
        result.max_allowed_risk_dollars = round(max_allowed_risk_dollars, 2)
        result.max_allowed_risk_pct = self.risk_cfg.per_trade.max_risk_pct_equity
        
        if result.candidate_total_max_loss > max_allowed_risk_dollars:
            veto("PER_TRADE_RISK_EXCEEDED")
            max_contracts_risk = 0
        else:
            if result.max_loss_per_contract > 0:
                max_contracts_risk = int(math.floor(max_allowed_risk_dollars / result.max_loss_per_contract))
            else:
                max_contracts_risk = 999999
                
        # 5. Daily Loss Budget
        current_daily_loss = max(0.0, -(account_ctx.daily_realized_pnl + getattr(account_ctx, "daily_unrealized_pnl", 0.0)))
        result.daily_loss_used = round(current_daily_loss, 2)
        
        max_daily_loss = min(
            account_ctx.equity * (self.risk_cfg.daily.max_loss_pct_equity / 100.0),
            self.risk_cfg.daily.max_loss_dollars
        )
        daily_loss_remaining = max_daily_loss - current_daily_loss
        result.daily_loss_remaining = round(max(0.0, daily_loss_remaining), 2)
        
        if result.daily_loss_remaining <= 0:
            veto("DAILY_LOSS_LIMIT_REACHED")
            max_contracts_daily = 0
        elif result.candidate_total_max_loss > result.daily_loss_remaining:
            veto("DAILY_LOSS_LIMIT_REACHED")
            max_contracts_daily = 0
        else:
            if result.max_loss_per_contract > 0:
                max_contracts_daily = int(math.floor(result.daily_loss_remaining / result.max_loss_per_contract))
            else:
                max_contracts_daily = 999999

        # 6. Buying Power Sufficient
        bp_req = result.max_loss_per_contract
        from qx.options_expression.models import StrategyType
        if candidate.strategy_type in (
            StrategyType.LONG_CALL,
            StrategyType.LONG_PUT,
            StrategyType.CALL_DEBIT_SPREAD,
            StrategyType.PUT_DEBIT_SPREAD,
            "LONG_CALL",
            "LONG_PUT",
            "CALL_DEBIT_SPREAD",
            "PUT_DEBIT_SPREAD",
        ) and getattr(candidate, "net_debit", None) is not None:
            bp_req = candidate.net_debit
            
        result.candidate_buying_power_required = round(bp_req, 2)
        
        min_buffer = self.risk_cfg.buying_power.min_remaining_pct 
        bp_buffer = account_ctx.equity * (min_buffer / 100.0)
        bp_available_for_trade = max(0.0, account_ctx.buying_power - bp_buffer)
        
        if bp_available_for_trade <= 0:
            veto("INSUFFICIENT_BUYING_POWER")
            max_contracts_bp = 0
        elif bp_req > bp_available_for_trade:
            veto("INSUFFICIENT_BUYING_POWER")
            max_contracts_bp = 0
        else:
            if bp_req > 0:
                max_contracts_bp = int(math.floor(bp_available_for_trade / bp_req))
            else:
                max_contracts_bp = 999999

        # Current Symbol/Sector Exposure
        result.exposure_basis = "MAX_LOSS"
        sym = expr_result.symbol.upper()
        # determine sector from rules engine sector benchmarks
        benchmarks = self.config.direction_engine.sector_benchmarks
        sector = normalize_sector(benchmarks.get(sym)).canonical_sector_id
        if sector is None:
            block("SECTOR_PROVENANCE_INCOMPLETE")

        if result.state == PortfolioRiskState.BLOCKED:
            result.reason_codes = reason_codes
            result.evidence_ladder = ladder
            return result
        
        sym_exposure = 0.0
        sec_exposure = 0.0
        for p in account_ctx.positions:
            val = abs(p.quantity) * p.current_price * (100.0 if p.asset_class == "OPTION" else 1.0)
            if p.symbol.upper() == sym:
                sym_exposure += val
            if p.sector_status == "KNOWN" and p.canonical_sector_id == sector:
                sec_exposure += val
                
        result.symbol_exposure_before = round(sym_exposure, 2)
        result.sector_exposure_before = round(sec_exposure, 2)
        
        candidate_exposure = result.max_loss_per_contract 
        post_sym_exposure = sym_exposure + result.candidate_total_max_loss
        post_sec_exposure = sec_exposure + result.candidate_total_max_loss
        
        result.symbol_exposure_after = round(post_sym_exposure, 2)
        result.sector_exposure_after = round(post_sec_exposure, 2)
        
        sym_pct = (post_sym_exposure / account_ctx.equity) * 100.0 if account_ctx.equity > 0 else 0.0
        sec_pct = (post_sec_exposure / account_ctx.equity) * 100.0 if account_ctx.equity > 0 else 0.0
        
        result.concentration_before = round((sym_exposure / account_ctx.equity) * 100.0, 2) if account_ctx.equity > 0 else 0.0
        result.concentration_after = round(sym_pct, 2)
        
        allowed_sym_exposure = (self.risk_cfg.concentration.max_symbol_pct / 100.0) * account_ctx.equity
        remaining_sym = allowed_sym_exposure - sym_exposure
        
        if sym_pct > self.risk_cfg.concentration.max_symbol_pct:
            veto("SYMBOL_CONCENTRATION_EXCEEDED")
            max_contracts_sym = int(math.floor(max(0, remaining_sym) / candidate_exposure)) if candidate_exposure > 0 else 0
        else:
            max_contracts_sym = int(math.floor(max(0, remaining_sym) / candidate_exposure)) if candidate_exposure > 0 else 999999

        allowed_sec_exposure = (self.risk_cfg.concentration.max_sector_pct / 100.0) * account_ctx.equity
        remaining_sec = allowed_sec_exposure - sec_exposure
        
        if sec_pct > self.risk_cfg.concentration.max_sector_pct:
            veto("SECTOR_CONCENTRATION_EXCEEDED")
            max_contracts_sec = int(math.floor(max(0, remaining_sec) / candidate_exposure)) if candidate_exposure > 0 else 0
        else:
            max_contracts_sec = int(math.floor(max(0, remaining_sec) / candidate_exposure)) if candidate_exposure > 0 else 999999
            
        # Correlated Exposure
        correlation_group = None
        for group, symbols in getattr(self.risk_cfg, "correlation_groups", {}).items():
            if sym in symbols:
                correlation_group = group
                break
                
        existing_related = []
        if correlation_group:
            group_symbols = self.risk_cfg.correlation_groups[correlation_group]
            for p in account_ctx.positions:
                if p.symbol.upper() in group_symbols and p.symbol.upper() != sym:
                    existing_related.append(p.symbol.upper())
                    
        result.existing_related_positions = list(set(existing_related))
        if len(existing_related) > 0:
            result.correlation_risk = True
            
        # Dummy correlation cap
        max_contracts_corr = 999999

        # Portfolio Greeks
        greek_limits = self.risk_cfg.greek_limits
        candidate_greeks = {
            "delta": candidate.combined_delta,
            "gamma": candidate.combined_gamma,
            "theta": candidate.combined_theta,
            "vega": candidate.combined_vega,
        }
        configured_limits = {
            "delta": greek_limits.max_abs_delta,
            "gamma": greek_limits.max_abs_gamma,
            "theta": greek_limits.max_negative_theta,
            "vega": greek_limits.max_abs_vega,
        }
        semantic_availability = {}
        for greek_name, limit in configured_limits.items():
            declared_available = (
                candidate.combined_greek_availability.get(greek_name) == "AVAILABLE"
            )
            complete_coverage = candidate.combined_greek_coverage.get(greek_name) == 1.0
            provenance = candidate.combined_greek_provenance.get(
                greek_name, "UNAVAILABLE"
            )
            semantic_availability[greek_name] = (
                declared_available
                and complete_coverage
                and is_greek_available(
                    candidate_greeks[greek_name],
                    provenance,
                    candidate.combined_greek_metadata.get(
                        greek_name,
                        {
                            "combined": True,
                            "all_legs_available": False,
                            "source_metadata_valid": False,
                        },
                    ),
                )
            )
            if not semantic_availability[greek_name]:
                candidate_greeks[greek_name] = None
            if limit is not None and not semantic_availability[greek_name]:
                block(f"CANDIDATE_{greek_name.upper()}_UNAVAILABLE")

        if result.state == PortfolioRiskState.BLOCKED:
            result.reason_codes = reason_codes
            result.evidence_ladder = ladder
            return result

        cand_delta = candidate_greeks["delta"]
        cand_gamma = candidate_greeks["gamma"]
        cand_theta = candidate_greeks["theta"]
        cand_vega = candidate_greeks["vega"]

        post_delta = account_ctx.greeks.net_delta + cand_delta if cand_delta is not None else None
        post_gamma = account_ctx.greeks.net_gamma + cand_gamma if cand_gamma is not None else None
        post_theta = account_ctx.greeks.net_theta + cand_theta if cand_theta is not None else None
        post_vega = account_ctx.greeks.net_vega + cand_vega if cand_vega is not None else None

        result.portfolio_delta_after = round(post_delta, 4) if post_delta is not None else None
        result.portfolio_gamma_after = round(post_gamma, 4) if post_gamma is not None else None
        result.portfolio_theta_after = round(post_theta, 4) if post_theta is not None else None
        result.portfolio_vega_after = round(post_vega, 4) if post_vega is not None else None
        
        def _get_greek_cap(limit, before, cand):
            if cand == 0: return 999999
            is_hedge = (cand * before) < 0
            if is_hedge and not self.risk_cfg.hedge_policy.allowance_enabled:
                room = limit - abs(before)
                return int(math.floor(max(0, room) / abs(cand)))
            room = limit - abs(before) if not is_hedge else limit + abs(before)
            return int(math.floor(max(0, room) / abs(cand)))
            
        max_contracts_delta = _get_greek_cap(greek_limits.max_abs_delta, account_ctx.greeks.net_delta, cand_delta) if greek_limits.max_abs_delta is not None else 999999
        max_contracts_gamma = _get_greek_cap(greek_limits.max_abs_gamma, account_ctx.greeks.net_gamma, cand_gamma) if greek_limits.max_abs_gamma is not None else 999999
        max_contracts_vega = _get_greek_cap(greek_limits.max_abs_vega, account_ctx.greeks.net_vega, cand_vega) if greek_limits.max_abs_vega is not None else 999999
        
        max_contracts_theta = 999999
        if greek_limits.max_negative_theta is not None and cand_theta < 0:
            room = abs(greek_limits.max_negative_theta) - abs(account_ctx.greeks.net_theta) if account_ctx.greeks.net_theta < 0 else abs(greek_limits.max_negative_theta)
            if not self.risk_cfg.hedge_policy.allowance_enabled and account_ctx.greeks.net_theta > 0:
                room = abs(greek_limits.max_negative_theta)
            max_contracts_theta = int(math.floor(max(0, room) / abs(cand_theta)))
        
        if greek_limits.max_abs_delta is not None and abs(post_delta) > greek_limits.max_abs_delta:
            veto("PORTFOLIO_DELTA_LIMIT_EXCEEDED")
            
        if greek_limits.max_abs_gamma is not None and abs(post_gamma) > greek_limits.max_abs_gamma:
            veto("PORTFOLIO_GAMMA_LIMIT_EXCEEDED")
            
        if greek_limits.max_abs_vega is not None and abs(post_vega) > greek_limits.max_abs_vega:
            veto("PORTFOLIO_VEGA_LIMIT_EXCEEDED")
            
        if greek_limits.max_negative_theta is not None and post_theta < greek_limits.max_negative_theta:
            veto("THETA_LIMIT_EXCEEDED")

        result.max_contracts_by_risk = max_contracts_risk
        result.max_contracts_by_daily_loss = max_contracts_daily
        result.max_contracts_by_buying_power = max_contracts_bp
        result.max_contracts_by_symbol = max_contracts_sym
        result.max_contracts_by_sector = max_contracts_sec
        result.max_contracts_by_delta = max_contracts_delta
        result.max_contracts_by_gamma = max_contracts_gamma
        result.max_contracts_by_vega = max_contracts_vega
        result.max_contracts_by_theta = max_contracts_theta
        result.max_contracts_by_correlation = max_contracts_corr
        
        caps = {
            "PER_TRADE_RISK": max_contracts_risk,
            "DAILY_LOSS_LIMIT": max_contracts_daily,
            "BUYING_POWER": max_contracts_bp,
            "SYMBOL_CONCENTRATION": max_contracts_sym,
            "SECTOR_CONCENTRATION": max_contracts_sec,
            "PORTFOLIO_DELTA": max_contracts_delta,
            "PORTFOLIO_GAMMA": max_contracts_gamma,
            "PORTFOLIO_VEGA": max_contracts_vega,
            "PORTFOLIO_THETA": max_contracts_theta,
        }
        
        min_cap = min(caps.values())
        binding = [k for k, v in caps.items() if v == min_cap][0]
        result.binding_constraint = binding
        
        result.recommended_max_contracts = max(0, min_cap)
        result.approved_contracts_cap = result.recommended_max_contracts
        
        if result.approved_contracts_cap == 0 and result.state != PortfolioRiskState.BLOCKED:
            veto(f"CAPACITY_EXHAUSTED_{binding}")
        
        if result.state == PortfolioRiskState.PORTFOLIO_APPROVED:
            reason_codes.append("PORTFOLIO_RISK_APPROVED")
            
        result.reason_codes = reason_codes
        result.evidence_ladder = ladder

        return result
